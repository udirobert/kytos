"""k040: per-sample sign-agreement (sagr) consensus variants.

Builds on ``tools/build_consensus_deltas.py`` / ``_v2.py`` (same source npz
schema: ``genes``, ``targets``, ``delta`` [T,G], ``covered`` [T], optional
``delta_batch`` / ``n_cells``). Consumes the k036 per-sample vote stores
(``<name>_samplestats.npz`` with ``pos_count``/``neg_count`` [T_stats,G] int16,
``n_samples_voting`` [T_stats] int32, ``targets``) for the two X-Atlas arms.

The k035/k038 cross-source *agreement gate* axis is closed (both tied the
champion with opposite pds<->reach reshuffles). The remaining slot-eligible
mechanism is per-sample sign agreement: for X-Atlas arms each (target,gene)
has 78-116 voting samples, so a gene's own replication evidence is far deeper
than the 4-source cross-agreement signal. ``sagr`` uses it as per-gene
shrinkage INSIDE each deep source, before consensus:

    agree[t,g] = max(pos_count, neg_count)          (majority-sign votes)
    cons[t,g]  = (agree[t,g] + KAPPA/2) / (n_voting[t] + KAPPA)
    delta'_s   = delta_s * cons_s                    (s in {hct116, hek293t})

cons is the Jeffreys-smoothed majority-sign fraction in [~0.5, ~1]: genes
whose sample-level deltas flip sign (agree/n -> 0.5) shrink toward half
weight, genes consistently signed keep ~1.0, and low-depth targets pull to
the 0.5 prior. Because ``consensus_delta`` unit-normalizes each source row
after shrinkage, only *relative* per-gene shrinkage matters: a source's mass
redistributes onto its confidently-signed genes. Sources without per-sample
stats (k562, cd4) keep cons=1 (the within-source term is unavailable, same
fallback convention as v2's n_cells reliability).

Variants emitted (into an existing variant dir; existing outputs skipped
unless --force):

- ``consensus_w_ctr_sagr``: weighted consensus over sagr-shrunk sources,
  K562-norm restored, common-response centered. Single-variable change vs
  the k027 champion (``consensus_w_ctr``) -- the probe candidate.

- ``consensus_w_ctr_sagr_agr``: the same sagr-shrunk consensus with the
  standard cross-source agreement gate (0.30/0.70) applied on top, i.e.
  ``consensus_w_ctr_agr`` recomputed on denoised sources. Local-gate
  screening only.

Run:
  python tools/build_consensus_deltas_v3.py \
      --src-dir /kytos-vol/k035-src \
      --stats-dir /kytos-vol/k036-samplestats \
      --out-dir /kytos-vol/k035-machinery
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consensus_deltas as cd
from build_consensus_deltas import (
    AGR_HI,
    AGR_LO,
    WEIGHTED,
    load_source_npz,
)
from build_consensus_deltas_v2 import _agreement_gate, _unit_rows

# Jeffreys-style prior strength for the majority-sign fraction: cons ->
# 0.5 as n_voting -> 0, exact agreement at n=100 still pulls to ~0.98.
KAPPA = 4.0


def load_sagr_weights(stats_dir: Path, name: str, targets: list[str], n_genes: int):
    """Per-(target,gene) sign-consistency shrinkage for source ``name``.

    Returns a (T,G) float64 array in [~0.5,~1], or None when no
    ``<name>_samplestats.npz`` exists (source keeps full weight). Targets
    absent from the stats store or with zero voting samples get the 0.5
    prior (neutral shrinkage).
    """
    path = stats_dir / f"{name}_samplestats.npz"
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as d:
        stat_targets = d["targets"].astype(str).tolist()
        stat_pos = {t: i for i, t in enumerate(stat_targets)}
        idx = np.array([stat_pos.get(t, -1) for t in targets], dtype=np.int64)
        present = idx >= 0
        n_voting = np.zeros(len(targets), dtype=np.float64)
        n_voting[present] = d["n_samples_voting"][idx[present]].astype(np.float64)
        pos = np.zeros((len(targets), n_genes), dtype=np.float64)
        neg = np.zeros((len(targets), n_genes), dtype=np.float64)
        pos[present] = d["pos_count"][idx[present]].astype(np.float64)
        neg[present] = d["neg_count"][idx[present]].astype(np.float64)
        if d["genes"].astype(str).tolist() != genes_ref:  # noqa: F821
            raise ValueError(f"{path}: gene axis differs from source deltas")
    agree = np.maximum(pos, neg)
    cons = (agree + KAPPA / 2.0) / np.maximum(n_voting[:, None] + KAPPA, 1e-12)
    return cons


genes_ref: list[str] = []


def main(argv=None) -> int:
    global genes_ref
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--stats-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--force", action="store_true", help="overwrite existing outputs")
    args = p.parse_args(argv)

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)
    if "k562" not in sources:
        raise ValueError("deltas_k562.npz is required as the reference source")

    ref = sources["k562"]
    genes, targets = ref["genes"], ref["targets"]
    genes_ref = genes
    for name, s in sources.items():
        if s["genes"] != genes or s["targets"] != targets:
            raise ValueError(f"{name}: axis or target order differs from reference")

    T, G = len(targets), len(genes)
    covered = {
        n: (s["covered"] if s["covered"] is not None else np.ones(T, bool))
        for n, s in sources.items()
    }

    # Per-sample sign-agreement shrinkage per source.
    sagr = {}
    sagr_report = {}
    for n, s in sources.items():
        cons = load_sagr_weights(args.stats_dir, n, targets, G)
        if cons is None:
            sagr[n] = None
            sagr_report[n] = {"has_samplestats": False}
            continue
        cons = np.where(covered[n][:, None], cons, 1.0)
        sagr[n] = cons
        c = cons[covered[n]]
        sagr_report[n] = {
            "has_samplestats": True,
            "kappa": KAPPA,
            "cons_median": float(np.median(c)),
            "cons_p10": float(np.quantile(c, 0.1)),
            "cons_p90": float(np.quantile(c, 0.9)),
        }

    # Reproduce the v1/v2 weighted-consensus path, but each source row is
    # sagr-shrunk before consensus_delta unit-normalizes it.
    tpos = {t: i for i, t in enumerate(targets)}
    per_target = {}
    for n, s in sources.items():
        d = s["delta"].astype(np.float64)
        if sagr[n] is not None:
            d = d * sagr[n]
        per_target[n] = {tpos[t]: d[tpos[t]] if covered[n][tpos[t]] else None for t in targets}

    k562_norm = np.linalg.norm(sources["k562"]["delta"], axis=1)
    median_norm = float(np.median(k562_norm[k562_norm > 0])) if (k562_norm > 0).any() else 1.0
    weighted = np.zeros((T, G), dtype=np.float64)
    for i, t in enumerate(targets):
        cons, _ = cd.consensus_delta({n: per_target[n][i] for n in sources}, WEIGHTED)
        if cons is None:
            continue
        norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
        weighted[i] = cons * norm
    ctr = cd.center_common_response(weighted)

    # Cross-source agreement gate recomputed on the SHRUNK unit sources:
    # the gate now measures agreement between the denoised directions.
    shrunk_delta = {}
    for n, s in sources.items():
        d = s["delta"].astype(np.float64)
        shrunk_delta[n] = d * sagr[n] if sagr[n] is not None else d
    norm_src = {n: _unit_rows(shrunk_delta[n], covered[n]) for n in sources}
    agr_std = _agreement_gate(norm_src, WEIGHTED, AGR_LO, AGR_HI)

    variants = {
        "consensus_w_ctr_sagr": ctr.astype(np.float32),
        "consensus_w_ctr_sagr_agr": (ctr * agr_std).astype(np.float32),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for name, matrix in variants.items():
        out_path = args.out_dir / f"variant_{name}.npz"
        if out_path.exists() and not args.force:
            skipped.append(out_path.name)
            continue
        np.savez_compressed(
            out_path,
            genes=np.asarray(genes),
            targets=np.asarray(targets),
            deltas=matrix,
        )
        written.append(out_path.name)

    manifest = {
        "builder": "tools/build_consensus_deltas_v3.py",
        "src_dir": str(args.src_dir),
        "stats_dir": str(args.stats_dir),
        "sagr": sagr_report,
        "variants": sorted(variants),
        "written_this_run": written,
        "skipped_existing": skipped,
        "weights": WEIGHTED,
        "agr_clip": {"standard": (AGR_LO, AGR_HI)},
        "semantics": [
            "sagr: cons[t,g] = (max(pos,neg) + k/2)/(n_voting + k), k=4; "
            "source delta rows multiplied by cons before the weighted "
            "consensus -- per-sample sign agreement acts as per-gene "
            "shrinkage inside each deep source",
            "sources without a samplestats npz keep cons=1 (no within-source term available)",
            "consensus_w_ctr_sagr: weighted consensus over shrunken "
            "sources, K562-norm restored, common-response centered -- "
            "single-variable change vs consensus_w_ctr",
            "consensus_w_ctr_sagr_agr: sagr consensus x standard "
            "cross-source agreement gate recomputed on shrunken sources",
        ],
    }
    (args.out_dir / "build_manifest_v3.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"written": written, "skipped_existing": skipped, "sagr": sagr_report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
