# Final-phase runbook — Oct 22 drop → Nov 5 deadline

Status: **ACTIVE** · Written 2026-09-28 (k034) · No embargoed numbers here.

On **Oct 22** the challenge releases 3 new cell lines as contexts **D, E, F**
(new control `.h5ad` files + a **new `pert_counts.csv`** — different
perturbation panel, size unknown) and possibly a new `gene_names.csv`.
Final submissions due **Nov 5 11:59 UTC**. **No scoring feedback** in that
window — every submission is blind; the daily submission cap still applies,
so do not waste slots.

## Hard rules

- **Never reuse A/B/C labels.** `obs["context"]` in the prediction must be
  `D`/`E`/`F`, and `vcc prep` must be passed `--contexts D,E,F` — the flag
  **defaults to `A,B,C`** and will fail validation silently late if omitted.
- The generator's `--contexts` flag must match the `context_<X>.h5ad`
  filenames in `--raw-dir` (`run_k027_dual_moment_submit.py` reads
  `context_{ctx}.h5ad` per context letter).
- **Check the new `gene_names.csv` first.** If the gene axis changed, all
  delta NPZs (panel-axis 18,533) must be rebuilt — the extracts are pinned
  to `data/raw/vcc2026/gene_names.csv`. If unchanged, proceed as below.
- Do **not** run `vcc submit` without explicit approval; keep `run-id`
  prefix `k034-*`/`k035-*` for final-phase machinery, `k0NN-*` for probes
  (Oct-03 probes ran as `k037-*`/`k038-*`).
- All heavy stages run on **Modal** — the local Mac cannot package a
  360k-cell prediction (~55 GB RAM for prep).
- **`vcc prep` does NOT fit the 31 GB VPS either.** Measured 2026-10-03 on the
  champion bundle: the streamed matrix build peaks ~2 GB and runs there fine,
  but `vcc prep` reached **>29 GB RSS + all 8 GB swap** before a guard killed
  it (swap thrash, no `.vcc` written). Matrix assembly = VPS-eligible,
  packaging = Modal-only. Keep prep in the ≥64 GB Modal job, as
  `tools/modal_k038_rmass_submit.py` does end-to-end.
- **One in-flight submission per team**, on top of the 2/day cap: the API
  rejects a second create while one is `scoring` (val-panel scoring took ~20
  min on 2026-10-03). On Oct 22, with no scoring feedback to release the lock,
  queue submits serially and confirm each upload completed before starting the
  next. `GET /api/cli/submissions/limits` (token on the VPS at
  `~/.config/vcc/credentials.json`) returns `{spent, limit, in_flight}` and is
  the only way to check state — there is no "list my submissions" command.
- If the new `pert_counts.csv` carries an `n_cells` column ≠ 400, that
  column wins inside `vcc prep` — pass matching `--cells-per-pert` to the
  generator (it uses one global count).

## Where the genome-wide deltas live (k034)

Pre-extracted, every target in each source, on the 18,533-gene panel axis,
schema identical to the k023 extracts (`genes`, `targets`, `delta`,
`covered`, `n_cells`; X-Atlas all-targets mode omits `delta_batch`):

| Source | Path (Modal volume `kytos-vcc`) | Coverage |
|---|---|---|
| K562 (Replogle GWPS) | `/kytos-vol/k034-final-prep/k034-k562-all/deltas_k562.npz` | 9,869 covered / 9,869 requested |
| HCT116 (X-Atlas) | `/kytos-vol/k034-final-prep/k034-hct116-all/deltas_hct116.npz` | 18,293 targets in source |
| HEK293T (X-Atlas) | `/kytos-vol/k034-final-prep/k034-hek293t-all/deltas_hek293t.npz` | 18,311 targets in source |
| CD4 (Marson) | `/kytos-vol/k034-final-prep/k034-cd4-all/deltas_cd4.npz` | 7,281 covered / 11,526 contrasts |
| Jurkat (GSE249595) | `/kytos-vol/k034-final-prep/k034-jurkat-all/deltas_jurkat_{rest,stim}.npz` | stim: 18,032 covered / 18,465 stems (median 59 cells); rest arm sparse (217) |

