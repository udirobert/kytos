# Cleveland experiments

Run-IDs use the `cNNN-*` prefix (VCC keeps `kNNN-*`).

| Run | What |
|---|---|
| `c001-ctrw-full-vs-coarse` | Phase 1 classical CTRW + Spearman gate (≥0.8); myosin ρ=0.823 tightest |
| `c002-ctqw-coarse` | Phase 2 exact CTQW on coarse graphs + classical compare |
| `c003-ctqw-compression-audit` | Full vs coarse CTQW; myosin compression preserves known-site signal |
| `c004-randomization` | Phase 3 edge-rewire z-scores (not significant yet) |

```bash
.venv-cleveland/bin/python tools/run_cleveland_c001.py
.venv-cleveland/bin/python tools/run_cleveland_c002.py
.venv-cleveland/bin/python tools/run_cleveland_c003.py
.venv-cleveland/bin/python tools/run_cleveland_c004.py --n-null 40
```

Method draft: [`docs/cleveland/method-report.md`](../../docs/cleveland/method-report.md).

Artifacts follow `docs/cleveland/run-protocol.md`.
