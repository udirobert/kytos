"""Kytos — submission script for the 2026 Virtual Cell Challenge.

Reads official challenge inputs and writes a cell-eval-ready prediction AnnData
(H5AD). This is the "submission harness first" pattern (NOTES §4 ratiocine):
lock the input→output contract early and test against a FROZEN local
`cell-eval run` long before the deadline. It must import CLEANLY with NO
third-party packages installed (degrade, don't crash).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# --------------------------------------------------------------------------- #
# Contract / validation
# --------------------------------------------------------------------------- #


@dataclass
class ChallengeInputs:
    """Everything a prediction needs in one deterministic object.

    - basal_state   : expression of cells expressing non-targeting guides
    - gene_targets  : CRISPRi knockdown target gene identifiers
    - gene_order    : canonical gene axis (cell-eval `-g expected_genelist`)

    Until the official schema is confirmed (Gate 3), these are read from
    conventional paths and validated loosely.
    """

    basal_path: Path
    targets_path: Path
    gene_order_path: Path
    normalization: str = "log1p"  # "counts" or "log1p" — Gate 3 decision
    # Verified against cell-eval 0.8.2 defaults (cell_eval/_cli/_const.py):
    # DEFAULT_PERT_COL="target_gene", DEFAULT_CTRL="non-targeting". A
    # `cell-eval run -ap pred.h5ad -ar real.h5ad` with zero flags must work.
    pert_col: str = "target_gene"
    control_value: str = "non-targeting"
    n_per_group: int = 100

    def validate(self) -> None:
        for p in (self.basal_path, self.targets_path, self.gene_order_path):
            if not Path(p).exists():
                raise FileNotFoundError(f"missing input: {p}")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


@dataclass
class PredictionResult:
    """A prediction ready to be written as AnnData + meta.json."""

    genes: List[str]
    groups: List[str]  # perturbation label per cell (obs[pert_col])
    values: "object"  # [n_cells, n_genes] 2D matrix
    meta: Dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Strategy hook: models share this one submission path
# --------------------------------------------------------------------------- #


class Strategy:
    """Interface for a prediction method. Phase 0 ships MeanShiftBaseline."""

    name: str = "base"

    def fit(self, inputs: ChallengeInputs) -> None:
        """Fit on whatever the strategy needs (Atlas 2025, Replogle, etc.)."""

    def predict(
        self, inputs: ChallengeInputs, gene_order: List[str], targets: List[str]
    ) -> PredictionResult:
        raise NotImplementedError


def _basal_mean_vector(inputs: ChallengeInputs, n_genes: int):
    """Per-gene basal mean, or a small positive constant fallback.

    The real Challenge basal is an H5AD of non-targeting-guide expression; when
    it is readable we predict its per-gene mean (the honest "no shift" floor).
    Until then (fixture placeholder) we fall back to a small positive constant.
    Never zeros: all-zero predictions become NaN under cell-eval's log1p
    normalization (log(0)) and crash the DE Mann-Whitney.
    """
    import numpy as np

    try:
        import anndata as ad

        basal = ad.read_h5ad(inputs.basal_path)
        if basal.shape[1] == n_genes:
            mean = np.asarray(basal.X.mean(axis=0), dtype=np.float32).ravel()
            if mean.size == n_genes and np.isfinite(mean).all():
                return mean
    except Exception:
        pass
    return np.full(n_genes, 1.0, dtype=np.float32)


class MeanShiftBaseline(Strategy):
    """Predict the mean shift from basal state, scaled by context similarity.

    Phase-0 floor baseline (NOTES §3.1): predict the basal mean for every group
    (control and perturbed alike) — the zero-shift floor that cell-eval can
    actually score. A real fit on Atlas 2025 replaces the identity. The
    contract (shape, schema, meta) is what we are locking down.
    """

    name = "mean-shift"

    def predict(
        self, inputs: ChallengeInputs, gene_order: List[str], targets: List[str]
    ) -> PredictionResult:
        import numpy as np

        n_genes = len(gene_order)
        n_cells = inputs.n_per_group
        # One control block + one block per knocked gene, n_cells each.
        # obs[pert_col] must label EVERY cell so cell-eval can compare control
        # vs perturbed groups — the group labels and X rows must line up
        # (regression fixed: groups was n_cells long while X had
        # n_cells * (1 + n_targets) rows, which AnnData would reject).
        groups = [inputs.control_value] * n_cells
        for target in targets:
            groups.extend([target] * n_cells)
        basal_mean = _basal_mean_vector(inputs, n_genes)
        values = np.repeat(basal_mean[np.newaxis, :], len(groups), axis=0)
        meta = {
            "strategy": self.name,
            "normalization": inputs.normalization,
            "n_per_group": n_cells,
            "n_targets": len(targets),
            "gene_order_sha": _file_hash(inputs.gene_order_path),
        }
        return PredictionResult(genes=gene_order, groups=groups, values=values, meta=meta)


# --------------------------------------------------------------------------- #
# AnnData assembly + H5AD write
# --------------------------------------------------------------------------- #


def cell_eval_h5ad(gene_order, groups, values, pert_col="target_gene", control="non-targeting"):
    """Build a cell-eval-ready AnnData (X + obs[pert_col] + var gene axis).

    Returns None if `anndata` isn't installed so the metadata contract can still
    be validated offline.
    """
    try:
        import anndata as ad
    except ImportError:
        return None
    import numpy as np

    adata = ad.AnnData(
        X=np.asarray(values, dtype=np.float32),
        obs={pert_col: np.asarray(groups, dtype=object)},
        var={"gene_name": np.asarray(gene_order, dtype=object)},
    )
    adata.var.index = list(gene_order)
    return adata


def _code_hash() -> str:
    try:
        import git

        return git.Repo(Path(__file__).resolve().parent.parent).head.object.hexsha[:12]
    except Exception:
        return "nohash"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kytos submission harness")
    p.add_argument("--basal", required=True, help="basal-state AnnData/H5AD path")
    p.add_argument("--targets", required=True, help="gene identifiers (CRISPRi targets)")
    p.add_argument("--gene-order", required=True, help="expected_genelist for var axis")
    p.add_argument("--out", required=True, help="output prediction .h5ad path")
    p.add_argument("--meta", default=None, help="optional meta.json path")
    p.add_argument("--normalization", default="log1p", choices=["counts", "log1p"])
    p.add_argument("--strategy", default="mean-shift", choices=["mean-shift"])
    p.add_argument(
        "--pert-col",
        default="target_gene",
        help="obs column for perturbation labels (cell-eval default: target_gene)",
    )
    p.add_argument(
        "--control-pert",
        default="non-targeting",
        help="control group label (cell-eval default: non-targeting)",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    inputs = ChallengeInputs(
        basal_path=Path(args.basal),
        targets_path=Path(args.targets),
        gene_order_path=Path(args.gene_order),
        normalization=args.normalization,
        pert_col=args.pert_col,
        control_value=args.control_pert,
    )
    inputs.validate()

    gene_order = [ln.strip() for ln in Path(args.gene_order).read_text().splitlines() if ln.strip()]
    targets = [ln.strip() for ln in Path(args.targets).read_text().splitlines() if ln.strip()]
    strategy = MeanShiftBaseline()
    result = strategy.predict(inputs, gene_order, targets)

    adata = cell_eval_h5ad(
        result.genes, result.groups, result.values, inputs.pert_col, inputs.control_value
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if adata is not None:
        adata.write_h5ad(args.out)
    else:
        # Degrade cleanly — write JSON placeholder so the harness contract is
        # testable before `anndata` is installed.
        out.write_text(json.dumps({"genes": gene_order}, indent=2) + "\n")

    meta = {
        "run_id": os.environ.get("KYTOS_RUN_ID", "unset"),
        "code": _code_hash(),
        **result.meta,
    }
    if args.meta:
        Path(args.meta).write_text(json.dumps(meta, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
