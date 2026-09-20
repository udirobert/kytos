from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

REPO = Path(__file__).resolve().parents[1]
for directory in (REPO / "src", REPO / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

k007 = importlib.import_module("run_k007_neighbor_prior")
dual_moment_counts = importlib.import_module("kytos.models.dual_moment").dual_moment_counts
ContextConditionedTransfer = importlib.import_module(
    "kytos.models.layer_a"
).ContextConditionedTransfer
HeterogeneousTransportSampler = importlib.import_module(
    "kytos.models.layer_b"
).HeterogeneousTransportSampler

CONTROL = "non-targeting"
PERT_COL = "target_gene"


def stable_seed(seed: int, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest()[:4], "little")


def split_rows(rows, n_fit: int, n_eval: int, seed: int):
    rows = np.asarray(rows, dtype=np.int64)
    if min(n_fit, n_eval) < 1 or len(np.unique(rows)) != len(rows):
        raise ValueError("Split requires positive sizes and unique row positions")
    if len(rows) < n_fit + n_eval:
        raise ValueError(f"Need {n_fit + n_eval} independent cells, have {len(rows)}")
    order = np.random.default_rng(seed).permutation(rows)
    return np.sort(order[:n_fit]), np.sort(order[n_fit : n_fit + n_eval])


def checked_counts(x):
    x = sparse.csr_matrix(x, dtype=np.float64)
    if not all(x.shape) or not np.isfinite(x.data).all():
        raise ValueError("Counts must be a nonempty finite matrix")
    if (x.data < 0).any() or (x.data != np.floor(x.data)).any():
        raise ValueError("Expected raw nonnegative integer counts, not normalized expression")
    depths = np.asarray(x.sum(axis=1)).ravel()
    if (depths <= 0).any():
        raise ValueError("Zero-depth cells must be resolved before this diagnostic")
    return x, depths


def moments(x):
    x, depths = checked_counts(x)
    probabilities = x.multiply((1.0 / depths)[:, None]).tocsr()
    mean_probability = np.asarray(probabilities.mean(axis=0)).ravel()
    bulk_probability = np.asarray(x.sum(axis=0)).ravel() / depths.sum()
    logged = x.copy()
    logged.data = np.log1p(logged.data)
    return {
        "mean_probability": mean_probability,
        "bulk_probability": bulk_probability,
        "mean_log1p_raw": np.asarray(logged.mean(axis=0)).ravel(),
    }


def diagnostics(pred, real, controls):
    pred, pred_depths = checked_counts(pred)
    real, real_depths = checked_counts(real)
    controls, _ = checked_counts(controls)
    if pred.shape[1] != real.shape[1] or pred.shape[1] != controls.shape[1]:
        raise ValueError("Diagnostic gene axes differ")
    p, r, c = moments(pred), moments(real), moments(controls)
    dp = p["mean_log1p_raw"] - c["mean_log1p_raw"]
    dr = r["mean_log1p_raw"] - c["mean_log1p_raw"]
    denominator = np.linalg.norm(dp) * np.linalg.norm(dr)
    p_probability = pred.multiply((1.0 / pred_depths)[:, None])
    r_probability = real.multiply((1.0 / real_depths)[:, None])
    p_var = np.maximum(
        np.asarray(p_probability.power(2).mean(axis=0)).ravel() - p["mean_probability"] ** 2, 0
    )
    r_var = np.maximum(
        np.asarray(r_probability.power(2).mean(axis=0)).ravel() - r["mean_probability"] ** 2, 0
    )
    return {
        "mean_probability_l1": float(np.abs(p["mean_probability"] - r["mean_probability"]).sum()),
        "bulk_probability_l1": float(np.abs(p["bulk_probability"] - r["bulk_probability"]).sum()),
        "raw_log_mean_mse": float(np.mean((p["mean_log1p_raw"] - r["mean_log1p_raw"]) ** 2)),
        "raw_log_delta_cosine": float(dp @ dr / denominator) if denominator > 0 else None,
        "probability_variance_ratio": float(p_var.sum() / r_var.sum()) if r_var.sum() > 0 else None,
        "pred_zero_fraction": float(1 - pred.count_nonzero() / np.prod(pred.shape)),
        "real_zero_fraction": float(1 - real.count_nonzero() / np.prod(real.shape)),
        "pred_median_depth": float(np.median(pred_depths)),
        "real_median_depth": float(np.median(real_depths)),
        "n_pred": pred.shape[0],
        "n_real": real.shape[0],
    }


def direct_moment_counts(control, desired, n_cells: int, pool_k: int, seed: int):
    raw, depths = checked_counts(control)
    if pool_k < 1 or len(depths) < n_cells * pool_k:
        raise ValueError("Not enough independent controls for template pooling")
    selected = np.random.default_rng(seed).choice(len(depths), n_cells * pool_k, replace=False)
    selected = selected[np.argsort(depths[selected], kind="stable")]
    template = raw[selected].toarray() / depths[selected, None]
    template = template.reshape(n_cells, pool_k, raw.shape[1]).mean(axis=1)
    emitted_depths = np.rint(depths[selected].reshape(n_cells, pool_k).mean(axis=1)).astype(
        np.int64
    )
    emitted_depths = np.clip(emitted_depths, 1, 1_000_000)
    return sparse.csr_matrix(
        dual_moment_counts(
            template,
            desired["mean_probability"],
            desired["bulk_probability"],
            depths=emitted_depths,
            seed=seed,
        )
    )


def transport_counts(control_path, genes, target, delta, n_cells, seed, scale):
    x, _, _ = k007.build_context_predictions(
        "audit",
        control_path,
        [target],
        genes,
        n_cells,
        np.random.default_rng(seed),
        {target: delta},
        {},
        ContextConditionedTransfer(),
        HeterogeneousTransportSampler(noise_scale=0.05, kd_std=2.0),
        library_cap="median",
        delta_scale=scale,
    )
    return x


def synthetic_data(seed: int):
    rng = np.random.default_rng(seed)
    genes = [f"G{i}" for i in range(12)]
    targets = genes[:3]
    blocks, labels = [], []
    for target, n_cells in [(CONTROL, 256), *[(t, 128) for t in targets]]:
        rates = rng.lognormal(0.0, 0.6, size=(n_cells, len(genes)))
        rates *= np.geomspace(0.1, 20.0, len(genes))
        if target != CONTROL:
            j = genes.index(target)
            rates[:, j] *= 0.4
            rates[:, (j + 4) % len(genes)] *= 1.4
        blocks.append(sparse.csr_matrix(rng.poisson(rates)))
        labels.extend([target] * n_cells)
    return ad.AnnData(
        sparse.vstack(blocks, format="csr"),
        obs=pd.DataFrame({PERT_COL: labels}, index=[f"cell_{i}" for i in range(len(labels))]),
        var=pd.DataFrame(index=genes),
    )


def load_source(path, genes):
    """Load a borrowed-delta source NPZ.

    Two accepted schemas: the original paired-transfer layout
    (``genes`` + ``paired_targets`` + ``delta_k562``) and the generic
    multi-lineage layout (``genes`` + ``targets`` + ``deltas``). Returns
    ``{target: delta_vector}`` subset to the consumer ``genes`` axis.
    """
    with np.load(path, allow_pickle=False) as data:
        source_genes = data["genes"].astype(str).tolist()
        if "paired_targets" in data.files and "delta_k562" in data.files:
            targets = data["paired_targets"].astype(str).tolist()
            deltas = data["delta_k562"]
        elif "targets" in data.files and "deltas" in data.files:
            targets = data["targets"].astype(str).tolist()
            deltas = data["deltas"]
        else:
            raise ValueError(
                "Source NPZ must carry (paired_targets, delta_k562) or (targets, deltas) keys"
            )
        if len(set(source_genes)) != len(source_genes) or len(set(targets)) != len(targets):
            raise ValueError("Source axes must be unique")
        if deltas.shape != (len(targets), len(source_genes)) or not np.isfinite(deltas).all():
            raise ValueError("Invalid source delta matrix")
        position = {g: i for i, g in enumerate(source_genes)}
        if not set(genes) <= set(source_genes):
            raise ValueError(
                "Source is missing evaluation genes; use an explicitly aligned artifact"
            )
        columns = [position[g] for g in genes]
        return {t: deltas[i, columns].astype(np.float32) for i, t in enumerate(targets)}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def axis_sha256(genes) -> str:
    return hashlib.sha256("\n".join(str(g) for g in genes).encode()).hexdigest()


def resolve_consumer_axis(genes, source_path, allow_drop):
    """Return (keep_positions, axis_resolution_or_None) for the consumer axis.

    Strict by default: uncovered labels return an empty keep list so the
    caller's strict ``load_source`` still fails closed. With
    ``allow_drop=True`` (the audited resolution for the Atlas-only
    duplicate-symbol labels, see experiments/k022-pipeline-audit/
    axis-20260921-01/axis_report.json), uncovered labels are dropped and the
    drop is returned for the manifest -- never silent.
    """
    with np.load(source_path, allow_pickle=False) as data:
        source_genes = set(data["genes"].astype(str).tolist())
    missing = sorted(set(genes) - source_genes)
    if not missing:
        return list(range(len(genes))), None
    if not allow_drop:
        return [], missing
    keep = [i for i, g in enumerate(genes) if g in source_genes]
    aligned = [genes[i] for i in keep]
    return keep, {
        "rule": "drop_from_diagnostic_axis",
        "dropped_labels": missing,
        "n_consumer_labels": len(genes),
        "n_aligned_labels": len(aligned),
        "aligned_axis_sha256": axis_sha256(aligned),
        "audit_report": "experiments/k022-pipeline-audit/axis-20260921-01/axis_report.json",
    }


def run_audit(
    real,
    out_dir,
    *,
    cells=32,
    controls=128,
    pool_k=4,
    seed=0,
    max_targets=0,
    source=None,
    sources=None,
    var_keep=None,
):
    if controls < cells * pool_k or pool_k < 1:
        raise ValueError("Fit-control count must cover cells * pool_k")
    if source is not None and sources is not None:
        raise ValueError("Pass either source or sources, not both")
    if source is not None:
        sources = {"default": source}
    vidx = var_keep if var_keep is not None else slice(None)
    genes = real.var_names[vidx].astype(str).tolist()
    if len(set(genes)) != len(genes) or not real.obs_names.is_unique:
        raise ValueError("Unique cell and gene identifiers are required")
    labels = real.obs[PERT_COL].astype(str).to_numpy()
    ctrl_fit, ctrl_eval = split_rows(
        np.flatnonzero(labels == CONTROL), controls, controls, stable_seed(seed, CONTROL)
    )
    targets = sorted(set(labels) - {CONTROL})
    if sources:
        covered = set().union(*[set(s) for s in sources.values()])
        targets = [t for t in targets if t in covered]
    if max_targets:
        targets = targets[:max_targets]
    splits, dropped = {}, {}
    for target in targets:
        rows = np.flatnonzero(labels == target)
        if len(rows) < 2 * cells:
            dropped[target] = {"available_cells": len(rows), "required_cells": 2 * cells}
        else:
            splits[target] = split_rows(rows, cells, cells, stable_seed(seed, target))
    if not splits:
        raise ValueError("No targets have enough independent fit/evaluation cells")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    control_fit = real[ctrl_fit, vidx].to_memory() if real.isbacked else real[ctrl_fit, vidx].copy()
    control_eval = real[ctrl_eval, vidx].X
    control_moments = moments(control_fit.X)
    summary = {
        "run_id": "k022-pipeline-audit",
        "diagnostics_only": True,
        "official_score_computed": False,
        "cells_per_target": cells,
        "fit_controls": controls,
        "eval_controls": controls,
        "pool_k": pool_k,
        "seed": seed,
        "transport": {
            "kd_std": 2.0,
            "noise_scale": 0.05,
            "library_cap": "median",
            "mean_correct": False,
        },
        "arm_definitions": {
            "observed_fit_split": (
                "Independent observed fit cells versus evaluation cells; not an upper bound."
            ),
            "measured_transport": ("Fit mean log1p(raw) minus fit-control mean; delta_scale=1.0."),
            "measured_direct_moments": (
                "Fit mean per-cell probabilities and separate pooled-count probabilities."
            ),
            "borrowed_transport_ds1p7[__name]": (
                "Optional borrowed source vector(s); historical application "
                "with delta_scale=1.7. Multiple --source-npz inputs produce "
                "one arm per named source on identical splits."
            ),
        },
        "limitations": [
            "Not a six-metric leaderboard surrogate and not a promotion gate.",
            "Measured effects are split-sample diagnostics, not deployable "
            "predictions or perfect oracles.",
            "Transport uses mean log1p(raw) shifts; dual-moment uses separate "
            "measured probability moments.",
            "No additive signature-versus-generator headroom decomposition is justified.",
            "Borrowed source effects, when provided, retain historical units "
            "without an implicit conversion.",
            "DE significance and official metric calibration require the "
            "subsequent external evaluation.",
        ],
        "dropped_targets": dropped,
        "targets": {},
    }
    cell_names = real.obs_names.astype(str).to_numpy()
    split_manifest = {
        "control_fit": cell_names[ctrl_fit].tolist(),
        "control_eval": cell_names[ctrl_eval].tolist(),
        "targets": {
            t: {"fit": cell_names[a].tolist(), "eval": cell_names[b].tolist()}
            for t, (a, b) in splits.items()
        },
    }
    (out_dir / "splits.json").write_text(json.dumps(split_manifest, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="kytos-k022-") as temp:
        control_path = Path(temp) / "controls.h5ad"
        control_fit.write_h5ad(control_path)
        zero = np.zeros(len(genes), dtype=np.float32)
        null_transport = transport_counts(control_path, genes, "null", zero, cells, seed, 1.0)
        null_moment = direct_moment_counts(control_fit.X, control_moments, cells, pool_k, seed)
        summary["null"] = {
            "champion_transport": diagnostics(null_transport, control_eval, control_eval),
            "direct_moments": diagnostics(null_moment, control_eval, control_eval),
        }
        for target, (fit_rows, eval_rows) in splits.items():
            fit, evaluation = real[fit_rows, vidx].X, real[eval_rows, vidx].X
            desired = moments(fit)
            delta = (desired["mean_log1p_raw"] - control_moments["mean_log1p_raw"]).astype(
                np.float32
            )
            target_seed = stable_seed(seed, f"generate:{target}")
            transport = transport_counts(
                control_path, genes, target, delta, cells, target_seed, 1.0
            )
            generated = direct_moment_counts(control_fit.X, desired, cells, pool_k, target_seed)
            achieved = moments(generated)
            arms = {
                "observed_fit_split": diagnostics(fit, evaluation, control_eval),
                "measured_transport": diagnostics(transport, evaluation, control_eval),
                "measured_direct_moments": diagnostics(generated, evaluation, control_eval),
            }
            if sources:
                for name, source_deltas in sources.items():
                    if target not in source_deltas:
                        continue
                    borrowed = transport_counts(
                        control_path,
                        genes,
                        target,
                        source_deltas[target],
                        cells,
                        target_seed,
                        1.7,
                    )
                    arm = (
                        "borrowed_transport_ds1p7"
                        if len(sources) == 1 and name == "default"
                        else f"borrowed_transport_ds1p7__{name}"
                    )
                    arms[arm] = diagnostics(borrowed, evaluation, control_eval)
            summary["targets"][target] = {
                "arms": arms,
                "moment_constraint_error": {
                    key: float(np.abs(achieved[key] - desired[key]).sum())
                    for key in ("mean_probability", "bulk_probability")
                },
            }
    summary["code_hashes"] = {
        str(path.relative_to(REPO)): sha256_file(path)
        for path in (
            Path(__file__),
            REPO / "tools/run_k007_neighbor_prior.py",
            REPO / "src/kytos/models/dual_moment.py",
            REPO / "src/kytos/models/layer_b.py",
        )
    }
    summary["split_sha256"] = sha256_file(out_dir / "splits.json")
    summary["versions"] = {
        name: importlib.metadata.version(name) for name in ("numpy", "scipy", "anndata", "pandas")
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--real-h5ad", type=Path)
    parser.add_argument(
        "--source-npz",
        action="append",
        default=[],
        metavar="[NAME=]PATH",
        help="borrowed-delta source NPZ; repeat to evaluate multiple sources "
        "on identical splits (each gets a borrowed_transport_ds1p7__NAME arm)",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cells", type=int, default=32)
    parser.add_argument("--controls", type=int, default=128)
    parser.add_argument("--pool-k", type=int, default=4)
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--allow-large-input", action="store_true")
    parser.add_argument(
        "--allow-axis-drop",
        action="store_true",
        help="record and drop consumer labels absent from --source-npz instead "
        "of failing closed (audited resolution for the Atlas-only "
        "duplicate-symbol labels)",
    )
    args = parser.parse_args(argv)
    if args.cells < 1 or args.controls < 1 or args.max_targets < 0:
        parser.error("Cell counts must be positive and max-targets nonnegative")
    if args.smoke and (args.source_npz or args.allow_large_input):
        parser.error("Smoke mode cannot consume real source artifacts")
    if (
        args.real_h5ad
        and args.real_h5ad.stat().st_size > 256 * 1024**2
        and not args.allow_large_input
    ):
        parser.error(
            "Large data requires external compute; --allow-large-input is an explicit opt-in"
        )
    real = synthetic_data(args.seed) if args.smoke else ad.read_h5ad(args.real_h5ad, backed="r")
    axis_resolution = None
    var_keep = None
    named = {}
    try:
        if args.source_npz:
            for entry in args.source_npz:
                name, _, path = str(entry).partition("=")
                if not path:
                    name, path = "default", name
                if name in named:
                    parser.error(f"Duplicate source name {name!r}")
                named[name] = Path(path)
            genes_all = real.var_names.astype(str).tolist()
            first = next(iter(named.values()))
            keep, axis_resolution = resolve_consumer_axis(genes_all, first, args.allow_axis_drop)
            if keep and len(keep) < len(genes_all):
                var_keep = keep
            aligned = [genes_all[i] for i in var_keep] if var_keep is not None else genes_all
            sources = {}
            with np.load(first, allow_pickle=False) as ref:
                ref_genes = ref["genes"].astype(str).tolist()
            for name, path in named.items():
                with np.load(path, allow_pickle=False) as probe:
                    if probe["genes"].astype(str).tolist() != ref_genes:
                        raise ValueError(
                            f"Source {name!r} has a different gene axis; all "
                            "sources in one run must share an axis"
                        )
                sources[name] = load_source(path, aligned)
        else:
            sources = None
        summary = run_audit(
            real,
            args.out_dir,
            cells=args.cells,
            controls=args.controls,
            pool_k=args.pool_k,
            seed=args.seed,
            max_targets=args.max_targets,
            sources=sources,
            var_keep=var_keep,
        )
        summary["synthetic"] = args.smoke
        if axis_resolution:
            summary["axis_resolution"] = axis_resolution
        hash_inputs = ([args.real_h5ad] if args.real_h5ad else []) + list(named.values())
        summary["input_hashes"] = {str(path): sha256_file(path) for path in hash_inputs}
        (args.out_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
        print(
            json.dumps(
                {
                    "summary": str(args.out_dir / "summary.json"),
                    "targets": len(summary["targets"]),
                    "diagnostics_only": True,
                }
            )
        )
    finally:
        if real.isbacked:
            real.file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
