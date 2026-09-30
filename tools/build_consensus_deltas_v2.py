"""k035 machinery v2: variance-aware agreement gate + agr constants bracket.

Builds on ``tools/build_consensus_deltas.py`` (same source npz schema:
``genes``, ``targets``, ``delta`` [T,G], ``covered`` [T], optional
``delta_batch`` / ``n_cells``). Emits ONLY the new variants into an
existing variant directory (existing outputs are skipped, not overwritten,
unless --force):

- ``consensus_w_ctr_vagr`` ("variance-aware agreement"): the same
  ``consensus_w_ctr`` base (weighted consensus, common-response centered)
  gated by a per-(target,gene) agreement weight computed like ``_agr`` but
  with each source's contribution weighted by a per-target reliability
  ``rel_s[t] = min(1, n_cells_s[t] / 100)`` (the existing ``*_ncell``
  convention; sources without ``n_cells`` keep rel=1.0). The stored
  ``delta_batch`` arrays are POOLED batch-paired deltas, not per-sample
  matrices, so per-sample sign consistency is unavailable and the
  within-source term falls back to n_cells reliability only. Concretely::

      eff_s[t]   = w_s * rel_s[t]
      fused[t,g] = sum_s eff_s[t] * u_s[t,g]
      den[t,g]   = sum_s eff_s[t] * |u_s[t,g]|      (u_s = unit-normalized
                                                    source delta, 0 when
                                                    the target is uncovered)
      vagr[t,g]  = clip((|fused|/max(den,eps) - 0.30)/0.70, 0, 1)
      variant    = center_common_response(weighted_consensus) * vagr

  Effect: a low-cell-count source can still nominate a direction but votes
  proportionally less on whether sources agree, so noisy arms can neither
  rescue nor sink a gene's gate on their own.

- ``consensus_w_ctr_agr_loose`` / ``consensus_w_ctr_agr_tight`` /
  ``consensus_w_ctr_agr_xtight``: identical to ``consensus_w_ctr_agr`` but
  with clip constants (0.20, 0.60) / (0.40, 0.80) / (0.50, 0.90)
  bracketing/extending the confirmed (0.30, 0.70).

- ``consensus_w_ctr_vagr_tight``: the ``consensus_w_ctr_vagr``
  reliability-weighted agreement gate but with the tight clip constants
  (0.40, 0.80) instead of the standard (0.30, 0.70) -- the n_cells
  reliability term folded into the tight-constant gate.

Run:
  python tools/build_consensus_deltas_v2.py \
      --src-dir /opt/kytos/data/vol/k035-src \
      --out-dir /opt/kytos/data/vol/k035-machinery
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
    NCELL_FULL_WEIGHT,
    WEIGHTED,
    load_source_npz,
)

AGR_LOOSE = (0.20, 0.60)
AGR_TIGHT = (0.40, 0.80)
AGR_XTIGHT = (0.50, 0.90)


def _unit_rows(delta, covered):
    """(T,G) unit-normalized deltas, zeroed where uncovered."""
    d = delta.astype(np.float64)
    norms = np.linalg.norm(d, axis=1, keepdims=True)
    d = d / np.maximum(norms, 1e-12)
    return np.where(covered[:, None], d, 0.0)


def _agreement_gate(norm_src, weights, lo, hi, rel=None):
    """Per-(target,gene) clip gate; ``rel`` optionally scales source weights.

    ``norm_src``: {name: (T,G) unit deltas, zeros where uncovered}.
    ``weights``: {name: base weight}. ``rel``: {name: (T,) reliability} or
    None. Returns (T,G) float64 in [0,1].
    """
    fused = None
    den = None
    for name, u in norm_src.items():
        w = float(weights.get(name, 1.0))
        if rel is not None:
            w = w * np.asarray(rel[name], dtype=np.float64)[:, None]
        fused = u * w if fused is None else fused + u * w
        ad = np.abs(u) * w
        den = ad if den is None else den + ad
    return np.clip((np.abs(fused) / np.maximum(den, 1e-12) - lo) / (hi - lo), 0.0, 1.0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src-dir", type=Path, required=True)
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
    for name, s in sources.items():
        if s["genes"] != genes or s["targets"] != targets:
            raise ValueError(f"{name}: axis or target order differs from reference")

    T = len(targets)
    covered = {
        n: (s["covered"] if s["covered"] is not None else np.ones(T, bool))
        for n, s in sources.items()
    }

    # Reproduce the v1 weighted consensus exactly (same code path as
    # build_consensus_deltas.build_variants): weighted mean of unit-normalized
    # source deltas, amplitude restored to the target's K562 delta L2 norm.
    tpos = {t: i for i, t in enumerate(targets)}
    per_target = {
        n: {tpos[t]: s["delta"][tpos[t]] if covered[n][tpos[t]] else None for t in targets}
        for n, s in sources.items()
    }
    k562_norm = np.linalg.norm(sources["k562"]["delta"], axis=1)
    median_norm = float(np.median(k562_norm[k562_norm > 0])) if (k562_norm > 0).any() else 1.0
    weighted = np.zeros((T, len(genes)), dtype=np.float64)
    for i, t in enumerate(targets):
        cons, _ = cd.consensus_delta({n: per_target[n][i] for n in sources}, WEIGHTED)
        if cons is None:
            continue
        norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
        weighted[i] = cons * norm
    ctr = cd.center_common_response(weighted)

    norm_src = {n: _unit_rows(s["delta"], covered[n]) for n, s in sources.items()}

    # Per-target source reliability: min(1, n_cells/100); missing metadata
    # keeps full reliability (the *_ncell convention). Uncovered targets get
    # rel=0 so an absent source cannot vote (its u row is already zero, but
    # the explicit zero keeps the gate honest if a stray nonzero row slips
    # through).
    rel = {}
    for n, s in sources.items():
        if "n_cells" in s:
            r = np.minimum(1.0, np.asarray(s["n_cells"], dtype=np.float64) / NCELL_FULL_WEIGHT)
            rel[n] = np.where(covered[n], r, 0.0)
        else:
            rel[n] = np.where(covered[n], 1.0, 0.0)

    agr_loose = _agreement_gate(norm_src, WEIGHTED, *AGR_LOOSE)
    agr_tight = _agreement_gate(norm_src, WEIGHTED, *AGR_TIGHT)
    agr_xtight = _agreement_gate(norm_src, WEIGHTED, *AGR_XTIGHT)
    vagr = _agreement_gate(norm_src, WEIGHTED, AGR_LO, AGR_HI, rel=rel)
    vagr_tight = _agreement_gate(norm_src, WEIGHTED, *AGR_TIGHT, rel=rel)

    variants = {
        "consensus_w_ctr_agr_loose": (ctr * agr_loose).astype(np.float32),
        "consensus_w_ctr_agr_tight": (ctr * agr_tight).astype(np.float32),
        "consensus_w_ctr_agr_xtight": (ctr * agr_xtight).astype(np.float32),
        "consensus_w_ctr_vagr": (ctr * vagr).astype(np.float32),
        "consensus_w_ctr_vagr_tight": (ctr * vagr_tight).astype(np.float32),
    }

    # Self-check: recompute the confirmed consensus_w_ctr_agr and compare to
    # the on-disk v1 artifact when present (guards against drift in the base
    # consensus path between v1 and v2).
    agr_std = _agreement_gate(norm_src, WEIGHTED, AGR_LO, AGR_HI)
    check = (ctr * agr_std).astype(np.float32)
    ref_path = args.out_dir / "variant_consensus_w_ctr_agr.npz"
    verify = "skipped (no v1 artifact)"
    if ref_path.exists():
        with np.load(ref_path) as d:
            ref_mat = d["deltas"] if "deltas" in d.files else d["delta"]
        if ref_mat.shape == check.shape:
            max_abs = float(np.max(np.abs(ref_mat - check)))
            verify = f"max_abs_diff vs v1 consensus_w_ctr_agr: {max_abs:.3e}"
            if max_abs > 1e-4:
                raise ValueError(f"v2 base does not reproduce v1 ctr_agr ({verify})")
        else:
            verify = f"shape mismatch vs v1 artifact {ref_mat.shape} vs {check.shape}"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    skipped = []
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
        "builder": "tools/build_consensus_deltas_v2.py",
        "src_dir": str(args.src_dir),
        "sources": {
            n: {
                "targets_covered": int(covered[n].sum()),
                "has_batch_delta": "delta_batch" in s,
                "has_n_cells": "n_cells" in s,
            }
            for n, s in sources.items()
        },
        "variants": sorted(variants),
        "written_this_run": written,
        "skipped_existing": skipped,
        "weights": WEIGHTED,
        "ncell_full_weight": NCELL_FULL_WEIGHT,
        "agr_clip": {
            "loose": AGR_LOOSE,
            "standard": (AGR_LO, AGR_HI),
            "tight": AGR_TIGHT,
            "xtight": AGR_XTIGHT,
        },
        "semantics": [
            "base = consensus_w_ctr: weighted (k562 2 : others 1) mean of "
            "unit-normalized source deltas, norm restored to the target's "
            "K562 delta L2 norm, per-gene median across targets subtracted",
            "agr gates: clip((|fused|/sum|contrib| - lo)/(hi-lo), 0, 1) over "
            "unit-normalized weighted contributions",
            "vagr: same fraction with source contributions weighted by "
            "per-target reliability min(1, n_cells/100); sources without "
            "n_cells keep rel=1; uncovered targets rel=0",
            "vagr_tight: the vagr reliability-weighted gate evaluated at "
            "the tight clip constants (0.40, 0.80)",
            "delta_batch is a pooled batch-paired delta (not per-sample), so "
            "no per-sample sign-consistency term was computed -- n_cells "
            "reliability is the only within-source term",
            "verification: " + verify,
        ],
    }
    (args.out_dir / "build_manifest_v2.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "written": written,
                "skipped_existing": skipped,
                "verify": verify,
                "out": str(args.out_dir),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
