# Kytos — Phase 0 Environment

Status: **UPDATED 2026-09-23** — local `cell-eval 0.8.2` is the legacy harness
used by early runs; the official 2026 scorer `cell-eval2` (`vcc2026`) is pinned
at `5e64833518a6603a0301cbe28185d49c30f4a986` (v0.16.0), contract smoke-tested
(2026-09-21), and used for the k025 Gate B real-data run (2026-09-22). The
local `.venv-eval2` was deleted 2026-09-23 to save disk — rebuild with:
`python3.12 -m venv .venv-eval2 && .venv-eval2/bin/pip install "cell-eval2 @
git+https://github.com/ArcInstitute/cell-eval2@5e64833518a6603a0301cbe28185d49c30f4a986"
"pdex==0.3.0"`. Real scoring runs on Modal with the same pin.

Declared for the 2026 Virtual Cell Challenge. Install via `uv`. Python 3.14.5
is present here; `uv` 0.5.9 is available.

**Platform note (updated 2026-08-22, evening):** `uv sync` now works end to
end. Two gotchas were fixed: (1) `torch` ≥2.13 ships no macOS wheels at all,
so `pyproject.toml` forks the constraint (`torch<2.13` on darwin, latest
elsewhere — uv resolves a per-platform lock fork); (2) the local `.venv` had
accidentally been created from an **x86_64 (Rosetta) Python** — recreated as
arm64 (`uv venv --python cpython-3.12.8-macos-aarch64`). On this machine the
env resolves to torch 2.12.1; full suite: 89/89 green in one command
(`uv run pytest`). `.venv-science` (uv-managed CPython 3.12.8, legacy
`cell-eval 0.8.2` + pdex) remains the local eval environment.

## Compute reality (updated 2026-09-05)

This Mac has **8 GB RAM** (`sysctl hw.memsize` confirms 8 GiB). That is enough
to install the env, run `vcc prep --dry-run` on small subsets, generate sparse
baselines (e.g. `tools/run_k003_mean_shift.py`), and work on the Observatory.
It is **not** enough to:

- run a full `vcc prep` on a 2026 panel (peak ~28 GB),
- hold the 2025 Atlas source (6.9 GB) and prep it,
- run the legacy `cell-eval` harness or `cell-eval2` on the full 2025 validation,
- train any real Layer A/B model or sample real control-cell distributions.

For those tasks the default is an **external machine** (Kaggle free GPU for
smoke tests, Vast/RunPod hourly for `vcc prep` / training, a 32 GB+ VPS if a
persistent cron is needed). See `docs/release-infrastructure.md §4` and
`docs/architecture.md §4` for the compute ladder and platform ordering.

## Core inference/env stack

| Package | Why |
|---|---|
| `anndata` | cell × gene matrices everywhere; the scorer/eval I/O type |
| `scvi-tools` (`scvi`) | single-cell normalization + latent conditioning utility |
| `scanpy` | AnnData I/O, preprocessing, QC, gene-rank / NN-graph plumbing |
| `torch` | Layer A (gene-level transfer) and Layer B (cell sampler) training |
| `h5py`, `hdf5plugin` | H5AD / array read hardware for large corpora |

## Eval / harness

| Package | Why |
|---|---|
| `cell-eval 0.8.2` | legacy local scoring suite used by early runs; not the identified official 2026 scorer |
| `cell-eval2` | official 2026 scorer (`vcc2026`), pinned @`5e64833` v0.16.0 + `pdex==0.3.0`; contract smoke-tested; real scoring on Modal; local `.venv-eval2` rebuildable per header |
| `pdex` | DE computation used by legacy cell-eval (referenced in `_evaluator.py`) |

## Iteration

| Package | Why |
|---|---|
| `pandas`, `numpy`, `scipy` | data plumbing |
| `torchmetrics` | array-metric checks (mse / mae / pearson) early smoke-tests |
| `polars` | DE-frame handling (eval tooling uses polars DataFrames) |
| `seaborn` + `matplotlib` | audit / run report plots |

## Not yet (Phase 2+)

`hf-deep`, `huggingface_hub`, `datasets`, *conditional-generative checkpoints* —
add only if the active strategy reopens that work; not part of the Phase-0
baseline that must fit T4/16GB.

## Notes on normalization

Legacy `cell-eval` upstream `pdex` defaults to `is_log1p=True` for continuous
input and `False` for `allow_discrete` counts (per `_build_pdex_kwargs`). The
exact submission encoding is now a Gate A/B question in
`docs/vcc-two-track-strategy.md`; lock it against the official `cell-eval2`
contract rather than assuming the legacy harness remains equivalent.

## Install (first action of Phase 0)

```bash
# Observatory enrichment venv (Python 3.12 — 3.14 has no torch wheel):
uv venv --python 3.12 .venv
uv pip install openai tavily-python fal-client

# Science track (legacy local eval; official cell-eval2 integration is separate):
uv pip install 'cell-eval==0.8.2'   # in a Python 3.12 env; anndata comes with it
uv pip install -r requirements.txt   # once declared, see src release hygiene
```

## Science venv (2026-08-22, live)

**`.venv-science`** — native **arm64** Python 3.12.8 (downloaded via
`uv python install 3.12`), with legacy `cell-eval 0.8.2` + `anndata` + `scanpy` +
`numba`/`llvmlite` installed and verified. This is the local eval env; it does
not contain the official 2026 `cell-eval2` scorer.

**`.venv-eval2`** — the pinned official-scorer env (`cell-eval2` @`5e64833`
v0.16.0 + `pdex==0.3.0`, Python 3.12), used for the Gate B contract smoke and
the k025 real-data run. Deleted 2026-09-23 to save disk; rebuild with the
command in the status header. Real scoring runs on Modal with the same pin.

**Gotcha that cost a cycle:** the machine is arm64, but the locally installed
Homebrew Python 3.12 is **x86_64 (Rosetta)** — so legacy `cell-eval`'s `llvmlite`
(numba) dependency had no wheel and failed to build from source (same class as
the earlier tiktoken/torch wheel issues). The native arm64 3.12.8 fixes all of
them. Keep the science stack on `.venv-science`, not the Rosetta `.venv`.

```bash
uv python install 3.12            # native arm64 CPython
uv venv --python 3.12.8 .venv-science
uv pip install --python .venv-science/bin/python 'cell-eval==0.8.2'
uv pip install --python .venv-science/bin/python pytest
```

Verify the harness imports cleanly with no packages present (it must degrade,
not crash, when eval/scorer packages aren't installed).

## Observatory enrichment (partner clients)

The `.venv` for enrichment tools needs only lightweight API clients — not the
full torch stack:

```bash
uv pip install openai tavily-python fal-client
```

**Local narration:** prefer [Venice AI](https://venice.ai) for chat completions
during development — private inference, OpenAI-compatible API, keeps hackathon
OpenAI credits for demo runs and TTS. Copy `.env.example` → `.env`, set
`NARRATION_PROVIDER=venice` and `VENICE_INFERENCE_KEY`. Full setup:
[`docs/venice-dev.md`](venice-dev.md).

**Production / Netlify:** `NARRATION_PROVIDER=openai` plus hackathon keys for
Tavily, fal, and `OPENAI_TTS_API_KEY` (Fabric briefings).