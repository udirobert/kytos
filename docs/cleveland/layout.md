# Cleveland — layout & environment

**Approved 2026-09-15.** Phase 1 implemented under this tree.
Mirrors the pre–Milestone 0 environment gate used for VCC work.

---

## Directory structure

Namespaces stay under `cleveland/` so VCC and GQAI never share modules,
data paths, or experiment IDs.

```
docs/cleveland/
  README.md              # challenge brief, approach, phases
  layout.md              # this file — env + tree
  run-protocol.md        # cleveland meta/facts schemas
  architecture.md        # CTQW / CTRW / coarse-grain ADR

src/cleveland/
  __init__.py
  targets.py             # PDB IDs, chains, active-site defs
  pipeline.py            # Phase 1 orchestration
  pdb/                   # fetch + catalytic-domain parse
  graph/                 # contact graph (ENM weights), coarse-grain
  walk/                  # classical CTRW (+ CTQW stub later)
  eval/                  # Spearman gate, hit-list ranking, audit flags
  io/                    # meta.json / facts.json writers

data/cleveland/
  README.md              # manifest: PDB IDs, chains, active-site defs
  raw/                   # gitignored — PDB downloads

experiments/cleveland/
  README.md
  c001-ctrw-full-vs-coarse/
    meta.json / facts.json / config.json / codehash
    metrics/ audit/ reproduce/

tests/cleveland/
  test_contact_graph.py

tools/run_cleveland_c001.py
```

**Not created yet:** Observatory pages for Cleveland, VCC harness changes,
or Qiskit/Braket/Classiq packages (Phase 2).

### Run-ID convention

| Prefix | Challenge |
|---|---|
| `kNNN-*` | Virtual Cell Challenge (existing) |
| `cNNN-*` | Cleveland / GQAI |

First classical baseline: `c001-ctrw-full-vs-coarse` (Phase 1 gate **all pass**).

---

## Python environment

**`.venv-cleveland`** + `pyproject` optional group `cleveland`:

```bash
uv venv .venv-cleveland
uv pip install --python .venv-cleveland/bin/python \
  "numpy" "scipy" "networkx>=3.0" "biopython>=1.81" "scikit-learn>=1.3" "pytest"
uv pip install --python .venv-cleveland/bin/python -e . --no-deps
```

Do **not** install torch/scanpy into `.venv-cleveland`. Do **not** install
Qiskit into `.venv` / `.venv-science`.

No hard ABI conflict with the VCC stack — the split is operational hygiene
against Phase 2 SDK bloat on an 8 GB Mac.

---

## Secrets

| Var | Where | Notes |
|---|---|---|
| `MOTH_API_KEY` | `.env` only (gitignored) | Placeholder in `.env.example` |
| `MOTH_API_BASE_URL` | `.env` / example | default `https://api.mothquantum.com` |

Scanner: `tools/scan_secrets.py` matches `\bmoth_[A-Za-z0-9]{16,}\b`.
