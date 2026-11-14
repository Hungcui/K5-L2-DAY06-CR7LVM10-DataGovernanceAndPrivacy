"""Evaluate T02 on real BDD images with reproducible injected QC defects.

Run from the project root: python -m tools.t02_real_controlled_eval

The first 18 of 30 real images (sorted by file_id) form the unlabeled reference
split. The remaining 12 are held-out sources; four separately corrupted copies
of each form 48 known-positive evaluation cases. The original 12 are controls,
but are NOT labelled clean: BDD does not supply QC ground truth. This script
never reads the instructor's gt/ directory or calls the network.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from src import t02_qc as q


ROOT = Path(__file__).resolve().parents[1]
BDD = ROOT / "data" / "real" / "bdd"
OUT = ROOT / "out" / "t02_real_controlled"
DEFECTS = ("blur", "dark", "glare", "compression")


def _light(value: str) -> str:
    return {"daytime": "day", "dawn/dusk": "dusk", "undefined": "unknown"}.get(value, value)


def _inject(source: Path, destination: Path, defect: str) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    array = np.asarray(image).copy()
    if defect == "blur":
        result = image.filter(ImageFilter.GaussianBlur(radius=6))
        result.save(destination, "JPEG", quality=95)
    elif defect == "dark":
        result = Image.fromarray((array.astype(np.float32) * 0.12).astype(np.uint8))
        result.save(destination, "JPEG", quality=95)
    elif defect == "glare":
        height, width = array.shape[:2]
        array[height // 3 : 2 * height // 3, width // 3 : 2 * width // 3] = 255
        Image.fromarray(array).save(destination, "JPEG", quality=95)
    elif defect == "compression":
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=3)
        destination.write_bytes(buffer.getvalue())
    else:
        raise ValueError(f"Unknown defect: {defect}")


def _build_inputs() -> pd.DataFrame:
    metadata = pd.read_csv(BDD / "metadata.csv")
    manifest = pd.read_csv(BDD / "manifest.csv")
    required = {"file_id", "path", "timeofday"}
    if not required.issubset(metadata.columns):
        raise ValueError(f"BDD metadata missing: {sorted(required - set(metadata.columns))}")
    hashes = {
        str(path).replace("\\", "/"): str(sha)
        for path, sha in zip(manifest["path"], manifest["sha256"])
    }
    metadata = metadata.sort_values("file_id", kind="stable").reset_index(drop=True)
    if len(metadata) < 30:
        raise ValueError(f"Expected at least 30 downloaded real images, got {len(metadata)}")
    metadata = metadata.head(30)

    image_dir = OUT / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, item in enumerate(metadata.itertuples(index=False)):
        relative = str(item.path).replace("\\", "/")
        source = BDD / relative
        if not source.is_file() or relative not in hashes or q.sha256_file(source) != hashes[relative]:
            raise ValueError(f"Missing or altered real source image: {relative}")
        source_id = str(item.file_id)
        light = _light(str(item.timeofday))
        original = image_dir / f"{source_id}_original.jpg"
        shutil.copyfile(source, original)
        split = "dev" if index < 18 else "eval"
        rows.append({"image_id": f"{source_id}_original", "path": f"images/{original.name}",
                     "camera_id": "bdd_real", "light": light, "split": split,
                     "source_id": source_id, "injected_defect": "none",
                     "is_control": True})
        if split == "eval":
            for defect in DEFECTS:
                destination = image_dir / f"{source_id}_{defect}.jpg"
                _inject(source, destination, defect)
                rows.append({"image_id": f"{source_id}_{defect}",
                             "path": f"images/{destination.name}",
                             "camera_id": "bdd_real", "light": light, "split": "eval",
                             "source_id": source_id, "injected_defect": defect,
                             "is_control": False})
    return pd.DataFrame(rows)


def _summary(scored: pd.DataFrame, controls: pd.Series, model: str) -> dict:
    positive = scored[~scored["is_control"]].copy()
    positive["flagged"] = positive["pred_action"].eq("RECAPTURE")
    positive["correct_type"] = positive["pred_defect_type"].eq(positive["injected_defect"])
    positive["score_above_original"] = positive["score"] > positive["source_id"].map(controls)
    by_type = {}
    for defect, group in positive.groupby("injected_defect", sort=False):
        by_type[defect] = {
            "n": int(len(group)),
            "flagged": int(group["flagged"].sum()),
            "correct_type": int(group["correct_type"].sum()),
            "ranked_above_original": int(group["score_above_original"].sum()),
        }
    return {"model": model, "known_injected_cases": int(len(positive)),
            "flagged": int(positive["flagged"].sum()),
            "correct_type": int(positive["correct_type"].sum()),
            "ranked_above_original": int(positive["score_above_original"].sum()),
            "by_type": by_type}


def main() -> None:
    if not (BDD / "metadata.csv").exists() or not (BDD / "manifest.csv").exists():
        raise FileNotFoundError("Missing data/real/bdd; download the BDD pack first")
    OUT.mkdir(parents=True, exist_ok=True)
    data = _build_inputs()
    result = {"protocol": {
        "source": "BDD100K real images downloaded by tools.download_real_samples",
        "selection": "first 30 image IDs sorted ascending; 18 dev, 12 held-out sources",
        "evaluation": "12 held-out sources x 4 deterministic injected defects = 48 known positives",
        "limits": "Original images have no QC ground truth; no false-positive rate, precision, or Defect Recall@20 is claimed."
    }}
    frames = []
    for name, scorer in (("poc", q.run_poc), ("baseline", q.run_baseline)):
        scored = scorer(data, OUT)
        controls = scored[scored["is_control"]].set_index("source_id")["score"]
        result[name] = _summary(scored, controls, name)
        frame = scored[["image_id", "source_id", "light", "split", "is_control",
                        "injected_defect", "score", "pred_defect_type", "pred_action"]].copy()
        frame.insert(0, "model", name)
        frames.append(frame)
    pd.concat(frames, ignore_index=True).to_csv(OUT / "controlled_results.csv", index=False)
    (OUT / "controlled_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("30 real sources: 18 dev references; 12 held-out sources; 48 known injected defects")
    for name in ("poc", "baseline"):
        stats = result[name]
        print(f"\n{name.upper()}: flagged {stats['flagged']}/48; "
              f"correct type {stats['correct_type']}/48; "
              f"score above its original {stats['ranked_above_original']}/48")
        for defect in DEFECTS:
            values = stats["by_type"][defect]
            print(f"  {defect}: flagged {values['flagged']}/12, "
                  f"correct type {values['correct_type']}/12, "
                  f"above original {values['ranked_above_original']}/12")
    print(f"\nSaved: {OUT / 'controlled_results.csv'}")
    print(f"Saved: {OUT / 'controlled_summary.json'}")


if __name__ == "__main__":
    main()
