# c003 — CTQW full vs coarse compression audit

**Phase 1 tightest margin:** `cardiac_myosin` ρ=**0.8230** (margin 0.0230; 795→56).

Question: does coarse-graining destroy CTQW known-site recovery?

| Target | P1 ρ | Full↔coarse CTQW ρ | Full best known rank | Coarse best known | Verdict |
|---|---|---|---|---|---|
| kras_g12c | 0.8573 | 0.6449 | 8.0 | 27.0 | `compression_degrades_known_signal` |
| bcr_abl1 | 0.8544 | 0.7961 | 11.0 | 3.0 | `compression_preserves_known_signal` |
| cardiac_myosin **← tightest P1** | 0.823 | 0.6369 | 99.0 | 24.0 | `compression_preserves_known_signal` |
| cmyc_max | 0.9425 | 0.8891 | None | None | `no_known_labels` |

Myosin verdict: **compression_preserves_known_signal** (full best known rank=99.0, coarse=24.0).

