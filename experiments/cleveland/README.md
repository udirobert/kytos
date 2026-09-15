# Cleveland experiments

Run-IDs use the `cNNN-*` prefix (VCC keeps `kNNN-*`).

| Run | What |
|---|---|
| `c001-ctrw-full-vs-coarse` | Phase 1 classical CTRW + spectral coarse-grain Spearman gate (≥0.8) |
| `c002-ctqw-coarse` | Phase 2 exact CTQW on coarse graphs + classical comparison; myosin P1 ρ=0.823 kept visible |

```bash
.venv-cleveland/bin/python tools/run_cleveland_c001.py
.venv-cleveland/bin/python tools/run_cleveland_c002.py
```

Artifacts follow `docs/cleveland/run-protocol.md`.
