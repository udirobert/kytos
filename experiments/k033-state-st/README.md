# k033 — trained signatures (Arc State ST on Replogle GWPS K562)

Status: **complete 2026-09-28 — negative gate result, no submission.** The
model trained to 40,000 steps; inference emitted learned deltas for the
covered panel + paired-eval targets; Gate B round 10 (`gate-20260928-01`)
scored `st_norm_dm` / `st_raw_dm` / `st_mix_dm` against the `dm_ref` drift
control. **All three ST arms lost to the reference.** Direction recovery
(PDS-space) on the measured hESC eval targets was the decisive failure: the
learned signature does not recover per-target direction better than (in fact
far worse than) the transplanted K562 consensus mean. See `AGENTS.md` §4
(`k033`) and `docs/vcc-two-track-strategy.md` for the strategy-level reading.

Contract of this run track:

- `tools/modal_k033_state_train.py` — prepare / fix / recompress / train /
  infer stages over the `kytos-vcc` Modal Volume
  (`/kytos-vol/k033-state/`). Dataset run `gwps-20260925-01`, model run
  `k033-st-gwps-k562-v1`.
- `state tx infer` emits per-target log1p HVG deltas
  (`/kytos-vol/k033-state/deltas/<run>-<ckpt>/st_deltas_hvg.npz`) for the
  272/300 covered panel targets plus the paired-hESC Gate B eval targets.
- `tools/modal_k033_delta_calibrate.py` — norm calibration + non-HVG
  backfill into the consumer artifact contract (`AGENTS.md` §4b).
- Gate B round 10 (`tools/modal_k025_eval2_gate.py`): arms
  `st_norm_dm` / `st_raw_dm` / `st_mix_dm` + `dm_ref` drift control.

Promotion rule (from the k028/k029 direction failures — see
`experiments/README.md`): a Gate B win must exceed the known local-vs-official
noise band, not just the reference, to earn a submission slot.

Exact losses, step rates, and arm metrics are embargoed until Oct 22:
`experiments/_embargoed/` (gitignored). This directory holds only receipts
(leaderboard result JSONs, entry IDs) once/if a variant is submitted.
