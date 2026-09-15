# Cleveland Clinic Enterprise Challenge (GQAI 2026)

**Status:** Phases 1–3 + packaging landed (`c001`–`c006`). Method report:
[`method-report.md`](method-report.md). **Cardiac myosin Phase 1 ρ=0.823**
remains the tightest compression margin (surfaced every run). `c003`: myosin
compression preserves known-site signal. `c005`: best configs still n.s. vs
null. `c006`: Qiskit fidelity **1.0** vs exact; Braket/Classiq exports ready.
**Separate workstream** from the Virtual Cell Challenge.

| | |
|---|---|
| **Challenge** | Global Quantum + AI Challenge 2026 — Cleveland Clinic Enterprise |
| **Title** | Unlocking undruggable targets: quantum simulation of allosteric signal propagation |
| **Key / API** | Moth Quantum — `MOTH_API_KEY` in `.env` (see `.env.example`); platform [keys](https://platform.mothquantum.com/keys), [API docs](https://api.mothquantum.com/docs) |
| **Hardware (later)** | AWS Braket + Classiq (challenge-provided) |
| **Companion** | VCC work stays under `docs/`, `src/kytos/`, `experiments/<kNN-*>` |

Conventions mirror Kytos (`docs/run-protocol.md`): run-IDs, `meta.json`,
`facts.json`, provenance, deterministic audit flags over narrative claims —
all under the `cleveland/` prefix.

---

## Problem

>85% of disease-causing proteins are "undruggable" — no deep active-site pocket
for small molecules. The practical path is **allostery**: a distal regulatory
pocket that, when bound, shuts down the active site. Classical MD to find these
sites is prohibitive and **forbidden as input** here. The task is to predict
allosteric connectivity **ab initio from static structure/topology**, using a
quantum algorithm, then validate blind against a known drug-bound structure.

### Required outputs (per protein)

1. **Connectivity Matrix** — N×N quantum connectivity strength between residue pairs.
2. **Hit List** — ranked top-5 predicted allosteric residues.
3. **Methodological Report** — which quantum metric and why it proxies biological signal transmission.

### Hard constraints

- No classical MD as input — topology only.
- Circuit depth must respect near-term coherence; deep unoptimized circuits are penalized.
- Hardware: AWS Braket + Classiq (free under the challenge).
- **Elastic network hypothesis (granted):** residue-contact topology drives signal propagation; atomic force fields may be abstracted away.

### Blind benchmark targets

| Target | Apo (input) | Known allosteric site | Holo (validation) |
|---|---|---|---|
| KRAS G12C | 4OBE | Switch-II pocket (Sotorasib) | 6OIM |
| BCR-ABL1 | 1OPL | Myristoyl pocket (Asciminib) | 5MO4 |
| Cardiac myosin | 5TBY | Super-relaxed-state site (Mavacamten) | 6C1H |
| c-Myc/Max (exploratory) | 1NKP | — consensus / docking viability | — |

---

## Approach (agreed — implement, do not relitigate)

**Continuous-time quantum walk (CTQW)** over a coarse-grained residue contact
graph. Source = active site. Connectivity score = time-averaged transition
amplitude from source under \(U(t) = e^{-iHt}\), with \(H\) the weighted
adjacency / Laplacian. Satisfies constraints natively: topology-only,
elastic-network-compatible, and ships a classical baseline (same graph under a
continuous-time **random** walk) for the required quantum-vs-classical
comparison.

### Falsifiable physical hypotheses (test against the table above)

- **Ballistic vs. diffusive spread:** CTQW should separate well-coupled distal
  sites from background faster / more sharply than the classical walk.
- **Interference-driven selection:** CTQW should suppress residues that are
  close by graph distance but off-axis from the real pathway (diffusive false
  positives).

### Stack (Cleveland only — not the VCC stack)

| Use | Libraries |
|---|---|
| Quantum (Phase 2+) | Qiskit / Braket / Classiq |
| Graphs | `networkx` |
| Structure | BioPython (PDB) |
| **Not used here** | torch, scanpy, anndata, cell-eval |

---

## Phases

| Phase | Scope | Gate |
|---|---|---|
| **1** ✓ | Classical CTRW + Spearman ≥ 0.8 | Passed; myosin tightest ρ=0.823 |
| **2** ✓ | CTQW coarse (`c002`) + Qiskit packaging (`c006`, fid=1.0) | P1 gate visible; hardware exports ready |
| **2b** ✓ | Full vs coarse audit (`c003`) | Myosin compression preserves known-site signal |
| **3** ✓ | Randomization (`c004`) + signal sweep (`c005`) | No z&lt;-2 yet (documented negative) |
| **4** ✓ | Methodological report | [`method-report.md`](method-report.md) |

### Phase 1 checklist (classical only) — done

1. ✓ Ingest PDBs for **4OBE, 6OIM, 1OPL, 5MO4, 5TBY, 6C1H, 1NKP** — catalytic domain; exclude solvent / cofactors / PTMs unless trivial nodes.
2. ✓ Contact graph: Cα, 9 Å cutoff, inverse-distance weights (ENM — no force fields).
3. ✓ Classical continuous-time random walk; source = active site; logged under run-protocol.
4. ✓ Coarse-grain via spectral clustering, `clip(n/6, 32, 56)` supernodes (~5–6 qubit Phase 2 budget).
5. ✓ **Validation gate:** Spearman ρ ≥ 0.8 full vs coarse rankings — all four apo targets passed.

Out of scope until Phase 2+: Qiskit/Braket/Classiq circuits, significance tests, written methodological report.

---

## Layout & environment

See [`layout.md`](layout.md) (approved). Run protocol: [`run-protocol.md`](run-protocol.md).
ADR: [`architecture.md`](architecture.md).

```bash
.venv-cleveland/bin/python tools/run_cleveland_c001.py
.venv-cleveland/bin/python tools/run_cleveland_c002.py
.venv-cleveland/bin/python tools/run_cleveland_c003.py
.venv-cleveland/bin/python tools/run_cleveland_c004.py --n-null 40
.venv-cleveland/bin/python tools/run_cleveland_c005.py --n-null 20
.venv-cleveland/bin/python tools/run_cleveland_c006.py
```
