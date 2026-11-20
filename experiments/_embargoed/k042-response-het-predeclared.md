# k042 pre-declared: dual-moment response-heterogeneity gate round

Date: 2026-10-12. Gate: eval2 (hESC paired transfer, 47 targets), cell-eval2
official-style scoring. Run ID: `gate-20261012-01`.

## Motivation (locked before running)

The transport-era `kd_std` mechanism (per-cell scalar response amplitude)
bought ~+0.05 official through k008 sweeps, but was silently dropped when
dual-moment replaced transport. Never retested inside dual-moment.

Round-9 `dm_nb` falsified UNIFORM per-cell noise (regressed overall). The
untested class is DIRECTIONAL heterogeneity — variance proportional to the
response, concentrated on responding genes.

Instrumented finding (synthetic probes, this session): dual-moment's
bulk-vs-cell moment reconciliation already forces per-cell response spread
— coupled to library depth, and at small scale produces a bimodal
control-like/responder split even at escape_frac=0. So the per-cell tilt
mechanisms are NOT guaranteed to add new variance; the explicit mixture is
the cleanest intervention.

## Arms (all on the k040 ship deltas: consensus_w_ctr_sagr)

| arm | mechanism | what it tests |
|---|---|---|
| dm_ref | cons_w deltas, a1.0/b0.5 | same-run drift control |
| sagr_dm | sagr deltas, a1.0/b0.5 | in-run reference = k040 config |
| sagr_eta1p0 | + eta_std=1.0 | scalar response-amplitude heterogeneity |
| sagr_eta2p0 | + eta_std=2.0 | transport-era optimal value transplanted |
| sagr_esc30 | + escape_frac=0.3 | explicit 30% escaped-cell mixture |
| sagr_esc50 | + escape_frac=0.5 | strong escape mixture |
| sagr_rn | + k036 per-gene response noise | measured directional variance |

## Implementation (src/kytos/models/dual_moment.py)

- `cell_effects` plumbing in `dual_moment_counts`: post-matching per-row
  tilt toward the profile implied by that cell's own effect vector, then
  integer emission + bulk repair. Row depths preserved exactly.
- `eta_std`: eta_i ~ trunc-N(1, s) clipped at 0, cell_effects = eta_i*delta.
- `escape_frac`: population split — escaped cells emitted with zero effect,
  responders amplitude-boosted 1/(1-frac) (mean-preserving).
- `response_noise`: dict target -> (G,) std; effect = eta_i*delta + z*std.
  Sourced from k036 samplestats: sqrt(max(e2-mean^2,0) * cells_per_sample),
  pooled across hct116/hek293t weighted by n_samples_voting. Rough scale
  (uniform cells/sample assumed) — flagged approximate.

## Read rules (pre-declared)

- Promotion candidate requires: arm beats sagr_dm AND dm_ref on official
  avg by the usual transfer-confidence margin (~+0.02-0.03), not just a
  component reshuffle.
- eta arms below +0.02 on avg => scalar heterogeneity is already
  well-covered by depth-coupled reconciliation => axis closed, do not
  spend a slot.
- escape arms winning on pds/fid/reach with flat de_proxy => mechanism is
  real; if avg gain >= +0.02 over sagr_dm, a k042 submission probe is
  justified (one slot).
- sagr_rn below ref => measured per-gene dispersion doesn't translate to
  per-cell scale (or the sqrt scaling is wrong); downscale variants are
  knob-tuning, not a new mechanism => axis closed.
- All exact numbers stay in experiments/_embargoed/k025-eval2-gate/.

## Expectation (honest)

Primary risk: the depth-coupled reconciliation already saturates the
useful heterogeneity budget, so all arms ~= sagr_dm. That is itself a
decisive negative that closes the last untested generation-side axis.

## OUTCOME (2026-10-12, gate-20261012-01 complete)

Full table in diagnostic-numbers.md. Best arm sagr_eta1p0 +0.003 avg over
sagr_dm — non-monotone (1.5/2.0 regress) so knob noise, not a mechanism;
esc30/esc50 flat (+0.002 max); sagr_rn catastrophic (-0.13, pds
collapses). eta scales bulk norm 0.51->0.83 at unchanged direction
cosine. **All arms below the +0.02 promotion bar — axis CLOSED, no slot
spent.** Bonus confirmation: sagr_dm beats dm_ref by +0.006 in-gate,
consistent with the k040 official read.
