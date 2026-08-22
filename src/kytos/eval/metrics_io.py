"""Load committed cell-eval metric CSVs from an experiment run folder."""

from __future__ import annotations

import csv
from pathlib import Path


def load_metric_column_csv(path: Path, *, value_column: str) -> dict[str, float | None]:
    """Read ``metric,<value_column>`` CSV into a metric-name → float-or-None map.

    An empty cell means the metric was mathematically undefined for the run
    (e.g. pearson_delta when the prediction is constant — cell-eval emits
    NaN). We serialize that as null, not NaN, so facts.json stays valid JSON.
    """
    if not path.is_file():
        raise FileNotFoundError(path)

    out: dict[str, float | None] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"empty CSV: {path}")
        metric_key = reader.fieldnames[0]
        if value_column not in reader.fieldnames:
            raise ValueError(f"{path}: missing column {value_column!r}")
        for row in reader:
            name = row[metric_key].strip()
            if not name:
                continue
            raw = (row[value_column] or "").strip()
            out[name] = float(raw) if raw else None
    return out


def load_agg_metrics(metrics_dir: Path) -> dict[str, float]:
    return load_metric_column_csv(metrics_dir / "agg_results.csv", value_column="value")


def load_ceiling_metrics(metrics_dir: Path) -> dict[str, float]:
    return load_metric_column_csv(
        metrics_dir / "ceiling_results.csv",
        value_column="ceiling",
    )
