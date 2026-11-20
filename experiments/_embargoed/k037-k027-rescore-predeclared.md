# k037-k027-rescore — pre-declared probe predictions (written 2026-10-03, BEFORE submit)

## Why this probe exists

The champion (`kytos-k027-consensus-dm`, +0.1262) has **no recorded
per-component officials**: its entry was purged from the API before capture.
Every component verdict since (k028, k029, k030, k034, k035) has therefore been
read against *confounded* baselines — k034 (uncentered) and k030 (mean+Jurkat)
each differ from k027 in more than the variable being interpreted. This probe
supplies the missing unconfounded baseline: resubmit the champion recipe
byte-identically and capture its six components.

## Input parity (verified pre-submit)

**Method revised during the run, before any submit:** the champion's original
packaged bundle is still on the Modal volume —
`/kytos-vol/k027-consensus-dm/prediction.prep.vcc`, 3.7 GiB, timestamped
2026-09-22T13:56Z (meta.json of that run: `created_at 13:53:10Z`). Submitting
that artifact is strictly better than rebuilding: input is byte-identical by
construction, so score movement is attributable entirely to scorer/panel
drift, not to build nondeterminism.

The rebuild was completed first anyway and independently confirms determinism:

| check | k027 receipt | VPS rebuild |
|---|---|---|
| deltas sha256 | `336f2cbc1d01…` | `/opt/kytos/data/vol/k023-variants/variant_consensus_w_ctr.npz` = `336f2cbc1d01…` ✓ |
| nnz | 2434201087 | 2434201087 ✓ (digit-for-digit) |
| total_cells / n_targets / contexts / dispatch.real / uncovered | 360000 / 300 / A,B,C / 900 / [] | identical ✓ |
| generator | amp 1.0, bulk 0.5, pool_k 4, bulk_delta, seed 0 | identical ✓ |

Infra finding: the streamed builder (`tools/run_k035_streamed_submit.py`) made
the full panel on the 4 vCPU/31 GB VPS in **830 s at ~2 GB peak** — but
`vcc prep` itself peaked **>29 GB** there and was aborted by guard (swap: 8 GB
file fully consumed). So §4's "VPS replaces Modal for CPU work" holds up to
matrix assembly and stops at packaging; prep stays a Modal job.

- submitter: `tools/modal_k037_k027_rescore_submit.py` (Modal CPU, `--wait`)
- model name `kytos-k037-k027-rescore` — distinct from the champion entry so
  the receipts are separable

## Declared predictions

| component | prediction | basis |
|---|---|---|
| **score_avg** | **+0.1212 to +0.1312** (±0.005 of +0.1262) | identical matrix through an identical scorer should reproduce; the band is the honesty test below |
| score_pds | **below** k035's 0.6113; expect 0.575–0.605 | the agreement gate is the only pds-raising delta between k027 and k035 |
| score_reach | **below** k035's 0.0591; expect 0.040–0.055 | same mechanism; k035's +0.016 vs k034 was attributed to the gate |
| score_nmae | **at or above** k035's 0.0830; expect 0.085–0.090 | the gate costs nmae (−0.004 vs k034), so removing it should recover it |
| score_mse | ~0.012 (band 0.010–0.014) | k034 0.0127 / k035 0.0118 both bracket the un-moved channel |
| score_fid | −0.018 to −0.024 | flat across all recent recipes |
| score_jac | ~0.001 | flat across all recent recipes |

## Read (falsifiable, decided before submit)

1. **score_avg reproduces (±0.005)** → scorer/panel stable since Sept 22; k027
   components become the canonical baseline and the k035-vs-k027 gate delta is
   now a clean single-variable comparison. Continue stacking machinery on
   `ctr_agr_tight`.
2. **score_avg moves > ±0.01** → the evaluation moved under us (panel/scorer
   drift, or leaderboard re-anchoring). That is the single most valuable result
   this slot could produce: it means cross-date recipe comparisons in §4 are
   confounded and every "regression/win" call needs re-basing.
3. **pds/reach NOT below k035** → the agreement gate did not actually buy
   direction; k035's 6/6 "confirmed" reading was an artifact of confounded
   baselines. Deprioritize agreement-gate stacking.

## Cost

1 of 2 daily slots, Oct 3 (0 used today). No compute risk: build is local to
the VPS, only `vcc submit` is externally visible.

---

## RESULT (2026-10-03T21:50:48Z published — entry `olPYV6UW8ytPw4i5AXSs`, rank 483/1299)

