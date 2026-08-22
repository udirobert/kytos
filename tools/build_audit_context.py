"""Build audit/context.json from a run's prediction h5ad (run in .venv-science).

The audit rules are deterministic; their INPUT is per-gene shifts of the
prediction vs its own control cells. This script computes that context from
the actual prediction AnnData — no hand-entered values. Aggregate across
targets (rules are run-level, matching k001's context shape).

Pathways: a small curated set (extend as the audit matures). Only genes
present in the prediction's var axis are kept.

Usage:
    .venv-science/bin/python tools/build_audit_context.py \\
        --run experiments/k002-... --pred data/raw/vcc2025/pred_k002.h5ad
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from kytos.audit.rules import HOUSEKEEPING_GENES  # noqa: E402

CONTROL_LABEL = "non-targeting"
PERT_COL = "target_gene"
EPS = 1e-3  # stability for log2 ratios of near-zero lognorm means

# Curated pathway panels used by the coherence rule. Extend deliberately.
PATHWAYS = [
    {
        "name": "interferon_response",
        "genes": ["ISG15", "IFIT1", "MX1", "OAS1"],
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="experiment run directory")
    parser.add_argument("--pred", type=Path, required=True, help="prediction h5ad")
    args = parser.parse_args(argv)

    import anndata as ad
    import numpy as np

    pred = ad.read_h5ad(str(args.pred))
    genes = list(map(str, pred.var.index))
    gene_idx = {g: i for i, g in enumerate(genes)}
    labels = np.asarray(pred.obs[PERT_COL].astype(str))
    control_mask = labels == CONTROL_LABEL
    if not control_mask.any():
        print(f"error: no {CONTROL_LABEL!r} cells in prediction", file=sys.stderr)
        return 1

    import scipy.sparse as sp

    X = pred.X
    X = X.toarray() if sp.issparse(X) else np.asarray(X)
    ctrl = X[control_mask]
    pert = X[~control_mask]
    ctrl_mean = ctrl.mean(axis=0)
    pert_mean = pert.mean(axis=0)

    def log2_shift(gene: str) -> float:
        i = gene_idx[gene]
        return float(math.log2((pert_mean[i] + EPS) / (ctrl_mean[i] + EPS)))

    housekeeping = {g: log2_shift(g) for g in HOUSEKEEPING_GENES if g in gene_idx}
    pathways = []
    for pathway in PATHWAYS:
        present = [g for g in pathway["genes"] if g in gene_idx]
        if len(present) >= 2:
            pathways.append(
                {
                    "name": pathway["name"],
                    "genes": present,
                    "gene_shifts": {g: log2_shift(g) for g in present},
                }
            )

    context = {
        "run_id": args.run.name,
        "source": str(args.pred),
        "basis": (
            "prediction: mean over perturbed cells vs control cells (log2 ratio, lognorm space)"
        ),
        "housekeeping_shifts": housekeeping,
        "pathways": pathways,
    }
    out = args.run / "audit" / "context.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(context, indent=2) + "\n")
    print(f"[audit-context] wrote {out}")
    print(
        "[audit-context] housekeeping shifts: "
        + ", ".join(f"{g} {v:+.3f}" for g, v in housekeeping.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
