# Cleveland experiments

Run-IDs use the `cNNN-*` prefix (VCC keeps `kNNN-*`).

| Run | What |
|---|---|
| `c001-ctrw-full-vs-coarse` | Phase 1 classical CTRW + Spearman gate; myosin ρ=0.823 tightest |
| `c002-ctqw-coarse` | Phase 2 exact CTQW on coarse graphs + classical compare |
| `c003-ctqw-compression-audit` | Full vs coarse CTQW; myosin compression preserves known-site signal |
| `c004-randomization` | Phase 3 edge-rewire z-scores (not significant) |
| `c005-signal-sweep` | H×T×resolution grid + null on winners (n.s.; better ranks) |
| `c006-circuit-packaging` | Qiskit packaging fid=1.0; Braket/Classiq exports |

```bash
.venv-cleveland/bin/python tools/run_cleveland_c00{1..6}.py
```

Method report: [`docs/cleveland/method-report.md`](../../docs/cleveland/method-report.md).

Artifacts follow `docs/cleveland/run-protocol.md`.
