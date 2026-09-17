"""Learned Layer A: context-conditioned signature transfer (k012).

Model classes mapping a source-context perturbation delta to a destination-
context delta, trained on the ~47 targets screened in both Replogle K562
GWPS and the 2025 Atlas (H1 hESC) — see docs/k012-layer-a-pipeline.md and
experiments/k012-paired-transfer/paired_transfer_train.npz.

Conventions: deltas are log1p mean-shift vectors over the 18,533-gene
context order. `fit` takes the paired training matrices; `predict` takes a
source delta (and optionally the destination context's basal log1p mean)
and returns the transferred delta.

CLI: python -m kytos.models.transfer <paired_transfer_train.npz>
runs leave-one-target-out evaluation of every class and writes
experiments/k012-transfer-loo/loo_report.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_EPS = 1e-8


class TransferModel:
    """Base: fit on paired (src, dst) deltas; predict dst-shaped deltas."""

    name: str = "base"

    def fit(
        self,
        delta_src: np.ndarray,
        delta_dst: np.ndarray,
        basal_src: np.ndarray | None = None,
        basal_dst: np.ndarray | None = None,
    ) -> "TransferModel":
        raise NotImplementedError

    def predict(self, delta_src: np.ndarray, basal_ctx: np.ndarray | None = None) -> np.ndarray:
        raise NotImplementedError


@dataclass
class IdentityTransfer(TransferModel):
    """Raw transplant — what the pipeline does today. Null baseline."""

    name: str = "identity"

    def fit(self, delta_src, delta_dst, basal_src=None, basal_dst=None):
        return self

    def predict(self, delta_src, basal_ctx=None):
        return np.asarray(delta_src, dtype=np.float64)


@dataclass
class GlobalScalarTransfer(TransferModel):
    """delta_dst ≈ s · delta_src, one pooled scalar. The k011 axis, measured."""

    name: str = "global_scalar"
    s: float = 1.0

    def fit(self, delta_src, delta_dst, basal_src=None, basal_dst=None):
        src, dst = np.asarray(delta_src, np.float64), np.asarray(delta_dst, np.float64)
        self.s = float((src * dst).sum() / ((src**2).sum() + _EPS))
        return self

    def predict(self, delta_src, basal_ctx=None):
        return self.s * np.asarray(delta_src, np.float64)


@dataclass
class PerGeneShrunkTransfer(TransferModel):
    """Per-gene scalar s_g shrunk toward the global scalar by gene-wise evidence."""

    name: str = "per_gene_shrunk"
    s_global: float = 1.0
    s_gene: np.ndarray = field(default_factory=lambda: np.empty(0))

    def fit(self, delta_src, delta_dst, basal_src=None, basal_dst=None):
        src, dst = np.asarray(delta_src, np.float64), np.asarray(delta_dst, np.float64)
        self.s_global = float((src * dst).sum() / ((src**2).sum() + _EPS))
        den = (src**2).sum(axis=0)
        s_raw = (src * dst).sum(axis=0) / (den + _EPS)
        tau = float(np.median(den))
        w = den / (den + tau + _EPS)
        self.s_gene = self.s_global + w * (s_raw - self.s_global)
        return self

    def predict(self, delta_src, basal_ctx=None):
        return self.s_gene * np.asarray(delta_src, np.float64)


@dataclass
class BasalRatioTransfer(TransferModel):
    """delta_dst(g) ≈ s · delta_src(g) · (basal_dst/basal_src)^gamma, clipped.

    Note: with a single destination context the ratio is a fixed per-gene
    vector — context-generalization can only be validated once a second dst
    corpus exists. Here it competes on its fixed-modulation merits.
    """

    name: str = "basal_ratio"
    gamma_grid: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    clip: tuple[float, float] = (0.25, 4.0)
    gamma: float = 0.0
    s: float = 1.0
    modulation: np.ndarray | None = None

    def fit(self, delta_src, delta_dst, basal_src=None, basal_dst=None):
        src, dst = np.asarray(delta_src, np.float64), np.asarray(delta_dst, np.float64)
        if basal_src is None or basal_dst is None:
            self.modulation = np.ones(src.shape[1])
            self.gamma = 0.0
            self.s = float((src * dst).sum() / ((src**2).sum() + _EPS))
            return self
        ratio = np.asarray(basal_dst, np.float64) / np.maximum(
            np.asarray(basal_src, np.float64), _EPS
        )
        ratio = np.clip(ratio, self.clip[0], self.clip[1])
        best = (np.inf, 0.0, np.ones(src.shape[1]), 1.0)
        for g in self.gamma_grid:
            m = ratio**g
            sm = src * m
            s = float((sm * dst).sum() / ((sm**2).sum() + _EPS))
            mse = float(((s * sm - dst) ** 2).mean())
            if mse < best[0]:
                best = (mse, g, m, s)
        _, self.gamma, self.modulation, self.s = best
        return self

    def predict(self, delta_src, basal_ctx=None):
        return self.s * self.modulation * np.asarray(delta_src, np.float64)


@dataclass
class LowRankTransfer(TransferModel):
    """Rank-r linear map: project src and dst onto their own PCA bases, ridge-fit
    an r×r map between latent spaces. delta_hat = ((x B_sᵀ) W) B_d — can rotate
    directions, not just rescale them."""

    name: str = "low_rank"
    rank: int = 16
    ridge: float = 1.0
    basis_src: np.ndarray | None = None
    basis_dst: np.ndarray | None = None
    W: np.ndarray | None = None

    def fit(self, delta_src, delta_dst, basal_src=None, basal_dst=None):
        src, dst = np.asarray(delta_src, np.float64), np.asarray(delta_dst, np.float64)
        r = min(self.rank, src.shape[0] - 1)
        _, _, vt_s = np.linalg.svd(src, full_matrices=False)
        _, _, vt_d = np.linalg.svd(dst, full_matrices=False)
        self.basis_src = vt_s[:r]
        self.basis_dst = vt_d[:r]
        src_c = src @ self.basis_src.T
        dst_c = dst @ self.basis_dst.T
        self.W = np.linalg.solve(src_c.T @ src_c + self.ridge * np.eye(r), src_c.T @ dst_c)
        return self

    def predict(self, delta_src, basal_ctx=None):
        src = np.asarray(delta_src, np.float64)
        return (src @ self.basis_src.T) @ self.W @ self.basis_dst


@dataclass
class LooMetrics:
    name: str
    mean_cosine: float
    median_cosine: float
    de_pearson: float
    sign_accuracy: float
    magnitude_ratio: float
    per_target_cosine: list[float]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < _EPS or nb < _EPS:
        return 0.0
    return float(a @ b / (na * nb))


def loo_evaluate(
    model: TransferModel,
    delta_src: np.ndarray,
    delta_dst: np.ndarray,
    basal_src: np.ndarray | None = None,
    basal_dst: np.ndarray | None = None,
    top_k: int = 200,
) -> LooMetrics:
    """Leave-one-target-out eval: fit on P-1 pairs, predict the held-out delta."""
    src, dst = np.asarray(delta_src, np.float64), np.asarray(delta_dst, np.float64)
    p = src.shape[0]
    cosines, pears, signs, mags = [], [], [], []
    for i in range(p):
        tr = np.ones(p, dtype=bool)
        tr[i] = False
        model.fit(src[tr], dst[tr], basal_src, basal_dst)
        hat = model.predict(src[i], basal_dst)
        cosines.append(_cosine(hat, dst[i]))
        k = min(top_k, src.shape[1])
        top = np.argsort(np.abs(dst[i]))[-k:]
        h, t = hat[top], dst[i][top]
        pears.append(float(np.corrcoef(h, t)[0, 1]) if t.std() > _EPS else 0.0)
        signs.append(float((np.sign(h) == np.sign(t)).mean()))
        mags.append(float(np.linalg.norm(hat) / (np.linalg.norm(dst[i]) + _EPS)))
    return LooMetrics(
        name=model.name,
        mean_cosine=float(np.mean(cosines)),
        median_cosine=float(np.median(cosines)),
        de_pearson=float(np.nanmean(pears)),
        sign_accuracy=float(np.mean(signs)),
        magnitude_ratio=float(np.mean(mags)),
        per_target_cosine=[round(c, 4) for c in cosines],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("npz", type=Path)
    ap.add_argument("--top-k", type=int, default=200)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument(
        "--report",
        type=Path,
        default=Path("experiments/k012-transfer-loo/loo_report.json"),
    )
    args = ap.parse_args(argv)

    d = np.load(args.npz, allow_pickle=False)
    delta_src, delta_dst = d["delta_k562"], d["delta_hesc"]
    basal_src, basal_dst = d["basal_k562_log1p"], d["basal_hesc_log1p"]
    paired = d["paired_targets"].tolist()

    models: list[TransferModel] = [
        IdentityTransfer(),
        GlobalScalarTransfer(),
        PerGeneShrunkTransfer(),
        BasalRatioTransfer(),
        LowRankTransfer(rank=args.rank),
    ]
    results = [
        loo_evaluate(m, delta_src, delta_dst, basal_src, basal_dst, args.top_k) for m in models
    ]

    print(f"{'model':<18} {'cos':>7} {'med':>7} {'deP':>7} {'sign':>7} {'mag':>7}")
    for r in results:
        print(
            f"{r.name:<18} {r.mean_cosine:>7.3f} {r.median_cosine:>7.3f} "
            f"{r.de_pearson:>7.3f} {r.sign_accuracy:>7.3f} {r.magnitude_ratio:>7.3f}"
        )

    # fitted global scalar on all pairs — the measured k011 analog
    g = GlobalScalarTransfer().fit(delta_src, delta_dst)
    print(f"\nfitted global scalar (all pairs): s = {g.s:.3f}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "npz": str(args.npz),
                "n_pairs": int(delta_src.shape[0]),
                "paired_targets": paired,
                "top_k": args.top_k,
                "rank": args.rank,
                "fitted_global_scalar": g.s,
                "results": [r.__dict__ for r in results],
            },
            indent=2,
        )
    )
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
