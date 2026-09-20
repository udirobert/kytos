"""Metadata-only gene-axis audit for the k022 source-alignment blocker.

The k022 pilot stopped in preflight because three Atlas validation labels
(HSPA14-1, TBCE-1, TMSB15B-1) are absent from the paired-transfer source
axis. The source axis is the 2026 ``gene_names.csv`` order (18,533); the
Atlas validation file carries 18,080 genes, so the two axes were never the
same namespace.

This tool compares a CONSUMER axis (labels the pipeline must cover, e.g.
``adata_Validation.h5ad`` var_names) against SOURCE axes (labels a producer
artifact supplies, e.g. ``paired_transfer_train.npz`` genes) plus optional
REFERENCE axes (informational, e.g. the 2026 panel order). For every
uncovered consumer label it reports machine-checkable evidence:

- whether the label looks like a ``var_names_make_unique`` artifact
  (``BASE-N`` where ``BASE`` also exists in the consumer axis);
- whether a plausible base label exists in each source axis;
- which ``var`` columns could carry stable feature IDs (Ensembl-style or
  explicitly named ``*_id`` columns), including the missing labels' rows.

It PROPOSES resolutions; it never applies them silently. An approved
mapping still has to be baked into a versioned, provenance-recorded
artifact before ``run_k022_pipeline_audit.load_source`` will accept it —
the run protocol forbids inferring equivalence from spelling alone.

CLI:
  python tools/audit_gene_axis.py \
    --consumer-h5ad /path/adata_Validation.h5ad \
    --source-npz /path/paired_transfer_train.npz \
    --reference-csv data/raw/vcc2026/gene_names.csv \
    --out axis_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]

SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<copy>\d+)$")
ID_NAME_RE = re.compile(r"(gene.?id|ensembl|feature.?id)", re.IGNORECASE)
ENSG_RE = re.compile(r"^ENS[A-Z0-9]*G\d+")


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if pd.isna(value):
        return None
    return str(value)


def axis_sha256(genes) -> str:
    return hashlib.sha256("\n".join(str(g) for g in genes).encode()).hexdigest()


def axis_summary(genes, name: str, role: str) -> dict:
    genes = [str(g) for g in genes]
    return {
        "name": name,
        "role": role,
        "n": len(genes),
        "n_unique": len(set(genes)),
        "unique": len(set(genes)) == len(genes),
        "sha256": axis_sha256(genes),
        "head": genes[:5],
        "tail": genes[-5:],
    }


def id_column_report(var: pd.DataFrame) -> dict:
    """Describe var columns that might carry stable feature identifiers."""
    report = {}
    for col in var.columns:
        series = var[col]
        as_str = series.astype(str)
        report[str(col)] = {
            "dtype": str(series.dtype),
            "n_unique": int(as_str.nunique()),
            "n_null": int(series.isna().sum()),
            "ensg_like_fraction": round(float(as_str.str.match(ENSG_RE).mean()), 4),
            "name_suggests_id": bool(ID_NAME_RE.search(str(col))),
        }
    return report


def _siblings(base: str, labels) -> list[str]:
    """Consumer labels sharing ``base`` (exact or BASE-N copies)."""
    out = []
    for g in labels:
        if g == base:
            out.append(g)
            continue
        m = SUFFIX_RE.match(g)
        if m and m.group("base") == base:
            out.append(g)
    return sorted(out)


def missing_label_report(
    label: str,
    consumer_labels,
    sources: dict[str, list[str]],
    var: pd.DataFrame | None,
    var_dump: bool,
) -> dict:
    """Evidence + candidate resolutions for one uncovered consumer label."""
    entry: dict = {"label": label, "candidates": [], "blockers": []}
    if var is not None and var_dump:
        rows = {}
        if label in var.index:
            row = var.loc[label]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            rows[label] = {str(k): _jsonable(v) for k, v in row.items()}
        entry["var_rows"] = rows

    consumer_set = set(consumer_labels)
    match = SUFFIX_RE.match(label)
    if match:
        base = match.group("base")
        copy_index = int(match.group("copy"))
        siblings = _siblings(base, consumer_labels)
        duplicated_in_consumer = base in consumer_set and len(siblings) > 1
        base_sources = [name for name, genes in sources.items() if base in set(genes)]
        entry["suffix_analysis"] = {
            "base": base,
            "copy_index": copy_index,
            "base_in_consumer_axis": base in consumer_set,
            "consumer_labels_sharing_base": siblings,
            "looks_like_make_unique_artifact": duplicated_in_consumer,
            "base_present_in_sources": base_sources,
        }
        if var is not None and var_dump:
            for sibling in siblings:
                if sibling != label and sibling in var.index:
                    row = var.loc[sibling]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    entry.setdefault("var_rows", {})[sibling] = {
                        str(k): _jsonable(v) for k, v in row.items()
                    }
        entry["has_mapping_candidate"] = bool(base_sources)
        for name in base_sources:
            candidate = {
                "rule": "suffix_base_map",
                "source": name,
                "source_label": base,
                "confidence": "requires_verification",
            }
            if duplicated_in_consumer:
                candidate["caveat"] = (
                    f"{base!r} also exists in the consumer axis, so {label!r} is a "
                    "distinct feature sharing a symbol. Mapping it to the base's "
                    "source column is only defensible if stable IDs prove the two "
                    "rows are the same feature; otherwise it fabricates an effect."
                )
            else:
                candidate["caveat"] = (
                    f"{base!r} is absent from the consumer axis, so {label!r} is "
                    "not a duplicate-artifact pattern; the -N suffix may be a "
                    "versioned alias. Defensible only with a recorded rule."
                )
            entry["candidates"].append(candidate)
        if not base_sources:
            entry["blockers"].append(f"base {base!r} absent from every source axis")
    else:
        entry["suffix_analysis"] = None
        entry["has_mapping_candidate"] = False
        entry["blockers"].append("no -N suffix pattern and no exact source match")

    entry["candidates"].append(
        {
            "rule": "drop_from_diagnostic_axis",
            "confidence": "defensible_if_recorded",
            "caveat": (
                "Subset the consumer axis to labels the source covers; the drop "
                "must be recorded in the run manifest. Diagnostics then describe "
                "the aligned axis, not the full Atlas axis."
            ),
        }
    )
    entry["candidates"].append(
        {
            "rule": "stable_id_map",
            "confidence": "requires_producer_metadata",
            "caveat": (
                "Regenerate or annotate the source artifact with stable feature "
                "IDs so the consumer row maps by identity, not spelling."
            ),
        }
    )
    return entry


def build_report(
    consumer_genes,
    sources: dict[str, list[str]],
    *,
    references: dict[str, list[str]] | None = None,
    consumer_var: pd.DataFrame | None = None,
    consumer_name: str = "consumer",
    var_dump: bool = True,
) -> dict:
    consumer = [str(g) for g in consumer_genes]
    sources = {name: [str(g) for g in genes] for name, genes in sources.items()}
    references = {name: [str(g) for g in genes] for name, genes in (references or {}).items()}
    axes = [axis_summary(consumer, consumer_name, "consumer")]
    axes += [axis_summary(g, n, "source") for n, g in sources.items()]
    axes += [axis_summary(g, n, "reference") for n, g in references.items()]
    if not all(a["unique"] for a in axes):
        raise ValueError("All axes must have unique labels; fix upstream before auditing")

    consumer_set = set(consumer)
    missing = {name: sorted(consumer_set - set(genes)) for name, genes in sources.items()}
    extra = {name: len(set(genes) - consumer_set) for name, genes in sources.items()}
    union_missing = sorted(set().union(*missing.values())) if missing else []
    reference_hits = {
        label: [n for n, genes in references.items() if label in set(genes)]
        for label in union_missing
    }

    resolutions = {
        label: missing_label_report(label, consumer, sources, consumer_var, var_dump)
        for label in union_missing
    }
    unmappable = [label for label, r in resolutions.items() if not r["has_mapping_candidate"]]
    decision = "aligned" if not union_missing else "review_required"
    return {
        "tool": "audit_gene_axis",
        "decision": decision,
        "labels_without_source_mapping": unmappable,
        "axes": axes,
        "missing_from_source": missing,
        "extra_in_source": extra,
        "missing_in_references": {
            label: hits for label, hits in reference_hits.items() if not hits
        },
        "resolutions": resolutions,
        "var_id_columns": id_column_report(consumer_var) if consumer_var is not None else None,
        "notes": [
            "Proposals are evidence, not approvals: no mapping is applied by this tool.",
            "drop_from_diagnostic_axis is always available but changes the axis the "
            "diagnostic describes; record the drop in the run manifest.",
            "suffix_base_map is only defensible when stable IDs prove the consumer "
            "row is the same feature as the base label's row.",
        ],
    }


def apply_axis_mapping(
    source_genes, consumer_genes, mapping: dict[str, str] | None = None
) -> list[int]:
    """Source column index for each consumer label under an approved mapping.

    Exact labels need no mapping entry; every other consumer label must
    appear in ``mapping`` pointing at an existing source label. Fails
    closed: any uncovered label raises ValueError naming the gap.
    """
    source = [str(g) for g in source_genes]
    consumer = [str(g) for g in consumer_genes]
    mapping = {str(k): str(v) for k, v in (mapping or {}).items()}
    if len(set(source)) != len(source) or len(set(consumer)) != len(consumer):
        raise ValueError("Axes must have unique labels")
    position = {g: i for i, g in enumerate(source)}
    bad_targets = [f"{c}->{s}" for c, s in mapping.items() if s not in position]
    if bad_targets:
        raise ValueError(f"Mapping points outside the source axis: {bad_targets}")
    missing = [g for g in consumer if g not in position and g not in mapping]
    if missing:
        raise ValueError(f"Consumer labels with no approved source column: {missing}")
    return [position[g] if g in position else position[mapping[g]] for g in consumer]


def _read_gene_lines(path: Path) -> list[str]:
    lines = [ln.strip() for ln in Path(path).read_text().splitlines()]
    return [ln for ln in lines if ln]


def _read_csv_axis(path: Path) -> list[str]:
    frame = pd.read_csv(path)
    return frame.iloc[:, 0].astype(str).tolist()


def _read_npz_genes(path: Path) -> list[str]:
    with np.load(path, allow_pickle=False) as data:
        if "genes" not in data:
            raise ValueError(f"{path} has no 'genes' array (keys: {list(data)})")
        return data["genes"].astype(str).tolist()


def _read_h5ad_axis(path: Path):
    import anndata as ad

    adata = ad.read_h5ad(path, backed="r")
    try:
        var = adata.var.copy()
        genes = adata.var_names.astype(str).tolist()
    finally:
        adata.file.close()
    return genes, var


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    consumer = parser.add_mutually_exclusive_group(required=True)
    consumer.add_argument("--consumer-h5ad", type=Path)
    consumer.add_argument("--consumer-genes", type=Path)
    parser.add_argument("--source-npz", type=Path, action="append", default=[])
    parser.add_argument("--source-genes", type=Path, action="append", default=[])
    parser.add_argument("--reference-csv", type=Path, action="append", default=[])
    parser.add_argument("--no-var-dump", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.source_npz and not args.source_genes:
        parser.error("At least one --source-npz or --source-genes is required")

    var = None
    if args.consumer_h5ad:
        consumer_genes, var = _read_h5ad_axis(args.consumer_h5ad)
        consumer_name = args.consumer_h5ad.name
    else:
        consumer_genes = _read_gene_lines(args.consumer_genes)
        consumer_name = args.consumer_genes.name

    sources = {path.name: _read_npz_genes(path) for path in args.source_npz} | {
        path.name: _read_gene_lines(path) for path in args.source_genes
    }
    references = {path.name: _read_csv_axis(path) for path in args.reference_csv}

    report = build_report(
        consumer_genes,
        sources,
        references=references,
        consumer_var=var,
        consumer_name=consumer_name,
        var_dump=not args.no_var_dump,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "decision": report["decision"],
                "missing": report["missing_from_source"],
            }
        )
    )
    return 0 if report["decision"] == "aligned" else 2


if __name__ == "__main__":
    raise SystemExit(main())
