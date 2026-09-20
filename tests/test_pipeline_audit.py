from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

audit = import_module("run_k022_pipeline_audit")


def test_split_is_disjoint_reproducible_and_order_independent_by_label():
    rows = np.arange(100)
    seed = audit.stable_seed(4, "G0")
    fit, evaluation = audit.split_rows(rows, 20, 30, seed)
    assert len(fit) == 20 and len(evaluation) == 30
    assert not set(fit) & set(evaluation)
    audit.stable_seed(4, "OTHER")
    repeated = audit.split_rows(rows, 20, 30, audit.stable_seed(4, "G0"))
    np.testing.assert_array_equal(fit, repeated[0])
    np.testing.assert_array_equal(evaluation, repeated[1])
    with pytest.raises(ValueError):
        audit.split_rows(rows, 60, 60, seed)
    with pytest.raises(ValueError):
        audit.split_rows([0, 0, 1, 2], 1, 1, seed)


def test_moments_keep_cell_and_bulk_statistics_separate():
    x = np.array([[9, 1], [0, 100]])
    result = audit.moments(x)
    np.testing.assert_allclose(result["mean_probability"], [0.45, 0.55])
    np.testing.assert_allclose(result["bulk_probability"], [9 / 110, 101 / 110])
    np.testing.assert_allclose(result["mean_log1p_raw"], np.log1p(x).mean(axis=0))
    assert not np.allclose(result["mean_log1p_raw"], np.log1p(x.mean(axis=0)))


@pytest.mark.parametrize(
    "x", [np.array([[0, 0]]), np.array([[1, -1]]), np.array([[1, np.nan]]), np.array([[1, 0.5]])]
)
def test_counts_fail_closed(x):
    with pytest.raises(ValueError):
        audit.moments(x)


def test_direct_moments_preserve_integer_depth_and_null_mean():
    x = np.tile([12, 8, 20], (16, 1))
    result = audit.direct_moment_counts(x, audit.moments(x), 4, 4, 0).toarray()
    np.testing.assert_array_equal(result.sum(axis=1), [40] * 4)
    np.testing.assert_allclose(audit.moments(result)["mean_probability"], [0.3, 0.2, 0.5])
    assert (result == np.floor(result)).all()
    with pytest.raises(ValueError):
        audit.direct_moment_counts(x[:2], audit.moments(x), 4, 4, 0)


def test_identical_diagnostic_has_zero_error_without_fake_cosine():
    x = sparse.csr_matrix([[10, 2], [8, 4], [9, 1]])
    result = audit.diagnostics(x, x, x)
    assert result["mean_probability_l1"] == 0
    assert result["bulk_probability_l1"] == 0
    assert result["raw_log_mean_mse"] == 0
    assert result["raw_log_delta_cosine"] is None
    assert result["probability_variance_ratio"] == pytest.approx(1)


def test_smoke_writes_disjoint_splits_and_labels_no_score(tmp_path):
    out = tmp_path / "audit"
    assert (
        audit.main(
            [
                "--smoke",
                "--out-dir",
                str(out),
                "--cells",
                "8",
                "--controls",
                "32",
                "--max-targets",
                "1",
            ]
        )
        == 0
    )
    summary = json.loads((out / "summary.json").read_text())
    splits = json.loads((out / "splits.json").read_text())
    assert summary["synthetic"] is True
    assert summary["diagnostics_only"] is True
    assert summary["official_score_computed"] is False
    assert len(summary["targets"]) == 1
    assert set(summary["null"]) == {"champion_transport", "direct_moments"}
    assert not set(splits["control_fit"]) & set(splits["control_eval"])
    used = set(splits["control_fit"] + splits["control_eval"])
    for target in splits["targets"].values():
        assert not set(target["fit"]) & set(target["eval"])
        assert not used & set(target["fit"] + target["eval"])
    assert len(summary["split_sha256"]) == 64
    with pytest.raises(FileExistsError):
        audit.main(
            [
                "--smoke",
                "--out-dir",
                str(out),
                "--cells",
                "8",
                "--controls",
                "32",
                "--max-targets",
                "1",
            ]
        )


def test_backed_input_uses_same_split_and_results(tmp_path):
    real = audit.synthetic_data(7)
    path = tmp_path / "tiny.h5ad"
    real.write_h5ad(path)
    memory = audit.run_audit(real, tmp_path / "memory", cells=8, controls=32, max_targets=1)
    assert (
        audit.main(
            [
                "--real-h5ad",
                str(path),
                "--out-dir",
                str(tmp_path / "backed"),
                "--cells",
                "8",
                "--controls",
                "32",
                "--max-targets",
                "1",
            ]
        )
        == 0
    )
    backed = json.loads((tmp_path / "backed" / "summary.json").read_text())
    assert memory["targets"] == backed["targets"]
    assert memory["null"] == backed["null"]
    assert backed["synthetic"] is False


def test_source_alignment_rejects_missing_genes(tmp_path):
    path = tmp_path / "source.npz"
    np.savez(
        path,
        genes=np.array(["B", "A"]),
        paired_targets=np.array(["T"]),
        delta_k562=np.array([[2, 1]]),
    )
    np.testing.assert_array_equal(audit.load_source(path, ["A", "B"])["T"], [1, 2])
    with pytest.raises(ValueError, match="missing"):
        audit.load_source(path, ["A", "B", "C"])
