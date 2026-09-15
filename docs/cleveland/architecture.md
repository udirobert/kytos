# Cleveland — architecture (Phase 1)

ADR for the classical baseline that Phase 2 CTQW must beat.

## Decision

Predict allosteric connectivity from a **residue contact graph** (elastic
network) using a **continuous-time random walk (CTRW)** sourced at the
orthosteric / active site. Compress the graph with **spectral clustering** to
32–64 supernodes before any quantum circuit work.

## Why

- Topology-only input; no MD trajectories.
- Elastic-network hypothesis is a granted challenge assumption.
- CTRW is the required classical comparator for later CTQW (`U(t)=e^{-iHt}`).
- Coarse-graining is gated by Spearman ρ ≥ 0.8 between full and projected
  rankings — falsifiable, not cosmetic.

## Non-goals (Phase 1)

- Quantum circuits (Qiskit / Braket / Classiq)
- Force fields / classical MD
- Methodological prize report
- z-score randomization (Phase 3)

## Parameters (defaults)

| Knob | Default | Notes |
|---|---|---|
| Contact cutoff | 9 Å | mid of 8–10 Å challenge band |
| Edge weight | inverse distance | Gaussian optional |
| Atom | Cα | Cβ near pocket later if needed |
| Walk horizon | T=10 (dimensionless) | logged in config |
| Clusters | clip(n/6, 32, 56) | keeps mid-size kinases above Spearman gate; myosin peaks ~56 |

## Phase 1 result (`c001-ctrw-full-vs-coarse`)

| Target | PDB | n → coarse | Spearman ρ |
|---|---|---|---|
| KRAS G12C | 4OBE | 169 → 32 | +0.857 |
| BCR-ABL1 | 1OPL | 287 → 48 | +0.854 |
| Cardiac myosin | 5TBY | 795 → 56 | +0.823 |
| c-Myc/Max | 1NKP | 88 → 32 | +0.943 |

All ≥ 0.8 — Phase 2 CTQW unblocked.

**Compression watch:** `cardiac_myosin` is the tightest pass (ρ=0.823, margin
0.023). Phase 2 (`c002`) must keep this receipt visible; if CTQW recovery is
weak specifically on myosin, treat compression as a first-line hypothesis.

## Phase 2

Exact unitary CTQW via Hermitian eigendecomposition of \(H\)
(`backend: exact_unitary_eigh`). Same source = active site. Outputs: coarse
connectivity matrix, top-5 hit list, classical CTRW comparator, post-hoc
known-site recovery. Hardware (Braket/Classiq) is packaging, not a different
metric.

## Phase 2b / 3 / packaging findings (keep myosin visible)

- **c003:** Myosin full vs coarse CTQW → compression **preserves** known-site
  signal (best known rank 99 → 24). KRAS is where compression hurts (8 → 27).
- **c004 / c005:** Edge-rewire nulls — no target with z&lt;-2 yet; c005 winners
  improve anecdotal ranks (KRAS best=5, Abl best=3, myosin best=24 with
  adjacency / T=10 coarse).
- **c006:** Qiskit `HamiltonianGate` packaging fidelity **1.0** vs exact eigh
  (incoherent sources). Braket/Classiq export stubs ready.
- Mavacamten labels: literature pocket contacts in `targets.py`.