Check `manifest_*.json` next to each for exact counts and provenance.
Union coverage across K562 + X-Atlas is effectively genome-wide for gene
symbols present in the sources.

## Oct-22 checklist (commands in order)

```bash
# 0. Download the NEW controls bundle (id shown by `vcc datasets list`)
vcc datasets download <final-controls-id> -d /tmp/final   # on Modal or locally
unzip -q -o <bundle>.zip -d data/raw/vcc2026-final/        # context_D/E/F.h5ad,
                                                          # NEW pert_counts.csv

# 1. Subset genome-wide deltas to the NEW panel (minutes; no re-scan needed)
#    -> produce one deltas_<source>.npz per source on the new target order
python tools/subset_deltas_npz.py \
    --in deltas_k562.npz deltas_hct116.npz deltas_hek293t.npz \
         deltas_cd4.npz deltas_jurkat_stim.npz \
    --targets-file data/raw/vcc2026-final/pert_counts.csv \
    --out-dir <src-dir>
#    (pull the k034-final-prep npz files first with `modal volume get`;
#    ~1-2 GB each. If a source lacks a target, re-extract with
#    `--targets-file <new pert_counts.csv>` — PREFER server-side spawns over
#    `modal run -d`: detached local entrypoints were cancelled when the
#    local client died (k034 hit this). The extractor apps are deployed:
#      Function.from_name("kytos-k023-consensus-extract","extract_xatlas")
#          .spawn("hct116", "<run-id>", [<targets>], False, "k034-final-prep")
#      Function.from_name("kytos-k031-jurkat","run_all")
#          .spawn("<run-id>", [<targets>], False, "k034-final-prep"))
#    NOTE: Modal SIGTERM-preempted one hek293t scan at ~68%; all-source
#    X-Atlas scans now checkpoint (scanned offset + CSR accumulator) to the
#    volume every 4B rows, so a restarted input RESUMES — do not delete
#    checkpoint_scan.npz in a run dir until manifest_*.json exists.

# 2. Build consensus deltas (~2 min on 8 GB; needs k562 as reference)
python tools/build_consensus_deltas.py --src-dir <src-dir> --out-dir <variant-dir>
#    -> variant_consensus_w_ctr.npz (champion recipe)

# 3. Generate + prep on Modal — parameterized final-phase tool
#    (downloads the controls bundle in-container, builds prediction.h5ad,
#    runs vcc prep --contexts, persists .vcc to the volume)
modal run -d tools/modal_k034_final_submit.py::build_and_prep \
    --dataset-id <final-controls-id> \
    --deltas-vol /kytos-vol/<variant-dir>/variant_consensus_w_ctr.npz \
    --contexts D,E,F --tag k034-final-dm
#    Dry-run check first if unsure: add --prep-dry-run (validates only).

# 4. Prep is INSIDE build_and_prep; it already passes --contexts D,E,F.
#    Manual equivalent:
vcc prep -g data/raw/vcc2026-final/gene_names.csv \
    --perts data/raw/vcc2026-final/pert_counts.csv \
    --contexts D,E,F \
    -o prediction.prep.vcc prediction.h5ad
#    --dry-run first to confirm "targets: verified" for D/E/F.

# 5. Submit (with approval only)
modal run -d tools/modal_k034_final_submit.py::submit_from_volume \
    --tag k034-final-dm --model-name kytos-k034-final-dm
```

## Expected wall-clock (Modal)

| Stage | Time |
|---|---|
| Subset genome-wide npz → new panel | ~5 min |
| Re-extract with `--targets-file` (only if needed) | k562 ~30 s; cd4 ~20 min; hct116 ~30-60 min; hek293t ~1-2 h; jurkat ~1-2 h |
| Consensus build | ~2 min |
| Dual-moment generation (~300 targets × 400 × 3 ctx) | ~15-25 min |
| `vcc prep` packaging | ~30-60 min (needs ≥64 GB RAM) |
| **Total critical path** | **~1.5-2 h** if no re-extract; ≤4 h worst case |

## Rehearsal proof (2026-09-28)

`experiments/k034-final-rehearsal/` — mock 50-target panel, contexts
relabeled D/E/F: consensus → generation (189 s) → `vcc prep --contexts
D,E,F --dry-run` passed with `targets: verified`. See its `execution.json`.
