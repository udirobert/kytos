"""Unit tests for k012 transfer classes and the LOO harness."""

import numpy as np
import pytest

from kytos.models.transfer import (
    BasalRatioTransfer,
    GlobalScalarTransfer,
    IdentityTransfer,
    LowRankTransfer,
    PerGeneShrunkTransfer,
    loo_evaluate,
)


def _rng(seed=0):
    return np.random.default_rng(seed)


def test_global_scalar_recovers_scale():
    rng = _rng()
    src = rng.normal(size=(10, 60))
    dst = 2.5 * src
    m = GlobalScalarTransfer().fit(src, dst)
    assert abs(m.s - 2.5) < 1e-9
    np.testing.assert_allclose(m.predict(src[0]), dst[0], rtol=1e-9)


def test_identity_passthrough():
    src = _rng().normal(size=(5, 30))
    m = IdentityTransfer().fit(src, -src)
    np.testing.assert_array_equal(m.predict(src[2]), src[2])


def test_per_gene_shrunk_bounded_by_evidence():
    rng = _rng(1)
    src = rng.normal(size=(12, 40))
    dst = 2.0 * src
    # one gene with no source signal gets raw scale 0 -> shrunk toward global
    src[:, 7] = 0.0
    dst[:, 7] = rng.normal(size=12)
    m = PerGeneShrunkTransfer().fit(src, dst)
    assert abs(m.s_gene[7] - m.s_global) < 1e-6
    # genes with strong evidence sit near the true per-gene scale
    assert abs(m.s_gene[0] - 2.0) < 0.2


def test_low_rank_recovers_latent_map():
    rng = _rng(2)
    p, g, r0 = 15, 50, 4
    a = rng.normal(size=(p, r0))
    b_src = rng.normal(size=(r0, g))
    b_dst = rng.normal(size=(r0, g))
    src = a @ b_src
    dst = (2.0 * a) @ b_dst  # latent coefficient map W0 = 2I, different output basis
    m = LowRankTransfer(rank=8, ridge=1e-6).fit(src, dst)
    err = np.linalg.norm(m.predict(src) - dst) / np.linalg.norm(dst)
    assert err < 0.05


def test_basal_ratio_finds_gamma():
    rng = _rng(3)
    g = 40
    src = rng.normal(size=(12, g))
    basal_src = rng.uniform(1.0, 3.0, size=g)
    basal_dst = basal_src * rng.uniform(1.0, 3.0, size=g)  # varying ratio per gene
    ratio = basal_dst / basal_src
    dst = 0.5 * src * ratio[None, :] ** 0.5
    m = BasalRatioTransfer().fit(src, dst, basal_src, basal_dst)
    assert m.gamma == 0.5
    assert abs(m.s - 0.5) < 0.05


def test_loo_evaluate_metrics_finite_and_scalar_moves_magnitude():
    rng = _rng(4)
    src = rng.normal(size=(10, 80))
    dst = 1.8 * src + 0.1 * rng.normal(size=(10, 80))
    r_scalar = loo_evaluate(GlobalScalarTransfer(), src, dst)
    r_ident = loo_evaluate(IdentityTransfer(), src, dst)
    for r in (r_scalar, r_ident):
        assert np.isfinite(r.mean_cosine)
        assert np.isfinite(r.de_pearson)
        assert len(r.per_target_cosine) == 10
    # cosine is scale-invariant — a pure scalar cannot change it
    assert r_scalar.mean_cosine == pytest.approx(r_ident.mean_cosine, abs=1e-9)
    # but magnitude calibration must move toward the true ratio ~1.8x vs 1.0x
    assert r_scalar.magnitude_ratio > r_ident.magnitude_ratio
