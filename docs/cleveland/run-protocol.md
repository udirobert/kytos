# Cleveland — experiment run protocol

Mirrors [`docs/run-protocol.md`](../run-protocol.md) under the `cleveland/`
namespace. VCC Observatory enrichment is **out of scope** for Phase 1.

## Layout

```
experiments/cleveland/<run-id>/
  meta.json
  facts.json
  config.json
  codehash
  metrics/summary.json
  audit/flags.json
  reproduce/seeds.json
```

## Run-ID prefix

| Prefix | Challenge |
|---|---|
| `kNNN-*` | Virtual Cell Challenge |
| `cNNN-*` | Cleveland Clinic / GQAI 2026 |

## Phase 1 `facts.json` (minimum)

```json
{
  "run_id": "c001-ctrw-full-vs-coarse",
  "challenge": "cleveland-gqai-2026",
  "phase": 1,
  "method": "classical_ctrw_full_vs_coarse",
  "gate": "spearman_rank_correlation",
  "all_pass": false,
  "targets": {
    "kras_g12c": {
      "pdb_id": "4OBE",
      "spearman_rho": 0.0,
      "pass": false,
      "n_full": 0,
      "n_coarse": 0,
      "hit_list_top5": [],
      "flags": []
    }
  }
}
```

## Audit flags (deterministic)

| id | severity | meaning |
|---|---|---|
| `coarsegrain_spearman_pass` | info | ρ ≥ 0.8 |
| `coarsegrain_spearman_fail` | fail | ρ < 0.8 — blocks Phase 2 for that protein |
| `sparse_active_site` | warn | few active-site residues on the LCC graph |
| `sparse_contact_graph` | warn | unusually few edges |

## Environment

Use `.venv-cleveland` only (see `docs/cleveland/layout.md`). Never install
Qiskit/Braket/Classiq into VCC venvs.
