from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

cd = import_module("consensus_deltas")
audit = import_module("run_k022_pipeline_audit")
builder = import_module("build_consensus_deltas")


def test_map_gene_axis_exact_only():
    positions, missing = cd.map_gene_axis(["B", "A", "C-1"], ["A", "C", "B"])
    assert positions.tolist() == [1, -1, 0]
    assert missing == ["C"]


def test_deltas_from_group_sums_pooled_and_batch():
    # samples S1,S2; control + target T in each; control only in S3
    keys = [("S1", "CTRL"), ("S2", "CTRL"), ("S3", "CTRL"), ("S1", "T"), ("S2", "T")]
    sums = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],  # S1 ctrl, 2 cells -> mean 0
            [2.0, 2.0, 2.0, 2.0],  # S2 ctrl, 2 cells -> mean 1
            [0.0, 0.0, 0.0, 0.0],  # S3 ctrl
            [4.0, 0.0, 0.0, 0.0],  # S1 T, 1 cell -> mean 4
            [4.0, 4.0, 0.0, 0.0],  # S2 T, 1 cell -> mean (4,4,0,0)
        ]
    )
    cells = np.array([2, 2, 2, 1, 1])
    out = cd.deltas_from_group_sums(sums, cells, keys, "CTRL")
    # pooled ctrl mean = (0+2)/(4 cells in S1+S2+S3=6 cells) -> (2/6,2/6,...)
    pooled_ctrl = np.array([2, 2, 2, 2]) / 6.0
    pooled_T = np.array([8, 4, 0, 0]) / 2.0 - pooled_ctrl
    np.testing.assert_allclose(out["T"]["pooled"], pooled_T, rtol=1e-6)
    # batch: S1 term = (4,0,0,0)-(0..) ; S2 term = (4,4,0,0)-(1,1,1,1)
    s1 = np.array([4, 0, 0, 0]) - np.zeros(4)
    s2 = np.array([4, 4, 0, 0]) - np.ones(4)
    expected_batch = (s1 * 1 + s2 * 1) / 2  # equal cell weights
    np.testing.assert_allclose(out["T"]["batch"], expected_batch, rtol=1e-6)
    assert out["T"]["n_cells"] == 2 and out["T"]["n_samples"] == 2
    with pytest.raises(ValueError):
        cd.deltas_from_group_sums(sums, cells, keys, "MISSING")


def test_consensus_delta_agreement_scales_norm():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    c = np.array([0.0, 1.0, 0.0])
    cons, n = cd.consensus_delta({"x": a, "y": b})
    assert n == 2 and np.isclose(np.linalg.norm(cons), 1.0)
    cons, n = cd.consensus_delta({"x": a, "y": c})
    assert n == 2 and np.linalg.norm(cons) < 0.8  # disagreement shrinks norm
    cons, n = cd.consensus_delta({"x": None, "y": c})
    assert n == 1
    cons, n = cd.consensus_delta({"x": None, "y": None})
    assert cons is None and n == 0
    with pytest.raises(ValueError):
        cd.consensus_delta({"x": a}, {"x": -1.0})


def test_center_common_response_removes_shared_component():
    rng = np.random.default_rng(0)
    shared = rng.normal(size=8)
    m = np.stack([shared + rng.normal(0, 0.01, 8) for _ in range(6)])
    centered = cd.center_common_response(m)
    assert np.abs(np.median(centered, axis=0)).max() < 1e-10
    with pytest.raises(ValueError):
        cd.center_common_response(np.zeros((2, 8)))


