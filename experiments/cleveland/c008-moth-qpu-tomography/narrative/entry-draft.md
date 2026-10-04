# Quantum tomography of a protein's allosteric core — on real hardware

**Challenge:** Quantum-native (expert tier) · Moth Hack 2026 virtual hackathon

## The idea

Allosteric drug sites — the pockets that made "undruggable" proteins like KRAS
druggable — are encoded in a protein's *contact topology*: which residues touch
which. We take the contact graph of a real drug target, keep the 20-node
"allosteric core" (the catalytic site, the known drug pocket, and the strongest
couplings between them), and hand it to a quantum processor as a coupling map.
What comes back is a measured two-qubit correlation structure for that piece of
biology — and a before/after picture of what a real QPU does to it.

This is quantum-native in the literal sense: the input is a graph that exists
only because a protein folds that way; the output is a quantum correlation
measurement that has no classical analog to "run" — you can only simulate it.

## What we ran

- **KRAS G12C** (PDB 4OBE) — the protein Sotorasib finally cracked; known
  allosteric pocket = Switch-II. 20-node core, 50 edges.
- **Cardiac myosin (MYH7)** — allosteric lever-arm drug target (mavacamten's
  protein). 20-node core, 42 edges.
- **Random control** — degree-matched random 20-node graph, 50 edges.

Each coupling map went through Moth's `graph-v1` engine twice: `emu` mode (Aer)
and `qpu` mode — executed on **IBM `ibm_fez`**, 1024 shots, full tomography:
per-qubit Bloch vectors + all nine two-qubit Pauli correlations per edge.

## What we found

1. **Correlation magnitude survives hardware.** Mean edge-correlation norms:
   KRAS 0.34 (emu) → 0.28 (QPU); myosin 0.42 → 0.42. Edge-agreement scores
   0.42–0.52 on hardware, comparable to emulation.
2. **Directional information decoheres.** Per-qubit Bloch vectors scramble
   between emulator and hardware (median cosine ≈ 0) — the noise is
   *orientational*, not amplitude loss.
3. **The topology signal is real but fragile.** On the emulator, protein
   coupling maps produce ~2× the edge correlation of the random control
   (0.34/0.42 vs 0.18). On hardware that separation washes out — today's
   QPUs blur exactly the fine structure that makes a protein graph a protein
   graph.

## Why it matters

This is a measurement, not a simulation claim: real protein topology in, real
hardware tomography out, with receipts (IBM job IDs below). The honest result —
"correlation survives, direction decoheres, topology-sensitivity is the first
casualty" — is a concrete fingerprint of where NISQ hardware stands when fed
real biological structure rather than benchmark graphs.

## Reproducibility

- Engine: Moth `graph-v1` (`mode: qpu`), IBM `ibm_fez`
- IBM jobs: KRAS `db1crfrid5ic73eqvk1g` · myosin `db1cssjid5ic73eqvlc0` ·
  control `db1d1h2vog1s73fhvp00`
- Code, graphs, payloads, raw results, analysis:
  `experiments/cleveland/c008-moth-qpu-tomography/` in this repo
- The pipeline upstream (PDB → contact graph → coarse-grain → CTQW allostery
  analysis) is the `src/cleveland/` package built for the Cleveland Clinic /
  GQAI quantum-allostery challenge.

## Honest caveats

- `graph-v1` internals are Moth's — we control the coupling map, not the
  circuit. The prepared state is *not* a pure graph state (single-qubit |r| up
  to 1.0); we report engine output faithfully.
- The 20-qubit engine cap forces functional-core subgraphs (KRAS 32→20,
  myosin 56→20 supernodes) — a slice of the protein, not the whole graph.
- We make no claim that hardware tomography recovers the allosteric site —
  site-ranking remains the classical+CTQW pipeline's job. This experiment
  characterizes what real hardware preserves and destroys.

## Figures

`narrative/figs/` — (1) the two allosteric cores colored by biological role,
(2) edge-correlation heatmaps emu vs QPU vs Δ, (3) per-qubit Bloch |r|,
(4) real-vs-random control comparison.
