# k002 Retro — what worked, what didn't, what changes for k003

Status: **SHIPPED NOTES** · 2026-08-22 · Scope: the first real `cell-eval` run
(VCC 2025 validation through the submission harness). Companion to
[`run-protocol.md`](run-protocol.md) and the k002 entry in
[`experiments/README.md`](../experiments/README.md).

This is a build-in-public accountability doc: the run shipped an honest 0.0,
and the *process* behind it also gets audited. Read alongside the run page,
which renders the same philosophy on the Trust panel.

---

## What worked

- **Committed tooling from minute one.** `tools/prep_vcc2025_validation.py`,
  `tools/import_cell_eval.py`, `tools/build_audit_context.py` went into the
  repo, not scratch space. That's what made the 12.9GB local offload safe —
  everything re-derives, and provenance (source URL + sha256) lives in
  `experiments/k002-*/meta.json`, not in anyone's memory.
- **Validate the data before touching it.** Verified the h5ad held **raw
  counts** before applying `normalize_total(1e4) + log1p`. A wrong assumption
  here silently poisons every downstream number.
- **Subsample with disclosure.** Full-depth scoring was ~12h wall-clock on
  this machine; a seeded subsample (200 cells/pert + 3,000 controls, seed 0)
  took ~20 min. Because the caveat is in `meta.json` **and rendered on the
  run page**, it cost credibility nothing. The disclosure is the product.
- **Undefined-metric honesty end to end.** `NaN → empty CSV cell → JSON null
  → "undefined"/"not reported"` was fiddly, but it's now permanent
  capability: any future undefined metric renders correctly with zero new
  work. ceiling/floor asymmetries (0.0 vs 0.494; undefined vs 0.667) are more
  legible, not less.
- **The story landed.** Floor-zero with a clean audit is a *better* narrative
  than a mediocre mid-score: k001 fails the audit loudly while passing the
  metric; k002 passes the audit silently while failing the metric. Both
  lenses are load-bearing.

## What didn't work

- **Runtime extrapolation came too late.** The ~15 min/group (~12h) ETA only
  surfaced *after* the full run was already going; the first process died to
  an interruption mid-flight. Benchmark one perturbation group **first**, then
  choose subsample-vs-full.
- **Process discipline.** The first long job was tied to session lifecycle.
  Multi-hour local jobs are `nohup` + log file from the start, no exceptions.
- **Scratch scripts nearly lived nowhere.** Four orchestration shell scripts
  sat in gitignored `data/raw/` until the offload forced them into the HF
  bundle (`Papajams/kytos-k002-repro`). Reproducibility was rescued, not
  designed.
- **Blind trust in a cross-platform lockfile.** `uv.lock` was resolved where
  torch 2.13 had wheels; on this Mac — arm64 hardware but a **Rosetta x86_64
  venv** — every arm64 wheel was silently "invisible". First diagnostic
  should have been `sysconfig.get_platform()`, not package archaeology. Fixed
  via the darwin fork in `pyproject.toml` (`torch<2.13`) + arm64 venv
  recreation.
- **Two-agent tree hygiene.** The parallel committer swept uncommitted work
  into their commits twice. Worked out this time; the rule going forward is
  commit-early or stash.

## k003 changes (and the disk plan)

1. **Stream, don't stage.** Prep in a single pass: download → write
   `real_lognorm`/`basal` → delete the source *immediately*. Peak local
   footprint drops from ~12.9GB to ~5.5GB.
2. **Decide depth before compute.** k003 is full-depth in the scoring matrix:
   overnight, `nohup`-ed, launched only after confirming the disk budget
   (~13GB peak during prep; 46Gi free at time of writing is fine).
3. **Offload intermediates as they exist**, not as a cleanup step — the HF
   bundle pattern is proven.
4. **Benchmark the first 3 targets**, log the ETA into the pipeline log, walk
   away. No babysitting.
5. **Pin the lock in CI.** `uv lock --check` job so a linux-only resolution
   can never silently break macOS again.

See [`data/README.md`](../data/README.md#vcc2025-k002--restore-guide) for the
concrete restore path.