`score_avg` **+0.12617341** (recorded champion +0.1262 → Δ **+0.00003**).
Components: pds 0.60321 · mse 0.01483 · nmae 0.08817 · fid −0.01882 ·
reach 0.06858 · jac 0.00106.
Raw channels: pds_cosine 0.77221 · expr_mse 0.97377 · lfc_nmae 0.94806 ·
fid_yield 0.50706 · reach 0.13964 · jaccard 0.03069.
`panel_id vcc2026-val-1`, `anchor_version valA-r4+valB-r4+valC-r4` — identical
to k035's receipt, so the two entries are directly comparable.

### Band-by-band against the declarations above

| component | declared | actual | verdict |
|---|---|---|---|
| score_avg | +0.1212…+0.1312 | +0.12617 | **CONFIRMED** (Δ3e-5 from the recorded value) |
| score_pds | 0.575–0.605, below k035 | 0.60321 | **CONFIRMED** (top of band) |
| score_reach | 0.040–0.055, below k035 | 0.06858 | **FALSIFIED** — above band AND above k035 |
| score_nmae | 0.085–0.090, ≥ k035 | 0.08817 | **CONFIRMED** |
| score_mse | 0.010–0.014 | 0.01483 | **MISS** (0.0008 above band; champion is *worse* than k035) |
| score_fid | −0.018…−0.024 | −0.01882 | **CONFIRMED** |
| score_jac | ~0.001 | 0.00106 | **CONFIRMED** |

### Which reads fired

**Read 1 fired** — scorer/panel/anchors are stable across the 11-day gap
(3e-5 on an identical byte stream). Cross-date comparisons in §4 are **not**
drift-confounded; the rank slides (308→483, 1088→1299 entries) are field
densification only. Read 2 is dead: no drift.

**Read 3 fired in part** — the pds half held (champion 0.6032 < gate 0.6113),
but the reach half broke. Re-reading k035 against this clean baseline:

| | k037 (champion) | k035 (ctr_agr) | gate Δ |
|---|---|---|---|
| pds | 0.60321 | 0.61126 | **+0.00805** |
| mse | 0.01483 | 0.01177 | −0.00306 |
| nmae | 0.08817 | 0.08301 | −0.00516 |
| fid | −0.01882 | −0.02090 | −0.00209 |
| reach | 0.06858 | 0.05912 | **−0.00946** |
| jac | 0.0010618 | 0.0010367 | −0.00003 |
| **avg** | +0.126173 | +0.124215 | **−0.001958** |

The agreement gate is a **component reshuffle, not a win**: it buys direction
(+0.008 pds) and pays it back with reach (−0.0095), nmae (−0.005), mse (−0.003)
and fid (−0.002). The six channel deltas sum to exactly the observed overall
loss. AGENTS.md's k035 line claiming the gate set the "highest recorded
`score_pds` (0.6113) **and `score_reach`** (0.0591)" is wrong on reach — the
champion scored 0.0686 — corrected in the same commit as this note.

Consequence for the reference delta set: `consensus_w_ctr_agr_tight` is *not*
a promotion on this evidence, only a tie-with-cost. It stays the reference for
stacking **only** because it moves pds, which is the channel the final phase
cannot otherwise reach.

### Consequence for k038 (same day, slot 2)

k038's declared reach band (0.062–0.072) was written against k035's 0.0591 and
hence read as "big rise". Against the true baseline it means something sharper
and better: **does `rmass` restore reach to champion level (≥0.0686) while
keeping the gate's +0.008 pds?** That is the pass criterion — the pds-vs-reach
trade above is exactly what rmass was built to break. nmae remains the
falsifiable one: predicted flat ±0.004 around k035's 0.0830, i.e. NOT back to
the champion's 0.0882.

### Infra corrections (these were wrong or unknown going in)

- `vcc prep` peaks **>29 GB** and cannot run on the 31 GB VPS; packaging is a
  Modal step. Recorded for the Oct 22 runbook.
- The site allows **one in-flight submission per team**, so the 2/day cap is not
  the binding constraint — scoring latency is (~20 min observed here). k038 had
  to queue behind k037; chained via `/tmp/k038_chain.sh`.
- The first k037 Modal submit job stopped after its image build with no
  function logs. `/api/cli/submissions/limits` (`spent 0, in_flight 0`) proved
  nothing reached the server, so no slot was lost — verify with `limits`, don't
  assume.
- Cost: 1 of 2 slots (k038 takes the second). The re-score is the cheapest
  possible probe — a byte-identical resubmit of an artifact already on disk —
  and it invalidated/anchored five runs' worth of component reads.
