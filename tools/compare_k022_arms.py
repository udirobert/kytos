"""Compare named borrowed-source arms across k022 audit summaries (k023).

Reads a multi-source summary.json (arms suffixed ``__<source>``) and prints a
per-target + aggregate comparison of ``raw_log_delta_cosine`` against the
``k562`` reference arm. Diagnostic output only -- not an official score.

Run:
  python tools/compare_k022_arms.py summary.json [--ref k562]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("summary", type=Path)
    p.add_argument("--ref", default="k562")
    args = p.parse_args(argv)

    s = json.loads(args.summary.read_text())
    targets = s["targets"]

    # Collect arm names; borrowed arms are suffixed __<source>.
    arm_names = set()
    for t in targets.values():
        arm_names.update(t["arms"])
    borrowed = sorted(a for a in arm_names if a.startswith("borrowed_transport"))
    shared = sorted(arm_names - set(borrowed))
    by_source = {}
    arm_label = {}
    for a in borrowed:
        src = a.split("__", 1)[1] if "__" in a else "default"
        by_source.setdefault(src, []).append(a)
        arm_label[a] = src

    ref_label = args.ref if args.ref in by_source else "default"
    rows = []
    for tname, t in sorted(targets.items()):
        row = {"target": tname}
        for a in shared:
            row[a] = t["arms"].get(a, {}).get("raw_log_delta_cosine")
        for a in borrowed:
            row[arm_label[a]] = t["arms"].get(a, {}).get("raw_log_delta_cosine")
        rows.append(row)

    srcs = list(by_source)
    header = ["target", *shared, *srcs]
    print("\t".join(header))
    for row in rows:
        cells = [f"{row[h]:.4f}" if row.get(h) is not None else "nan" for h in header[1:]]
        print("\t".join([row["target"], *cells]))

    print("\n=== medians over evaluated targets ===")
    for h in header[1:]:
        vals = [r[h] for r in rows if r.get(h) is not None]
        if vals:
            print(f"{h}\tmedian={np.median(vals):.4f}\tmean={np.mean(vals):.4f}\tn={len(vals)}")

    if ref_label in by_source:
        print(f"\n=== per-target delta vs {ref_label} (paired, both non-nan) ===")
        for src in srcs:
            if src == ref_label:
                continue
            diffs = [
                r[src] - r[ref_label]
                for r in rows
                if r.get(src) is not None and r.get(ref_label) is not None
            ]
            if diffs:
                wins = sum(d > 0 for d in diffs)
                print(
                    f"{src}\tmedian_delta={np.median(diffs):+.4f}\t"
                    f"mean_delta={np.mean(diffs):+.4f}\twins={wins}/{len(diffs)}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
