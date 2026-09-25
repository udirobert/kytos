"""Tests for dual-moment count generation (NB dispersion + soft threshold)."""

from __future__ import annotations

import hashlib

import numpy as np
from scipy import sparse

from kytos.models.dual_moment import build_prediction_dual_moment, fit_nb_size

GOLDEN_SHA = "6f09874ec9b6e2f483ec2b2801fb10113c20a4c437efa6574028bc11a2d88dda"


def _fixture(lam_scale: float = 1.0):
    import anndata as ad

    rng = np.random.default_rng(7)
    n_ctrl, n_gene, n_targ = 60, 80, 3
    lam = np.abs(rng.normal(2.0, 1.5, n_gene)) * lam_scale
    counts = sparse.csr_matrix(rng.poisson(lam[None, :], (n_ctrl, n_gene)).astype(np.int32))
    gene_names = [f"G{i:03d}" for i in range(n_gene)]
    ctrl = ad.AnnData(counts)
    ctrl.var_names = gene_names
    deltas = {f"T{i}": rng.normal(0, 0.4, n_gene).astype(np.float32) for i in range(n_targ)}
    return ctrl, deltas, gene_names


def _sha(x):
    parts = [x.data.tobytes(), x.indices.tobytes(), x.indptr.tobytes()]
    parts.append(np.asarray(x.shape, dtype=np.int64).tobytes())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _build(ctrl, deltas, genes, *, cells=8, seed=0, **kw):
    return build_prediction_dual_moment(
        ctrl, deltas, list(deltas), genes, cells_per_target=cells, seed=seed, **kw
    )


def test_default_path_parity_golden():
    ctrl, deltas, genes = _fixture()
    x = _build(ctrl, deltas, genes, amplitude=0.6, bulk_amplitude=0.3, pool_k=4)
    assert _sha(x) == GOLDEN_SHA


def test_nb_emission_pseudobulk_close():
    ctrl, deltas, genes = _fixture(lam_scale=50.0)
    det = _build(ctrl, deltas, genes)
    nb = _build(ctrl, deltas, genes, nb_dispersion=True)
    assert nb.shape == det.shape
    d, e = nb.toarray(), det.toarray()
    assert (d >= 0).all()
    corr = np.corrcoef(d.sum(0), e.sum(0))[0, 1]
    assert corr > 0.999


def test_nb_deterministic_per_seed():
    ctrl, deltas, genes = _fixture()
    a = _build(ctrl, deltas, genes, seed=1, nb_dispersion=True)
    b = _build(ctrl, deltas, genes, seed=1, nb_dispersion=True)
    c = _build(ctrl, deltas, genes, seed=2, nb_dispersion=True)
    assert (a.toarray() == b.toarray()).all()
    assert not (a.toarray() == c.toarray()).all()


def test_nb_restores_row_depth_variability():
    ctrl, deltas, genes = _fixture()
    nb = _build(ctrl, deltas, genes, nb_dispersion=True)
    det = _build(ctrl, deltas, genes)
    assert np.ptp(nb.toarray().sum(1)) >= np.ptp(det.toarray().sum(1))


def test_soft_threshold_below_thr_equals_zero_delta():
    ctrl, deltas, genes = _fixture()
    small = {k: (v * 0.01).astype(np.float32) for k, v in deltas.items()}
    zero = {k: np.zeros_like(v) for k, v in deltas.items()}
    a = _build(ctrl, small, genes, delta_soft_threshold=0.1)
    b = _build(ctrl, zero, genes)
    assert (a.toarray() == b.toarray()).all()


def test_mass_center_removes_uniform_shift():
    ctrl, deltas, genes = _fixture()
    uniform = {k: np.full_like(v, 0.1, dtype=np.float32) for k, v in deltas.items()}
    zero = {k: np.zeros_like(v) for k, v in deltas.items()}
    a = _build(ctrl, uniform, genes, delta_mass_center=True)
    b = _build(ctrl, zero, genes)
    assert np.array_equal(a.toarray(), b.toarray())


def test_fit_nb_size_recovers_overdispersion():
    rng = np.random.default_rng(3)
    n_cells, n_gene = 3000, 10
    mu = np.full(n_gene, 50.0)
    true_r = np.array([1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 2.0, 8.0, 40.0])
    p = true_r / (true_r + mu)
    counts = rng.negative_binomial(true_r, p, (n_cells, n_gene))
    est = fit_nb_size(sparse.csr_matrix(counts))
    assert np.allclose(np.log10(est), np.log10(true_r), atol=0.3)
