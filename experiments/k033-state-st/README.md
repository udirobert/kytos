# k033 — trained signatures (Arc State ST on Replogle GWPS K562)

Status: **in flight 2026-09-26** — training + inference chained server-side on
Modal; no submission yet. See `AGENTS.md` §4 (`k033`) and
`docs/vcc-two-track-strategy.md` §Current state for the strategy.

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
