# gate-local-20260929-01 — k035 machinery round (local VPS port)

Run on snapflip-vultr (45.76.242.245, 4 vCPU / 31 GB + 32 GB swap added during
run) with `tools/run_k025_gate_local.py` — a local port of
`tools/modal_k025_eval2_gate.py::run_gate` (identical pipeline logic; paths
under /opt/kytos/data/vol, no volume.commit, cell-eval2 from pinned
/opt/kytos/.venv-eval2, --arms filter, --out-dir, merge-resume).

Bundle reused: `gate-20260921-01/bundle` fetched verbatim from the Modal
volume (same bundle_src as gate-20260928-02). Anchor + bundle digests in the
scored CSVs are identical to the Modal reference
(anchor 477d72a6…, bundle 53931b96…). Real subset: 93,697 cells / 18,080
genes / 47 eval targets / 38,176 controls — matches Modal.

## Parity verdict: OK (float-epsilon)

dm_ref reproduces gate-20260928-02 to ~15 significant digits:

| stat | Modal gate-20260928-02 | local | rel diff |
|---|---|---|---|
| mean pds_cosine | 0.8538390379278445 | 0.8538390379278445 | ~0 |
| mean expr_mse_unbiased_capped_norm | 0.9560311144846588 | 0.9560311144846585 | ~3e-16 |
| scored avg (from_replicate) | 0.23037339020210001 | 0.2303733902020999 | ~1e-16 |
| de_proxy median | 7954 (real 396) | 7954 (real 396) | exact |
| bulk_shift norm / cos | 0.50747 / 0.07409 | 0.50747 / 0.07409 | ~1e-8 |

## Per-arm scores (from_replicate avg)

| arm | avg | vs dm_ref |
|---|---|---|
| dm_ref | 0.230373 | — (drift control) |
| dm_agr | 0.245031 | +0.0147 |
| dm_agr_ctr | 0.239862 | +0.0095 |
| dm_ctr_agr | 0.240615 | +0.0102 |
| dm_selctr | 0.228038 | -0.0023 |
| dm_selctr_agr | 0.239801 | +0.0094 |

Raw agg means + from_baseline component scores + diagnostics are in
results.json / run_*_agg.csv / scored_*.csv in this dir. Total harness
elapsed for the 5 machinery arms: 5,347 s (~89 min; ~14–22 min per
cell-eval2 run); dm_ref arm earlier in the session.

Notes: dm_ref's cell-eval2 `run` was executed manually once (identical
pinned binary + flags) after the first in-harness attempt was OOM-killed at
~25.6 GB RSS against the parent's ~10 GB; its output was verified against
the Modal reference and copied into run_dm_ref/ — the harness then ran
`score` itself. A 24 GB swapfile (/swapfile2) was added on the VPS; the
harness also frees the real/control matrices before spawning cell-eval2.