def test_builder_emits_variants_and_consensus(tmp_path):
    genes = np.array(["A", "B", "C"])
    targets = np.array(["T1", "T2", "T3"])
    rng = np.random.default_rng(1)
    for name in ("k562", "hct116", "hek293t", "cd4"):
        delta = rng.normal(size=(3, 3)).astype(np.float32)
        np.savez_compressed(
            tmp_path / f"deltas_{name}.npz",
            genes=genes,
            targets=targets,
            delta=delta,
            covered=np.array([True, True, name != "cd4"]),  # cd4 misses T3
        )
    out = tmp_path / "out"
    assert builder.main(["--src-dir", str(tmp_path), "--out-dir", str(out)]) == 0
    manifest = json.loads((out / "build_manifest.json").read_text())
    expected = {
        "k562",
        "hct116",
        "hek293t",
        "cd4",
        "consensus_mean",
        "consensus_mean_ctr",
        "consensus_w",
        "consensus_w_ctr",
        "consensus_w_ncell",
        "consensus_w_ncell_ctr",
    }
    assert set(manifest["variants"]) == expected
    for name in expected:
        with np.load(out / f"variant_{name}.npz") as v:
            assert v["deltas"].shape == (3, 3)
            assert v["targets"].tolist() == targets.tolist()
            assert np.isfinite(v["deltas"]).all()


def test_builder_ncell_downweights_sparse_source(tmp_path):
    genes = np.array(["A", "B", "C"])
    targets = np.array(["T1", "T2", "T3"])
    rng = np.random.default_rng(2)
    k562_delta = np.vstack([[1.0, 0.0, 0.0], rng.normal(size=(2, 3))]).astype(np.float32)
    hct_delta = np.vstack([[0.0, 1.0, 0.0], rng.normal(size=(2, 3))]).astype(np.float32)
    np.savez_compressed(
        tmp_path / "deltas_k562.npz",
        genes=genes,
        targets=targets,
        delta=k562_delta,
        covered=np.array([True, True, True]),
    )
    np.savez_compressed(
        tmp_path / "deltas_hct116.npz",
        genes=genes,
        targets=targets,
        delta=hct_delta,
        covered=np.array([True, True, True]),
        n_cells=np.array([2, 200, 200]),  # T1 far below NCELL_FULL_WEIGHT
    )
    out = tmp_path / "out"
    assert builder.main(["--src-dir", str(tmp_path), "--out-dir", str(out)]) == 0
    with np.load(out / "variant_consensus_w.npz") as v:
        plain = v["deltas"][0]
    with np.load(out / "variant_consensus_w_ncell.npz") as v:
        ncell = v["deltas"][0]
    # With hct116 down-weighted ~0.02 on T1, the ncell consensus stays closer to
    # k562's direction (gene A) than the plain weighted consensus does.
    assert ncell[0] / np.linalg.norm(ncell) > plain[0] / np.linalg.norm(plain)


def test_multi_source_audit_runs_named_arms(tmp_path):
    real = audit.synthetic_data(3)
    real_path = tmp_path / "real.h5ad"
    real.write_h5ad(real_path)
    genes = [f"G{i}" for i in range(12)]
    for name in ("k562", "consensus"):
        np.savez(
            tmp_path / f"{name}.npz",
            genes=np.array(genes),
            targets=np.array(["G0"]),
            deltas=np.ones((1, 12), dtype=np.float32),
        )
    out = tmp_path / "out"
    assert (
        audit.main(
            [
                "--real-h5ad",
                str(real_path),
                "--source-npz",
                f"k562={tmp_path / 'k562.npz'}",
                "--source-npz",
                f"consensus={tmp_path / 'consensus.npz'}",
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
    arms = summary["targets"]["G0"]["arms"]
    assert "borrowed_transport_ds1p7__k562" in arms
    assert "borrowed_transport_ds1p7__consensus" in arms


def test_load_source_generic_schema(tmp_path):
    path = tmp_path / "s.npz"
    np.savez(
        path,
        genes=np.array(["B", "A"]),
        targets=np.array(["T"]),
        deltas=np.array([[2, 1]]),
    )
    np.testing.assert_array_equal(audit.load_source(path, ["A", "B"])["T"], [1, 2])
    bad = tmp_path / "bad.npz"
    np.savez(bad, genes=np.array(["A"]))
    with pytest.raises(ValueError, match="paired_targets"):
        audit.load_source(bad, ["A"])
