# c002 — CTQW on coarse graphs

## Phase 1 compression receipts (do not drop)

**Tightest margin: `cardiac_myosin`** — Spearman **ρ=0.8230** (only 0.0230 above the 0.8 gate; 795→56 nodes).

Tightest Phase 1 compression margin (threshold 0.8). If Phase 2 connectivity looks weaker here, ask whether coarse-graining held up — receipts are this ρ and n_full→n_coarse.

If Phase 2 connectivity / known-site recovery looks weaker specifically on cardiac myosin, that is the first place to ask whether compression held up — these receipts answer that question either way.

## Per-target snapshot

| Target | P1 ρ | Q↔C ρ | CTQW known in top-5 | Best known rank (CTQW) |
|---|---|---|---|---|
| kras_g12c | 0.8573 | 0.3770 | 0/4 | 27.0 |
| bcr_abl1 | 0.8544 | 0.6837 | 1/5 | 3.0 |
| cardiac_myosin **← tightest P1** | 0.8230 | 0.6596 | 0/5 | 393.0 |
| cmyc_max | 0.9425 | 0.9113 | None/0 | None |

Hamiltonian: `laplacian`. Backend: exact `expm(-iHt)` (simulator; Braket/Classiq packaging is a follow-on).

## Label erratum (post-c002)

Cardiac myosin known-site list in c002 used a placeholder pocket. Corrected to
literature mavacamten contacts in `targets.py`; see `c003` / `method-report.md`.
Myosin Phase 1 ρ=0.823 margin unchanged and still the tightest compression receipt.

