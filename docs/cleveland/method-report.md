# Methodological report — GQAI 2026 Cleveland Clinic

**Team / repo:** Kytos `cleveland/` workstream  
**Runs:** `c001`–`c006` (2026-09-15)  
**Quantum metric:** continuous-time quantum walk (CTQW) time-averaged transition
probability on an elastic-network residue contact graph.

Numbers below are anchored to committed `experiments/cleveland/c00*` artifacts.

---

## 1. Problem and constraints

Predict allosteric connectivity **ab initio from static structure/topology**
(no classical MD trajectories as input). Required outputs per protein:
connectivity matrix, top-5 hit list, and this methodological account.

Granted: elastic-network hypothesis (contact topology drives signal).
Hardware: AWS Braket + Classiq — we package the **same metric** (c006); live
queue submission awaits challenge credentials.

## 2. Quantum metric (why it proxies signal)

Residue Cα contact graph within 9 Å, inverse-distance edge weights (ENM).
Default Hamiltonian: combinatorial Laplacian \(H = D - A\). Evolution
\(U(t)=e^{-iHt}\). Connectivity from active-site sources \(S\):

\[
C_j = \frac{1}{T}\int_0^T \sum_{s\in S} \frac{1}{|S|}\,\bigl|\langle j|U(t)|s\rangle\bigr|^2\,dt
\]

(uniform time samples; Hermitian eigendecomposition of \(H\)). Sources are an
**incoherent** mixture of basis states (not a coherent superposition).

**Why this proxies biological signal transmission**

- Topology-only and ENM-compatible by construction.
- Unitary evolution is ballistic / interference-capable vs classical CTRW on
  the same graph (required quantum–classical contrast).
- Orthosteric source → distal high-\(C_j\) residues as allosteric candidates.

## 3. Classical baseline

CTRW generator \(Q = D^{-1}A - I\), time-averaged occupation (`c001`/`c002`).

## 4. Coarse-graining and the myosin margin

Spectral clustering to `clip(n/6, 32, 56)` supernodes (~5–6 qubits after pad).

| Target | P1 Spearman ρ | Nodes |
|---|---|---|
| KRAS G12C | 0.857 | 169→32 |
| BCR-ABL1 | 0.854 | 287→48 |
| **Cardiac myosin** | **0.823** | **795→56** |
| c-Myc/Max | 0.943 | 88→32 |

**Cardiac myosin is the tightest Phase 1 pass (margin 0.023).** Every run
`c002`–`c006` surfaces this receipt.

### Compression audit (`c003`)

After correcting mavacamten pocket labels to literature contacts
(164, 167, 168, 666, 710–712, 721–722):

| Target | Full best known | Coarse best known | Verdict |
|---|---|---|---|
| KRAS | 8 | 27 | compression degrades |
| Abl | 11 | 3 | preserves |
| **Myosin** | 99 | **24** | **preserves** |

Myosin’s early c002 miss was **label error**, not the ρ=0.823 compression
margin. KRAS is where compression costs known-site rank — prefer full-graph
CTQW there when compute allows.

## 5. Blind recovery, nulls, and sweeps

| Run | Result |
|---|---|
| `c004` | Edge-rewire null on default CTQW — no z&lt;−2 |
| `c005` | Grid over {laplacian, adjacency} × {T=3,10,30} × {full, coarse}; null on winners — **still no z&lt;−2** |

**c005 winners (best known rank):**

| Target | Winner | Best known | z |
|---|---|---|---|
| KRAS | coarse / adjacency / T=10 | 5 | −0.82 |
| Abl | coarse / laplacian / T=3 | 3 | −0.85 |
| Myosin ← P1 tightest | coarse / adjacency / T=10 | 24 | +1.18 |

Honest conclusion: ENM–CTQW with these knobs is not yet significant under a
topological null. Abl remains the strongest anecdotal recovery (known site
rank 3).

## 6. Hardware packaging (`c006`)

Qiskit `HamiltonianGate` statevector on zero-padded coarse \(H\) (5–6 qubits).
**Fidelity vs exact eigh = 1.000** on all four targets when sources are mixed
incoherently. Braket/Classiq JSON + \(H\) `.npy` exports live under
`experiments/cleveland/c006-circuit-packaging/metrics/exports/` for challenge
queues. Depth-constrained Trotterization must preserve this metric.

## 7. Limitations and next levers

- Significance vs rewire null is the open scientific gap — not packaging.
- Try: contact cutoff sweep, community-weighted sources, multi-scale \(T\)
  integrals, or learned edge weights still topology-only.
- Live Braket/Classiq runs when credentials are available.
- c-Myc/Max stays exploratory (no validated site).

## 8. Artifact index

| Run | Role |
|---|---|
| `c001` | Classical CTRW gate; myosin ρ=0.823 |
| `c002` | Coarse CTQW + connectivity matrices |
| `c003` | Full vs coarse; myosin compression OK |
| `c004` | Edge-rewire z-scores (n.s.) |
| `c005` | H×T×resolution sweep (n.s. but better ranks) |
| `c006` | Qiskit packaging; Braket/Classiq exports |

Code: `src/cleveland/`. Env: `.venv-cleveland` (includes Qiskit).  
Secret: `MOTH_API_KEY` in `.env` only.
