"""Score each 2026 context's basal profile against reference cell-line controls.

Decision gate for the lineage-matched-corpus move (Track 1 item 3 in
docs/vcc-two-track-strategy.md): before swapping prior sources, verify what
contexts A/B/C actually resemble.

References (control log1p means, mapped to the 18,533-gene context order):
  K562  — Replogle GWPS bulk (figshare 35774443)
  RPE1  — Replogle essential arm bulk (figshare 35775581)
  HESC  — 2025 Atlas validation controls (H1 hESC)
  JURKAT / HEPG2 — Nadig et al. 2024 essential screens
          (HF dataset bendidiihab/tx_evaluation, single-cell raw counts;
          control rows are gene_name ~ non-targeting)

For each context × reference: Pearson + Spearman on all mapped genes, and
Pearson on the top-2000 context-discriminative genes (largest variance
across A/B/C) — the former measures global resemblance, the latter whether
the match survives on genes that actually differ between contexts.

Run (see tools/modal_lineage_score.py):
  python tools/score_context_lineage.py \
    --raw-dir data/raw/vcc2026 \
    --atlas-src /root/atlas/adata_Validation.h5ad \
    --k562-src /root/replogle/K562_gwps_raw_bulk_01.h5ad \
    --rpe1-src /root/replogle/rpe1_raw_bulk_01.h5ad \
    --jurkat-src /root/nadig/nadig_2024_jurkat.h5ad \
    --hepg2-src /root/nadig/nadig_2024_hepg2.h5ad \
    --out experiments/k012-lineage-score/lineage_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import stats
from scipy import sparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from perturbation_priors import (  # noqa: E402
    build_atlas_deltas_with_control,
    build_replogle_deltas_with_control,
    log1p_sparse,
)


def generic_control_mean(path: Path, context_genes: list[str]) -> np.ndarray:
    """Control log1p mean mapped to context gene order, for arbitrary h5ad layouts.

    Finds the perturbation column by looking for a 'non-targeting'-like label,
    and gene symbols from var['gene_name'] or var.index.
    """
    print(f"[ref] loading {path.name} ...", flush=True)
    adata = ad.read_h5ad(str(path))
    print(f"[ref] {path.name}: {adata.shape[0]} obs x {adata.shape[1]} genes", flush=True)

    ctrl_mask = None
    for col in adata.obs.columns:
        vals = adata.obs[col].astype(str).str.lower()
        hits = vals.str.contains("non.targeting|nontargeting|control", regex=True)
        if hits.sum() > 0 and hits.mean() < 0.5:
            ctrl_mask = hits.to_numpy()
            print(f"[ref] controls via obs['{col}'] ({hits.sum()} rows)", flush=True)
            break
    if ctrl_mask is None:
        idx = adata.obs.index.astype(str).str.lower()
        hits = idx.str.contains("non.targeting|nontargeting", regex=True)
        if hits.sum() == 0:
            raise ValueError(f"{path.name}: cannot locate non-targeting controls")
        ctrl_mask = hits.to_numpy()
        print(f"[ref] controls via obs index ({hits.sum()} rows)", flush=True)

    if "gene_name" in adata.var.columns:
        ref_genes = adata.var["gene_name"].astype(str).tolist()
    else:
        ref_genes = adata.var.index.astype(str).tolist()
    ref_index = {g: i for i, g in enumerate(ref_genes)}

    X_log = log1p_sparse(adata.X)
    if sparse.issparse(X_log):
        ctrl_mean = np.asarray(X_log[ctrl_mask].mean(axis=0)).ravel()
    else:
        ctrl_mean = np.asarray(X_log)[ctrl_mask].mean(axis=0)

    mapped = np.zeros(len(context_genes), dtype=np.float32)
    covered = 0
    for i, g in enumerate(context_genes):
        j = ref_index.get(g)
        if j is not None:
            mapped[i] = ctrl_mean[j]
            covered += 1
    print(f"[ref] {path.name}: {covered}/{len(context_genes)} genes mapped", flush=True)
    return mapped


def context_basal_log1p(path: Path) -> np.ndarray:
    ctrl = ad.read_h5ad(str(path))
    X = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
    return np.asarray(log1p_sparse(X).mean(axis=0)).ravel().astype(np.float32)


def _pearson(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    a, b = a[mask], b[mask]
    if a.std() < 1e-8 or b.std() < 1e-8:
        return float("nan")
    return float(stats.pearsonr(a, b)[0])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--atlas-src", type=Path, required=True)
    ap.add_argument("--k562-src", type=Path, required=True)
    ap.add_argument("--rpe1-src", type=Path, default=None)
    ap.add_argument("--jurkat-src", type=Path, default=None)
    ap.add_argument("--hepg2-src", type=Path, default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "experiments" / "k012-lineage-score" / "lineage_report.json",
    )
    ap.add_argument("--contexts", type=str, default="A,B,C")
    ap.add_argument("--top-disc", type=int, default=2000)
    args = ap.parse_args(argv)

    t0 = time.time()
    gene_order = pd.read_csv(args.raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    refs: dict[str, np.ndarray] = {}
    _, refs["K562"] = build_replogle_deltas_with_control(str(args.k562_src), gene_order)
    _, refs["HESC"] = build_atlas_deltas_with_control(str(args.atlas_src), gene_order)
    for name, src in [
        ("RPE1", args.rpe1_src),
        ("JURKAT", args.jurkat_src),
        ("HEPG2", args.hepg2_src),
    ]:
        if src is not None and Path(src).exists():
            if name == "RPE1":
                _, refs[name] = build_replogle_deltas_with_control(str(src), gene_order)
            else:
                refs[name] = generic_control_mean(Path(src), gene_order)

    ctx_basal: dict[str, np.ndarray] = {}
    for ctx in contexts:
        print(f"[ctx {ctx}] loading ...", flush=True)
        ctx_basal[ctx] = context_basal_log1p(args.raw_dir / f"context_{ctx}.h5ad")

    ctx_mat = np.stack([ctx_basal[c] for c in contexts])
    disc = ctx_mat.std(axis=0).argsort()[::-1][: args.top_disc]
    disc_mask = np.zeros(len(gene_order), dtype=bool)
    disc_mask[disc] = True
    all_mask = np.ones(len(gene_order), dtype=bool)

    table: dict[str, dict[str, dict[str, float]]] = {}
    print(f"\n{'ctx':<4} {'ref':<8} {'pearson':>8} {'spear':>8} {'disc-p':>8}", flush=True)
    for ctx in contexts:
        table[ctx] = {}
        for ref_name, ref_vec in refs.items():
            both = (ctx_basal[ctx] > 0) & (ref_vec > 0)
            row = {
                "pearson_all": _pearson(ctx_basal[ctx], ref_vec, all_mask),
                "pearson_nonzero": _pearson(ctx_basal[ctx], ref_vec, both),
                "spearman_nonzero": float(stats.spearmanr(ctx_basal[ctx][both], ref_vec[both])[0])
                if both.sum() > 10
                else float("nan"),
                "pearson_discriminative": _pearson(ctx_basal[ctx], ref_vec, disc_mask),
            }
            table[ctx][ref_name] = row
            print(
                f"{ctx:<4} {ref_name:<8} {row['pearson_nonzero']:>8.3f} "
                f"{row['spearman_nonzero']:>8.3f} {row['pearson_discriminative']:>8.3f}",
                flush=True,
            )

    best = {
        ctx: max(table[ctx].items(), key=lambda kv: kv[1]["pearson_nonzero"]) for ctx in contexts
    }
    print("\nbest match per context:", {c: b[0] for c, b in best.items()}, flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "created": time.strftime("%Y-%m-%d"),
                "references": sorted(refs),
                "contexts": contexts,
                "top_discriminative_genes": args.top_disc,
                "table": table,
                "best_per_context": {c: b[0] for c, b in best.items()},
                "elapsed_s": round(time.time() - t0, 1),
            },
            indent=2,
        )
    )
    print(f"[out] wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
