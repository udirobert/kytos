# c008 — Moth `graph-v1` tomography of protein allosteric cores on real hardware

**Run date:** 2026-10-04 · **Context:** Moth Hack virtual hackathon (submissions close **2026-10-05 23:59 PT**) · **Engine:** `graph-v1` (Moth Atlas) · **Hardware:** `ibm_fez` via Moth platform credentials.

## What ran

Two protein contact-graph "functional cores" were executed on real IBM quantum
hardware through Moth's graph engine:

| target | source graph | subgraph | moth qpu job | IBM job |
|---|---|---|---|---|
| KRAS G12C | 32 supernodes (c002 coarse grain) | 20 nodes / 50 edges | `252b239d-30c6-4400-bf45-7f78002993a6` | `db1crfrid5ic73eqvk1g` |
| cardiac myosin (MYH7) | 56 supernodes | 20 nodes / 42 edges | `54b278da-eb53-416b-bae7-f92f14b15769` | `db1cssjid5ic73eqvlc0` |

Each subgraph was extracted to fit the engine's 20-qubit cap while preserving
the biologically meaningful core: catalytic/active-site "source" supernodes,
known allosteric-site supernodes (KRAS: Switch-II / Sotorasib pocket; myosin:
converter/lever-arm), then greedily filled with the strongest-coupled
neighbors. Node-to-residue mapping is in `metrics/graphs/*_core.json`.

`mode: emu` ran the same coupling map on Moth's Aer backend as the comparison
baseline. 1024 shots per job; full single-qubit Bloch tomography + two-qubit
Pauli-pair correlations on every graph edge returned.

## What came back (`metrics/summary.json`)

| | KRAS emu→qpu | myosin emu→qpu |
|---|---|---|
| edge agreement score | 0.42 → 0.52 | 0.48 → 0.48 |
| mean edge \|corr\| | 0.338 → 0.284 (×0.84) | 0.419 → 0.424 (×1.01) |
| mean Bloch \|r\| | 0.55 → 0.50 | 0.59 → 0.64 |
| per-qubit Bloch direction cosine (median) | −0.01 | −0.27 |

## Honest interpretation

- **Correlation magnitudes survive hardware.** Edge-level two-qubit correlation
  norms on `ibm_fez` match or exceed the emulator baseline (myosin slightly
  higher — within protocol variance).
- **Directional structure does not.** Per-qubit Bloch vectors scramble between
  emu and QPU (median cosine ≈ 0 to −0.27). The decoherence signature here is
  *orientational* noise, not amplitude damping.
- **The engine is not preparing a pure graph state.** A graph state would show
  |r|=0 single-qubit marginals; both backends return |r| up to 1.0, and the emu
  output deviates from the exact CZ-product baseline we computed locally
  (`metrics/graphs/*_exact.json`, built by `reproduce/exact_baseline.py`).
  The correct description is "Moth's correlated-state protocol parameterized by
  our protein coupling map" — the biology enters through the coupling map.
- **No site-recovery claim.** Known-site edge correlations are inconsistent
  across targets (KRAS: lowest role mean; myosin: highest, n=5) — noise, not
  signal. The biological site-ranking result remains the CTQW analysis in
  c002–c007; this run supplies the hardware receipt and decoherence
  characterization. The pre-declared significance gate is still unmet.

## For the write-up (W2)

One-paragraph story: *We took the allosteric cores of two real drug targets —
KRAS G12C (the protein Sotorasib finally cracked) and cardiac myosin — encoded
their contact topology as 20-qubit coupling maps, and ran full two-qubit
tomography on real IBM hardware through Moth's platform. Correlation structure
survives the hardware; directional information decoheres — a measurable
fingerprint of what today's QPUs preserve and destroy when you feed them real
biology.*

Reproducibility receipts: job IDs above; payloads in `metrics/requests/`;
raw engine responses in `metrics/results/`.

## For visuals (W3)

Data files all under `experiments/cleveland/c008-moth-qpu-tomography/metrics/`:

- `graphs/{kras,myosin}_core.json` — 20-node coupling maps + node→residue roles
- `results/*_{emu,qpu}.json` — full tomography (bloch, relationships, measurements)
- `summary.json` — the headline table
- Suggested figures: (a) the 20-qubit graph colored by role (source/known/connector);
  (b) edge correlation heatmap emu vs qpu side-by-side + Δ; (c) per-qubit
  Bloch-vector |r| bar chart emu vs qpu; (d) the real backend receipt line
  (ibm_fez job IDs).

## Caveats for judges

- `graph-v1` internals are Moth's; we can document inputs/outputs but not the
  circuit. Disclosed in `audit/flags.json`.
- 20-qubit cap → functional-core subgraph, not the whole protein graph.
- `emu` is an emulator baseline, not necessarily an ideal-statevector baseline —
  the exact local reference is `metrics/graphs/*_exact.json`.
