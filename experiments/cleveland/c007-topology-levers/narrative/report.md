# c007 — topology levers vs edge-rewire null

Myosin Phase 1 compression margin: ρ=**0.8230** (tightest P1; still surfaced).

Levers: cutoff ∈ {8,9,10}, sources ∈ {active, +neighbors}, H ∈ {laplacian, adjacency}, score ∈ {T=10, multiscale, CTQW−CTRW}, resolution ∈ {coarse, full≤350}.

| Target | Winner | Best | z_best | z_mean | Sig? |
|---|---|---|---|---|---|
| kras_g12c | `cut=9.0 coarse/adjacency/ctqw_t10/active_plus_neighbors` | 2.0 | -1.5327580959954656 | -1.033484290445599 | False |
| bcr_abl1 | `cut=8.0 coarse/laplacian/ctqw_t10/active_plus_neighbors` | 2.0 | -0.7665946516991529 | -1.0924040928340126 | False |
| cardiac_myosin **← tightest P1** | `cut=9.0 coarse/laplacian/ctqw_t10/active+distal` | 3.0 | -1.0005655745839908 | -1.2332992972105123 | False |

**Any significant (z&lt;-2)?** `False`

