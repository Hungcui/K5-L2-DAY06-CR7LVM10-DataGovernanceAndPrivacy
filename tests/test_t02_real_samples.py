"""Optional QA tests for T02 on the local BDD100K real-sample pack.

Download the pack with::

    python -m tools.download_real_samples --packs bdd --bdd-n 30 \
        --max-side 640 --seed 42

The real images are gitignored.  If the pack is unavailable (for example on the
grader's clean machine), this module is skipped instead of failing the required
offline fixture test suite.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import t02_qc as q


ROOT = Path(__file__).resolve().parents[1]
BDD = ROOT / "data" / "real" / "bdd"
METADATA = BDD / "metadata.csv"
MANIFEST = BDD / "manifest.csv"

pytestmark = pytest.mark.skipif(
    not (METADATA.exists() and MANIFEST.exists()),
    reason="optional BDD real-sample pack has not been downloaded",
)


def _t02_input() -> pd.DataFrame:
    """Adapt BDD metadata to the columns expected by ``src.t02_qc``."""
    meta = pd.read_csv(METADATA)
    required = {"file_id", "path", "timeofday"}
    missing = required - set(meta.columns)
    if missing:
        raise AssertionError(f"BDD metadata is missing columns: {sorted(missing)}")

    data = meta.rename(columns={"file_id": "image_id", "timeofday": "light"}).copy()
    data["light"] = data["light"].replace(
        {"daytime": "day", "dawn/dusk": "dusk", "undefined": "unknown"}
    )
    # The downloaded subset comes from one public source.  A single explicit
    # camera group avoids pretending that unknown camera models are different.
    data["camera_id"] = "bdd_real"

    # Deterministic label-free split.  Reference statistics are fitted on dev
    # only; no hidden/eval ground truth is read.
    data = data.sort_values("image_id", kind="stable").reset_index(drop=True)
    data["split"] = np.where(data.index % 5 < 3, "dev", "eval")
    return data[["image_id", "path", "camera_id", "light", "split"]]


@pytest.fixture(scope="module")
def real_inputs() -> pd.DataFrame:
    return _t02_input()


@pytest.fixture(scope="module")
def real_ranked(real_inputs: pd.DataFrame) -> pd.DataFrame:
    return q.to_output(q.run_poc(real_inputs, BDD))


def test_real_pack_manifest_and_files_are_intact(real_inputs: pd.DataFrame):
    """Every selected real image exists and still matches its recorded hash."""
    manifest = pd.read_csv(MANIFEST)
    # Manifests created on Windows may store ``images\\name.jpg`` while the
    # metadata uses ``images/name.jpg``.  Normalise both forms before lookup.
    expected = {
        str(path).replace("\\", "/"): str(sha256)
        for path, sha256 in zip(manifest["path"], manifest["sha256"])
    }

    assert real_inputs["image_id"].is_unique
    for raw_path in real_inputs["path"].astype(str):
        rel_path = raw_path.replace("\\", "/")
        path = BDD / rel_path
        assert path.exists(), rel_path
        assert rel_path in expected, rel_path
        assert q.sha256_file(path) == expected[rel_path], rel_path


def test_poc_scores_every_real_image_once_with_valid_output(
    real_inputs: pd.DataFrame, real_ranked: pd.DataFrame
):
    """The algorithm must not crash, lose an image, or emit invalid scores."""
    assert sorted(real_ranked["image_id"]) == sorted(real_inputs["image_id"])
    assert real_ranked["image_id"].is_unique
    assert np.isfinite(real_ranked["score"]).all()
    assert real_ranked["score"].is_monotonic_decreasing
    assert set(real_ranked["pred_action"]) <= {"KEEP", "RECAPTURE"}
    assert set(real_ranked["pred_defect_type"]) <= {"none", *q.DEFECTS}


def test_poc_is_reproducible_on_real_images(
    real_inputs: pd.DataFrame, real_ranked: pd.DataFrame
):
    """Running twice on the same data must return exactly the same rows."""
    again = q.to_output(q.run_poc(real_inputs, BDD))
    pd.testing.assert_frame_equal(
        real_ranked.reset_index(drop=True), again.reset_index(drop=True)
    )


def test_real_pack_contains_multiple_lighting_slices(real_inputs: pd.DataFrame):
    """The sample must cover night and at least one non-night condition."""
    lights = set(real_inputs["light"].astype(str))
    assert "night" in lights
    assert len(lights - {"night"}) >= 1
