# Final-phase runbook — Oct 22 drop → Nov 5 deadline

Status: **COMPLETE** · Updated 2026-10-22 (k043), closed 2026-11-20 ·
k043 stood as the final submission; winners announced Nov 19. Analysis:
[`vcc-postmortem.md`](vcc-postmortem.md). Next: [`kytos-roadmap.md`](kytos-roadmap.md).

The final test set is live: 3 new cell lines as contexts **D, E, F**, panel
`vcc2026-test-1`, **300 perturbations** (129 shared with the validation
panel, **171 new**), same 18,533-gene axis (byte-identical
`gene_names.csv`), 400 cells/pert/context (360k prediction cells).
Final submissions due **Nov 5 23:59 UTC** (server-exclusive bound
`2026-11-06T00:00:00Z`). **Scores are hidden** until Nov 19 and **only the
last submission counts for prizes** — every submission is blind and
self-replacing.

Preflight receipt: `experiments/_embargoed/final-preflight-20261022.json`.

## Ship recipe (frozen)

`consensus_w_ctr_sagr` deltas + champion dual-moment generator
(amplitude 1.0, bulk_amplitude 0.5, pool_k 4, bulk_delta space, seed 0,
400 cells/pert). This is `kytos-k040-sagr-dm`'s mechanism — best recorded
validation submission — re-targeted at the final panel. Sources are the
four WEIGHTED arms only: **k562, hct116, hek293t, cd4** (weights
2:1:1:1). Jurkat stays OUT — `consensus_delta` defaults unlisted sources
to weight 1.0, and k030 showed adding Jurkat regresses.

## Hard rules

- **CLI must be `vcc-cli==0.3.0`.** Older versions are refused by the
  server in the final phase. All Modal images pin it explicitly; the build
  job also asserts `vcc --version` before generating.
- **Never reuse A/B/C labels.** `obs["context"]` must be `D`/`E`/`F`. CLI
  0.3.0 reads contexts from the controls bundle's `manifest.json` beside
  `--perts`/`--genes`; `build_and_prep` still passes `--contexts D,E,F`
  explicitly as a belt-and-braces guard against a wrong-bundle accident.
- **The validation delta NPZ is NOT shippable.** `/kytos-vol/k035-machinery/
  variant_consensus_w_ctr_sagr.npz` is built on the OLD 343-target list —
  171/300 final targets are new. Rebuild via the subset+consensus path.
- **Preserve `manifest.json` beside the CSVs** wherever the final bundle is
  unpacked — the CLI uses it for context/panel checks.
- Do **not** run `vcc submit` without explicit approval. Run-id prefix for
  final-phase machinery: `k043-*`.
- All heavy stages run on **Modal** (prep needs ≥64 GB; the 31 GB VPS
  OOM'd on prep 2026-10-03, and the Mac is 8 GB).
- **One in-flight submission per team** plus a 2/day cap. Final scores are
  hidden, so `vcc status` will not show results — verify completion via
  `GET /api/cli/submissions/limits` (`spent`, `in_flight`) or
  `vcc status <entry-id>` for terminal state only.
- Preflight verified: `--contexts D,E,F`, 300 targets, 400 cells/pert,
  18,400 control cells/context, `target_gene`/`context`/`ntc_id` obs
  columns, csr float32 X, no layers.

## Where the genome-wide inputs live (Modal volume `kytos-vcc`)

| Input | Path |
|---|---|
| K562 (Replogle GWPS) | `/kytos-vol/k034-final-prep/k034-k562-all/deltas_k562.npz` |
| HCT116 (X-Atlas) | `/kytos-vol/k034-final-prep/k034-hct116-all/deltas_hct116.npz` |
| HEK293T (X-Atlas) | `/kytos-vol/k034-final-prep/k034-hek293t-all/deltas_hek293t.npz` |
| CD4 (Marson) | `/kytos-vol/k034-final-prep/k034-cd4-all/deltas_cd4.npz` |
| Jurkat (NOT in recipe) | `/kytos-vol/k034-final-prep/k034-jurkat-all/deltas_jurkat_{rest,stim}.npz` |
| Per-sample sagr stats | `/kytos-vol/k036-samplestats/{hct116,hek293t}_samplestats.npz` |

Note: the VPS-side mirrors of `k034-*-all/` are empty directories — the
artifacts only exist on the Modal volume. Do not conclude missing coverage
from the VPS listing.

## Checklist (commands in order)

```bash
# 1. Audit coverage — subset-ability of every source + sagr stats on the
#    FINAL 300-target panel. Writes /kytos-vol/k043-final/coverage_report.json.
modal run tools/modal_k043_final_sagr.py::audit_final_coverage

# 2. Assemble final-panel consensus_w_ctr_sagr (subset 4 genome-wide
#    sources -> v3 sagr builder). Writes
#    /kytos-vol/k043-final/machinery/variant_consensus_w_ctr_sagr.npz.
modal run tools/modal_k043_final_sagr.py::build_final_deltas

# 3. Generate + package (downloads controls-final in-container, builds
#    prediction.h5ad via the champion dual-moment path, runs vcc prep
#    0.3.0, persists .vcc + meta + sha256 to /kytos-vol/k043-final/).
modal run -d tools/modal_k043_final_sagr.py::build_and_prep
#    Optional first pass: --prep-dry-run validates without writing .vcc.

# 4. Submit — explicit user approval required; only the LAST submission
#    counts for prizes.
modal run -d tools/modal_k043_final_sagr.py::submit_from_volume
```

## Expected wall-clock (Modal)

| Stage | Time |
|---|---|
| Coverage audit | ~5 min |
| Subset + sagr consensus build | ~10-15 min |
| Dual-moment generation (300 × 400 × 3 ctx) | ~15-25 min |
| `vcc prep` packaging (≥64 GB RAM) | ~30-60 min |
| **Total critical path** | **~1.5 h** |

## Submission strategy under the hidden-score / last-one-counts rule

- Build and validate the baseline early; hold it on the volume.
- A challenger only replaces the baseline after a separate explicit
  decision with evidence (new-source coverage audit results, not
  parameter sweeps — axes closed by k039/k041/k042 stay closed).
- Submit the chosen artifact **before** the deadline with hours of margin;
  in-flight submissions at the deadline are still scored, late uploads are
  not.
