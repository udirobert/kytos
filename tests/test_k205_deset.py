"""Regression tests for tools/modal_k205_deset.py feature assembly.

The Modal tool file can't be imported locally (it builds a Modal image at
module scope), so these tests extract `_load_feats` / `_feature_matrix`
from the source via AST and exec them in a numpy namespace. That keeps the
test honest -- it exercises the shipped code, including the k205 indexing
bug fix (kd_eff broadcast to full gene axis before column slicing).
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[1] / "tools" / "modal_k205_deset.py"


def _load_impl():
    """Exec _load_feats, _feature_matrix and FEATURES from the tool source."""
    tree = ast.parse(SRC.read_text())
    wanted = {"_load_feats", "_feature_matrix"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted, "expected functions missing from tool"
    feats = next(
        n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "FEATURES"
    )
    ns = {}
    exec(compile(ast.Module(body=[feats], type_ignores=[]), "<f>", "exec"), ns)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<f>", "exec"), ns)
    return ns["FEATURES"], ns["_load_feats"], ns["_feature_matrix"]


def _fake_npz(n_t=3, n_g=10):
    rng = np.random.default_rng(0)
    return {
        "genes": np.array([f"G{i}" for i in range(n_g)]),
        "targets": np.array([f"T{i}" for i in range(n_t)]),
        "z_hat": rng.normal(0, 1, (n_t, n_g)).astype(np.float32),
        "se_z": rng.uniform(0.5, 1.5, (n_t, n_g)).astype(np.float32),
        "tau2_z": rng.uniform(0, 0.5, (n_t, n_g)).astype(np.float32),
        "i2_z": rng.uniform(0, 1, (n_t, n_g)).astype(np.float32),
        "votes_pos": rng.integers(0, 5, (n_t, n_g)).astype(np.float32),
        "votes_neg": rng.integers(0, 5, (n_t, n_g)).astype(np.float32),
        "n_sources": rng.integers(1, 6, (n_t, n_g)).astype(np.float32),
        "n_voting": rng.integers(0, 6, (n_t, n_g)).astype(np.float32),
        "lfc_hat": rng.normal(0, 0.3, (n_t, n_g)).astype(np.float32),
        "se_hat": rng.uniform(0.05, 0.3, (n_t, n_g)).astype(np.float32),
        "kd_eff": rng.uniform(0.5, 1.0, n_t).astype(np.float32),
    }


def test_feature_matrix_full_axis():
    FEATURES, load_feats, feat_mat = _load_impl()
    npz = _fake_npz()
    arr = load_feats(npz)
    kd = npz["kd_eff"].astype(np.float32)
    X = feat_mat(arr, 10, kd, np.array([0, 2]))
    assert X.shape == (2, 10, len(FEATURES))
    fi = FEATURES.index("kd_eff")
    np.testing.assert_allclose(X[0, :, fi], kd[0], atol=1e-6)
    np.testing.assert_allclose(X[1, :, fi], kd[2], atol=1e-6)
    zfi = FEATURES.index("z_hat")
    np.testing.assert_allclose(X[0, :, zfi], npz["z_hat"][0], atol=1e-6)


def test_feature_matrix_column_subset_kd_eff_broadcast():
    """Regression: kd_eff must broadcast over the FULL gene axis before
    slicing -- broadcasting to len(cols) first made full-axis gene indices
    out-of-bounds (IndexError at index 11501, axis size 900)."""
    FEATURES, load_feats, feat_mat = _load_impl()
    npz = _fake_npz(n_g=10)
    arr = load_feats(npz)
    kd = npz["kd_eff"].astype(np.float32)
    cols = np.array([7, 3, 9])  # arbitrary full-axis gene indices
    X = feat_mat(arr, 10, kd, np.array([1]), cols)
    assert X.shape == (1, 3, len(FEATURES))
    fi = FEATURES.index("kd_eff")
    np.testing.assert_allclose(X[0, :, fi], kd[1], atol=1e-6)
    zfi = FEATURES.index("z_hat")
    np.testing.assert_allclose(X[0, :, zfi], npz["z_hat"][1, cols], atol=1e-6)


def test_log1p_n_voting_feature():
    FEATURES, load_feats, feat_mat = _load_impl()
    npz = _fake_npz()
    orig = npz["n_voting"][0, 1]
    npz["n_voting"][0, 2] = np.nan
    arr = load_feats(npz)
    fi = FEATURES.index("log1p_n_voting")
    X = feat_mat(arr, 10, npz["kd_eff"], np.array([0]))
    assert np.isfinite(X[0, :, fi]).all()
    assert X[0, 2, fi] == 0.0  # NaN votes -> 0, per _load_feats contract
    np.testing.assert_allclose(X[0, 1, fi], np.log1p(orig), atol=1e-6)
