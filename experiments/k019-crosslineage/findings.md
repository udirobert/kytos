# k019 — cross-lineage transfer, OOD-proxy gate

Date: 2026-09-19. Data: `essential_transfer_data.npz` (~2.3k paired K562↔lineage
essential targets). Held-out split; "OOD-proxy" = the *least cross-lineage-conserved*
targets (closest available stand-in for the non-essential panel targets).

## Headline

| lineage | metric (held-out cosine) | identity | global_scalar | ridge_dual | kernel_rbf | low_rank | gene_scale |
|---|---|---:|---:|---:|---:|---:|---:|
| Jurkat (A) | **OOD-proxy** | **−0.090** | −0.090 | +0.044 | +0.138 | **+0.099** | −0.094 |
| Jurkat (A) | in-dist | +0.619 | +0.619 | +0.826 | +0.701 | +0.818 | +0.656 |
| RPE1 (B)   | **OOD-proxy** | **−0.077** | −0.077 | +0.254 | +0.268 | **+0.296** | −0.049 |
| RPE1 (B)   | in-dist | +0.443 | +0.443 | +0.674 | +0.518 | +0.656 | +0.470 |

Δ-over-identity on OOD-proxy: Jurkat +0.14…+0.23, RPE1 +0.33…+0.37.

## Interpretation

1. **Identity transplant (what k011/k018 use for contexts A/B) is *anti-correlated*
   with the true lineage delta on panel-like targets** (cos ≈ −0.08/−0.09). For the
   ~non-conserved majority of the panel we are shipping the *wrong sign* of effect.
   This is the mechanistic reason `pds` is stuck at ~0.34.
2. **`delta_scale` cannot fix it** (global_scalar == identity cosine; it only rescales
   norm 0.73→0.39). Consistent with the whole k011/k013 magnitude-axis exhaustion.
3. **A learned cross-lineage map flips OOD cosine positive** — low_rank (k015's own
   method) is the strongest on OOD for both lineages; kernel_rbf close; ridge_dual ok.
   So k015's leaderboard regression was NOT the map direction — it was the surrounding
   config (and the 6000-gene/3000-target caps here differ from the panel build).
4. **gene_scale / per-gene coefficients do NOT extrapolate** (OOD ≈ identity). Only
   maps that move mass *across* genes (linear-subspace / nonlinear) recover direction.

## Caveat (do not skip)

OOD-proxy targets are still *essential* lineage-specific genes, not the actual 272
non-essential panel targets. Proxy ≠ proof. The only way to confirm is a single
leaderboard slot: replace identity transplant on contexts A/B with the learned
cross-lineage map, keep the champion sampler + delta_scale=1.7, and read pds.

## Decision

Path A gate: **PASSED** — a model class survives OOD by a wide margin, and it beats
the status-quo (identity) which is net-negative there. Proceed to build k019
(map-applied A/B panel prediction) as the decisive single-slot experiment.
