"""Required team QA tests for T02 Raw QC Triage.

These tests cover the assignment contract:
1. the official one-command pipeline produces a valid ranked_review.csv;
2. two seed-42 runs are exactly reproducible;
3. malformed metadata and empty images fail clearly.
"""
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from src import t02_qc as q


ROOT = Path(__file__).resolve().parents[1]


def _run_pipeline(output_dir: Path) -> pd.DataFrame:
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--config",
        "configs/lab.yaml",
        "--track",
        "t02",
        "--output",
        str(output_dir),
        "--run-name",
        "poc",
        "--offline",
        "--seed",
        "42",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        "T02 pipeline must exit with status 0.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    prediction = output_dir / "ranked_review.csv"
    assert prediction.exists(), f"Missing required output: {prediction}"
    frame = pd.read_csv(prediction)
    assert {"image_id", "score"} <= set(frame.columns)
    assert not frame[["image_id", "score"]].isna().any().any()
    assert np.isfinite(frame["score"]).all()
    assert frame["image_id"].is_unique
    return frame


def test_pipeline_one_command_creates_valid_ranked_review(tmp_path):
    """Success: the official command must create the required valid CSV."""
    ranked = _run_pipeline(tmp_path / "poc")
    assert len(ranked) == 96
    assert ranked["score"].is_monotonic_decreasing


def test_pipeline_is_reproducible_with_seed_42(tmp_path):
    """Reproducibility: two independent runs must match row for row."""
    first = _run_pipeline(tmp_path / "run_1")
    second = _run_pipeline(tmp_path / "run_2")
    pd.testing.assert_frame_equal(
        first.reset_index(drop=True),
        second.reset_index(drop=True),
        check_exact=True,
    )


def test_missing_metadata_columns_fail_clearly(tmp_path):
    """Edge: malformed images.csv must raise a clear validation error."""
    pd.DataFrame({"image_id": ["bad"], "path": ["missing.jpg"]}).to_csv(
        tmp_path / "images.csv", index=False
    )
    with pytest.raises(ValueError, match="thiếu cột"):
        q.load_inputs(tmp_path, verify_hash=False)


def test_empty_image_is_rejected():
    """Edge: a degenerate image must not silently produce a score."""
    with pytest.raises(ValueError, match="ảnh không hợp lệ"):
        q.image_features(np.zeros((0, 0, 3), dtype=np.uint8))
