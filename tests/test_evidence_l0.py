from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

l0 = import_module("evidence_l0")


def test_bh_q_monotone_and_nan():
    p = np.array([0.001, 0.02, 0.5, np.nan])
    q = l0.bh_q(p)
    assert np.isnan(q[3])
    assert q[0] == pytest.approx(0.003)
    assert q[1] == pytest.approx(0.03)
    assert q[2] == pytest.approx(0.5)
    assert np.all(np.diff(q[:3]) >= -1e-12)


def test_welch_min_samples_gate():
    mean = np.array([[1.0, 1.0, 1.0]])
    e2 = np.array([[1.0, 1.0, 1.0]])
    n = np.array([[2, 3, 10]])
    se, p, z = l0.welch_from_moments(mean, e2, n)
    assert np.isnan(se[0, 0])  # n=2 < MIN_SAMPLES
    assert np.isfinite(se[0, 1]) and np.isfinite(p[0, 1])
    assert np.isfinite(z[0, 2])


def test_welch_zero_variance_all_same():
    # identical deltas across samples -> se=0, t=0 by construction
    mean = np.array([[2.0]])
    e2 = np.array([[4.0]])
    n = np.array([[5]])
    se, p, z = l0.welch_from_moments(mean, e2, n)
    assert se[0, 0] == 0.0
    assert p[0, 0] == pytest.approx(1.0)


def test_kd_eff_clip_and_missing():
    genes = np.array(["A", "B", "C"])
    targets = ["A", "C", "MISSING"]
    lfc = np.array([[-0.5, 0.0, 0.0], [0.0, 0.0, 0.3], [0.0, 0.0, 0.0]])
    eff = l0.kd_eff_from_self(targets, genes, lfc)
    assert eff[0] == pytest.approx(0.5)
    assert eff[1] == 0.0  # positive self-lfc clips to 0
    assert np.isnan(eff[2])


def test_group_delta_welch_paired():
    # 3 samples; target mean expr 1.0 below control in every sample
    rng = np.random.default_rng(0)
    G, T, S = 20, 2, 4
    sums = np.zeros((T + 1, S, G))
    cnts = np.zeros((T + 1, S), dtype=np.int64)
    for s in range(S):
        ctrl = 10.0 + rng.normal(0, 0.01, G)
        sums[T, s] = ctrl * 100
        cnts[T, s] = 100
        for t in range(T):
            shift = -1.0 if t == 0 else 0.0
            x = ctrl + shift + rng.normal(0, 0.01, G)
            sums[t, s] = x * 50
            cnts[t, s] = 50
    mask = np.ones(G, dtype=bool)
    mean, se, p, z, nv, cov = l0.group_delta_welch(sums, cnts, sums[T], cnts[T], T, G, mask)
    assert cov.all()
    assert np.all(nv == S)
    assert np.allclose(mean[0], -1.0, atol=0.05)
    assert np.allclose(mean[1], 0.0, atol=0.05)
    assert np.all(z[0] < -3)  # consistent shift across samples -> significant
    assert np.all(np.abs(z[1]) < 10)


def test_emit_store_roundtrip(tmp_path):
    genes = np.array(["G1", "G2"])
    targets = np.array(["T1"])
    T, G = 1, 2
    out = l0.emit_store(
        tmp_path / "store",
        genes,
        targets,
        np.array([True]),
        np.full((T, G), -1.0, np.float32),
        np.full((T, G), 0.1, np.float32),
        np.full((T, G), 0.01, np.float32),
        np.full((T, G), -5.0, np.float32),
        np.full((T, G), 5, np.int16),
        np.array([0.5], np.float32),
        {"dataset_id": "x", "se_kind": "test"},
    )
    d = np.load(tmp_path / "store" / "stats.npz")
    assert out["status"] == "ok"
    for key in ("genes", "targets", "covered", "lfc", "se", "p", "q", "z", "n_voting", "kd_eff"):
        assert key in d.files
    m = json.loads((tmp_path / "store" / "manifest.json").read_text())
    assert m["dataset_id"] == "x" and m["se_kind"] == "test"


def test_pick_columns():
    obs = pd.DataFrame(
        {
            "gem_group": ["a", "a", "b"],
            "gene": ["GENE1", "non-targeting", "GENE2"],
        }
    )
    col, ctrl = l0.pick_pert_column(obs)
    assert col == "gene" and ctrl == "non-targeting"
    bcol, codes = l0.pick_batch_column(obs)
    assert bcol == "gem_group"
    assert sorted(set(codes.tolist())) == [0, 1]
    bcol2, _ = l0.pick_batch_column(obs, forced="gem_group")
    assert bcol2 == "gem_group"
    none_col, none_codes = l0.pick_batch_column(pd.DataFrame({"x": [1, 2, 3]}))
    assert none_col is None and none_codes is None
