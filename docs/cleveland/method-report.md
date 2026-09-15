# Methodological report (draft) — GQAI 2026 Cleveland Clinic

**Team / repo:** Kytos `cleveland/` workstream  
**Runs:** `c001`–`c004` (2026-09-15)  
**Quantum metric:** continuous-time quantum walk (CTQW) time-averaged transition
probability on an elastic-network residue contact graph.

This is the Phase 4 writeup draft. Numbers are anchored to committed
`experiments/cleveland/c00*` artifacts — not narrative invention.

---

## 1. Problem and constraints

Predict allosteric connectivity **ab initio from static structure/topology**
(no classical MD trajectories as input). Required outputs per protein:
connectivity matrix, top-5 hit list, and this methodological account.

Granted: elastic-network hypothesis (contact topology drives signal).
Hardware path: AWS Braket + Classiq (packaging deferred; metric identical).

## 2. Quantum metric (why it proxies signal)

We take the residue Cα contact graph within 9 Å, edges weighted by inverse
distance (ENM). The Hamiltonian is the combinatorial Laplacian
\(H = D - A\). The continuous-time quantum walk evolves
\(U(t) = e^{-iHt}\). Connectivity from active-site sources \(S\) is

\[
C_j = \frac{1}{T}\int_0^T \sum_{s\in S} \frac{1}{|S|}\,\bigl|\langle j|U(t)|s\rangle\bigr|^2\,dt
\]

(approximated by uniform time samples; implemented via one Hermitian
eigendecomposition of \(H\)).

**Why this is a proxy for biological signal transmission**

- Topology-only and ENM-compatible by construction.
- Unitary evolution is **ballistic / interference-capable**, unlike the
  classical continuous-time random walk (CTRW) on the same graph — the
  challenge’s required quantum-vs-classical contrast.
- Source = orthosteric / active site; distal high-\(C_j\) residues are
  candidate allosteric nodes (hit list).

## 3. Classical baseline

Same graph, CTRW generator \(Q = D^{-1}A - I\), time-averaged occupation.
Logged in every Phase 2+ run (`quantum_vs_classical_spearman`).

## 4. Coarse-graining and the myosin margin

Spectral clustering to `clip(n/6, 32, 56)` supernodes (~5–6 qubit budget).

Phase 1 gate (`c001`): Spearman ρ between full and coarse **classical**
rankings ≥ 0.8 for all apo targets.

| Target | P1 ρ | Nodes |
|---|---|---|
| KRAS G12C | 0.857 | 169→32 |
| BCR-ABL1 | 0.854 | 287→48 |
| **Cardiac myosin** | **0.823** | **795→56** |
| c-Myc/Max | 0.943 | 88→32 |

**Cardiac myosin is the tightest pass (margin 0.023).** Every subsequent run
surfaces this receipt so a weak myosin result can be read as a compression
question rather than a silent failure.

### Compression audit (`c003`)

Full-graph vs coarse CTQW known-site recovery (mavacamten pocket labels
corrected to literature contacts: 164, 167, 168, 666, 710–712, 721–722):

| Target | Full best known rank | Coarse best known | Verdict |
|---|---|---|---|
| KRAS | 8 | 27 | compression degrades |
| Abl | 11 | 3 | compression preserves |
| **Myosin** | 99 | **24** | **compression preserves** |

**Answer for reviewers:** on myosin, coarse-graining did **not** destroy the
known-site signal; the earlier c002 catastrophe (rank ~393) was dominated by
**wrong pocket labels**, not the ρ=0.823 compression margin.

## 5. Blind recovery and significance (`c002`/`c004`)

Post-hoc only — known sites never enter the Hamiltonian.

Phase 3 (`c004`): degree-preserving edge-rewire null (40 draws). Observed mean
known-site ranks are **not** significantly better than null (no z &lt; −2).
That is a real negative: CTQW-on-ENM with these defaults is not yet a
validated allosteric predictor under a topological null.

## 6. Limitations and next levers

- Exact unitary on ≤800 nodes is a **simulator**; Braket/Classiq circuits must
  match this metric under depth constraints.
- Hit lists still weak vs null — try adjacency Hamiltonian, multi-scale \(T\),
  or community-aware sources before claiming biology.
- KRAS is where compression *does* hurt known-site rank — optional
  full-graph CTQW for small domains.
- c-Myc/Max remains exploratory (no validated site).

## 7. Artifact index

| Run | Role |
|---|---|
| `c001-ctrw-full-vs-coarse` | Classical gate; myosin ρ=0.823 |
| `c002-ctqw-coarse` | Coarse CTQW + connectivity matrices |
| `c003-ctqw-compression-audit` | Full vs coarse; myosin compression OK |
| `c004-randomization` | Edge-rewire z-scores (not significant yet) |

Code: `src/cleveland/`. Env: `.venv-cleveland`. Secret: `MOTH_API_KEY` in `.env`.
