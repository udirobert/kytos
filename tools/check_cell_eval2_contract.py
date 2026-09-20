"""Pinned cell-eval2 ``vcc2026`` contract smoke (scorer validation gate).

Builds a tiny synthetic (prediction, real) h5ad pair, drives the
``cell-eval2`` CLI pinned to the inspected revision
(``5e64833518a6603a0301cbe28185d49c30f4a986``, project version 0.16.0), and
records the RESOLVED contract the pipeline actually runs under:

- emitted metric names versus the six scored ``vcc2026`` members;
- ``run_meta.json`` identity: version, config digest, resolved device,
  resolved DE backend, comparator, strict reference fingerprint;
- optionally the full competition path end to end on the fixture:
  ``baseline`` -> ``prep-real-bundle`` -> ``score --real-bundle``,
  which exercises the enrolment/metadata gates a real run must pass.

A pass proves the pinned package EXECUTES the contract on this machine.
It does not establish production equivalence: the fixture bundle is not
the live anchor bundle, and CPU-vs-production DE backend parity still
needs a recorded comparison (see
``experiments/k022-pipeline-audit/scorer_contract.json``).

Usage (inside .venv-eval2 or anywhere the pinned CLI is installed):
  python tools/check_cell_eval2_contract.py \
      --cell-eval2 .venv-eval2/bin/cell-eval2 \
      --python .venv-eval2/bin/python \
      --out experiments/k022-pipeline-audit/eval2_contract_smoke.json
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

EXPECTED_VCC2026 = [
    "pds_cosine",
    "expr_mse_unbiased_capped_norm",
    "de_wilcoxon_direction_fidelity_yield_raw",
    "de_wilcoxon_direction_reach_raw",
    "de_wilcoxon_sig_jaccard",
    "de_wilcoxon_lfc_nmae",
]

CONTROL = "non-targeting"
PERT_COL = "target"  # vcc2026 preset default; the Atlas uses target_gene


def make_fixture(workdir: Path, seed: int = 0) -> dict:
    """Write small synthetic real/pred h5ad files with integer counts.

    The prediction is an independent draw from the same generative rates —
    a 'good but noisy' predictor so every metric is defined. Target labels
    double as gene names so the panel-wide target-gene exclusion path is
    exercised.
    """
    import anndata as ad
    import pandas as pd
    from scipy import sparse

    rng = np.random.default_rng(seed)
    n_genes = 400
    targets = [f"G{i:03d}" for i in range(4)]
    # Cell counts are sized for the replicate anchor: the bundle's
    # de_wilcoxon_lfc_nmae gate needs split-half LFC NMAE < 1, which needs
    # ~75 cells per half to stay stable under Wilcoxon.
    per_target, n_control = 150, 600
    genes = [f"G{i:03d}" for i in range(n_genes)]
    base_rates = rng.lognormal(-1.0, 0.9, size=n_genes)

    # A shared block with OPPOSING directions across targets, so the
    # generic mean-response baseline is genuinely weak (its per-target
    # prediction cancels) and the scale denominators stay non-degenerate.
    shared = list(range(100, 115))

    def perturbed_rates(label: str, n: int) -> np.ndarray:
        rates = np.tile(base_rates, (n, 1)).astype(np.float64)
        if label != CONTROL:
            ti = targets.index(label)
            j = genes.index(label)
            rates[:, j] *= 0.15  # direct knockdown
            up = list(range(200 + ti * 15, 200 + ti * 15 + 12))
            down = list(range(300 + ti * 8, 300 + ti * 8 + 6))
            rates[:, up] *= 2.5
            rates[:, down] *= 0.4
            rates[:, shared] *= 3.0 if ti % 2 == 0 else 0.25
        return np.clip(rates, 1e-3, None)

    def build(seed_offset: int):
        draw_rng = np.random.default_rng(seed + seed_offset)
        blocks, labels = [], []
        for label, n in [(CONTROL, n_control), *[(t, per_target) for t in targets]]:
            blocks.append(sparse.csr_matrix(draw_rng.poisson(perturbed_rates(label, n))))
            labels.extend([label] * n)
        return ad.AnnData(
            sparse.vstack(blocks, format="csr").astype(np.int32),
            obs=pd.DataFrame({PERT_COL: labels}, index=[f"c{i}" for i in range(len(labels))]),
            var=pd.DataFrame(index=genes),
        )

    real, pred = build(0), build(1000)
    real_path, pred_path = workdir / "real.h5ad", workdir / "pred.h5ad"
    real.write_h5ad(real_path)
    pred.write_h5ad(pred_path)
    return {
        "real": str(real_path),
        "pred": str(pred_path),
        "n_genes": n_genes,
        "targets": targets,
        "cells_per_target": per_target,
        "control_cells": n_control,
        "pert_col": PERT_COL,
        "control_label": CONTROL,
    }


def run_step(name: str, argv: list[str], cwd: Path | None = None) -> dict:
    start = time.time()
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=1800)
    stderr_lines = proc.stderr.strip().splitlines()
    notable = [
        ln
        for ln in stderr_lines
        if any(
            marker in ln
            for marker in ("LOAD-BEARING", "falling back", "skipped", "omitted", "REFUS")
        )
    ]
    return {
        "step": name,
        "argv": argv,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - start, 2),
        "stdout_tail": proc.stdout.strip().splitlines()[-20:],
        "stderr_tail": stderr_lines[-20:],
        "notable_warnings": notable,
        "ok": proc.returncode == 0,
    }


def _csv_columns(path: Path) -> list[str]:
    with path.open() as handle:
        return next(csv.reader(handle))


def _csv_rows(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def parse_run_outdir(outdir: Path) -> dict:
    result: dict = {"files": sorted(p.name for p in outdir.iterdir())}
    meta_path = outdir / "run_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        result["run_meta"] = {
            key: meta.get(key)
            for key in (
                "cell_eval2_version",
                "config_digest",
                "comparator",
                "resolved_device",
                "resolved_de_backend",
                "source_fingerprint",
                "source_fingerprint_strict",
                "input_type_real_effective",
                "de_real_fingerprint",
            )
            if key in meta
        }
    if (outdir / "agg_results.csv").is_file():
        result["agg_metric_columns"] = _csv_columns(outdir / "agg_results.csv")[1:]
    if (outdir / "metric_aggregation.csv").is_file():
        result["metric_aggregation"] = _csv_rows(outdir / "metric_aggregation.csv")
    if (outdir / "results.csv").is_file():
        rows = _csv_rows(outdir / "results.csv")
        result["results_rows"] = len(rows)
        result["results_columns"] = list(rows[0]) if rows else []
    return result


def package_version(python: str) -> dict:
    code = (
        "import importlib.metadata, json;"
        "print(json.dumps({'cell_eval2': importlib.metadata.version('cell-eval2')}))"
    )
    proc = subprocess.run([python, "-c", code], capture_output=True, text=True)
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        out = {"cell_eval2": None, "error": proc.stderr.strip()[-500:]}
    out["python"] = python
    try:
        out["python_version"] = subprocess.run(
            [python, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        out["python_version"] = None
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cell-eval2", default="cell-eval2")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--anchor-splits", type=int, default=5)
    parser.add_argument("--no-full-path", action="store_true")
    args = parser.parse_args(argv)

    workdir_context = (
        tempfile.TemporaryDirectory(prefix="eval2-contract-") if args.workdir is None else None
    )
    workdir = Path(workdir_context.name) if workdir_context else args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "tool": "check_cell_eval2_contract",
        "pinned_revision": "5e64833518a6603a0301cbe28185d49c30f4a986",
        "expected_version": "0.16.0",
        "preset": "vcc2026",
        "expected_metrics": EXPECTED_VCC2026,
        "package": package_version(args.python),
        "fixture": make_fixture(workdir, args.seed),
        "steps": [],
        "production_equivalence": "not_established",
        "equivalence_caveats": [
            "Fixture bundle is locally built, not the live competition bundle; "
            "score enrolment mechanics are exercised, anchor values are not.",
            "resolved_de_backend records the CPU engine; parity with the "
            "production backend is a separate, unverified question.",
            "Metric VALUES on synthetic data carry no leaderboard meaning.",
        ],
    }

    run_dir = workdir / "run"
    step = run_step(
        "run",
        [
            args.cell_eval2,
            "run",
            "-ap",
            report["fixture"]["pred"],
            "-ar",
            report["fixture"]["real"],
            "--preset",
            "vcc2026",
            "-o",
            str(run_dir),
        ],
    )
    report["steps"].append(step)
    if step["ok"]:
        run_out = parse_run_outdir(run_dir)
        report["run"] = run_out
        emitted = set(run_out.get("agg_metric_columns", []))
        report["emitted_metrics"] = sorted(emitted)
        report["expected_metrics_present"] = sorted(emitted & set(EXPECTED_VCC2026))
        report["expected_metrics_missing"] = sorted(set(EXPECTED_VCC2026) - emitted)

    full_path_ok = None
    if not args.no_full_path and step["ok"]:
        baseline_dir = workdir / "baseline"
        bundle_dir = workdir / "bundle"
        scored_csv = workdir / "scored.csv"
        baseline_pred = baseline_dir / "baseline_pred.h5ad"
        steps = [
            run_step(
                "baseline",
                [
                    args.cell_eval2,
                    "baseline",
                    "-ar",
                    report["fixture"]["real"],
                    "--save-pred",
                    str(baseline_pred),
                    "--preset",
                    "vcc2026",
                    "-o",
                    str(baseline_dir),
                ],
            ),
        ]
        if steps[-1]["ok"]:
            steps.append(
                run_step(
                    "prep-real-bundle",
                    [
                        args.cell_eval2,
                        "prep-real-bundle",
                        "--real",
                        report["fixture"]["real"],
                        "--baseline",
                        str(baseline_pred),
                        "--preset",
                        "vcc2026",
                        "--anchor-splits",
                        str(args.anchor_splits),
                        "-o",
                        str(bundle_dir),
                    ],
                )
            )
        if steps[-1]["ok"]:
            steps.append(
                run_step(
                    "score --real-bundle",
                    [
                        args.cell_eval2,
                        "score",
                        "--user-agg",
                        str(run_dir / "agg_results.csv"),
                        "--real-bundle",
                        str(bundle_dir),
                        "-o",
                        str(scored_csv),
                    ],
                )
            )
        report["steps"].extend(steps)
        full_path_ok = all(s["ok"] for s in steps)
        if bundle_dir.is_dir():
            report["bundle_files"] = sorted(
                str(p.relative_to(bundle_dir)) for p in bundle_dir.rglob("*") if p.is_file()
            )
            for name in ("manifest.json", "anchor_meta.json"):
                meta = bundle_dir / name
                if meta.is_file():
                    report[f"bundle_{name}"] = json.loads(meta.read_text())
        if scored_csv.is_file():
            report["scored_columns"] = _csv_columns(scored_csv)
            report["scored_rows"] = _csv_rows(scored_csv)

    ok = all(s["ok"] for s in report["steps"])
    report["verdict"] = {
        "all_steps_ok": ok,
        "full_competition_path_ok": full_path_ok,
        "six_expected_metrics_emitted": not report.get("expected_metrics_missing", [1]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "verdict": report["verdict"],
                "resolved": report.get("run", {}).get("run_meta"),
            }
        )
    )
    if workdir_context is not None:
        workdir_context.cleanup()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
