"""Import a real cell-eval run's outputs into a run's committed metrics/ dir.

cell-eval writes wide describe() tables: rows are statistics (count, mean,
std, min, quartiles, max), columns are metrics. The Observatory's contract
(docs/run-protocol.md) is long-form committed CSVs:

  experiments/<run>/metrics/agg_results.csv      → metric,value   (mean over perts)
  experiments/<run>/metrics/ceiling_results.csv  → metric,ceiling (Spearman-Brown corrected)

This adapter fails loudly on schema surprises rather than silently mapping
the wrong cell — the committed CSVs are cited link targets from the site.

Usage:
    python tools/import_cell_eval.py --run experiments/k002-... \\
        --eval-outdir data/raw/vcc2025/cell-eval-k002
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _read_wide_describe(path: Path) -> dict[str, float]:
    """cell-eval aggregate CSV → {metric: mean}.

    Two shapes exist: prediction aggregates are pl.describe() tables (first
    column 'statistic', per-metric columns); ceiling aggregates are a single
    row of Spearman-Brown-corrected means (metric columns, one data row).
    Raise on anything else rather than silently mapping the wrong cell — the
    committed CSVs are cited link targets from the site.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: empty CSV")
        rows = list(reader)
        metrics = list(reader.fieldnames)
    if metrics[0] == "statistic":
        mean_row = next((r for r in rows if r["statistic"] == "mean"), None)
        if mean_row is None:
            raise ValueError(f"{path}: no 'mean' statistic row")
        metrics = metrics[1:]
    elif len(rows) == 1:
        mean_row = rows[0]  # ceiling aggregate: single row of means
    else:
        raise ValueError(f"{path}: unknown aggregate shape ({len(rows)} rows)")
    out: dict[str, float] = {}
    for metric in metrics:
        raw = mean_row.get(metric)
        try:
            out[metric] = float(raw)
        except (TypeError, ValueError):
            out[metric] = float("nan")
    return out


def _write_long(path: Path, values: dict[str, float], column: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", column])
        for metric, value in values.items():
            # NaN (undefined metric, e.g. pearson of a constant prediction)
            # serializes as an empty cell → null downstream, valid JSON.
            writer.writerow([metric, f"{value:.6g}" if value == value else ""])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="experiment run directory")
    parser.add_argument(
        "--eval-outdir",
        type=Path,
        required=True,
        help="cell-eval -o directory (contains agg_results.csv / agg_ceiling_results.csv)",
    )
    args = parser.parse_args(argv)

    metrics = _read_wide_describe(args.eval_outdir / "agg_results.csv")
    metrics_dir = args.run / "metrics"
    _write_long(metrics_dir / "agg_results.csv", metrics, "value")
    print(f"[import] wrote {metrics_dir / 'agg_results.csv'} ({len(metrics)} metrics)")

    ceiling_path = args.eval_outdir / "agg_ceiling_results.csv"
    if ceiling_path.is_file():
        ceilings = _read_wide_describe(ceiling_path)
        _write_long(metrics_dir / "ceiling_results.csv", ceilings, "ceiling")
        print(f"[import] wrote {metrics_dir / 'ceiling_results.csv'} ({len(ceilings)} ceilings)")
    else:
        print(f"[import] WARNING: no ceiling results at {ceiling_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
