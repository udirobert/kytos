#!/usr/bin/env bash
# Run the full k001 enrichment pipeline (Developer A critical path).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${1:-experiments/k001-mean-shift-baseline}"
PY="$ROOT/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "error: missing $PY — run: uv pip install --python .venv/bin/python openai tavily-python fal-client" >&2
  exit 1
fi

cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  echo "[run_enrichment] loaded $ENV_FILE"
fi

missing=()
if [[ -z "${VENICE_INFERENCE_KEY:-${VENICE_API_KEY:-}}" && -z "${OPENAI_API_KEY:-}" ]]; then
  missing+=("VENICE_INFERENCE_KEY or OPENAI_API_KEY")
fi
[[ -z "${TAVILY_API_KEY:-}" ]] && missing+=("TAVILY_API_KEY")
[[ -z "${FAL_KEY:-${FAL_API_KEY:-}}" ]] && missing+=("FAL_KEY")

if ((${#missing[@]})); then
  echo "[run_enrichment] warning: missing env: ${missing[*]} (those steps will degrade)" >&2
fi

"$PY" -m kytos.audit --run "$RUN"
"$PY" -m kytos.eval.facts --run "$RUN"

cd "$ROOT/tools"
"$PY" render_narrative.py --run "../$RUN"
"$PY" enrich_literature.py --run "../$RUN"
"$PY" pioneer_ner.py --run "../$RUN"
"$PY" render_visuals.py --run "../$RUN"
"$PY" render_briefing.py --run "../$RUN"

cd "$ROOT"
"$PY" frontend/build.py --out frontend/dist --experiments experiments/ 2>/dev/null || true
"$PY" tools/holo_audit.py --run "../$RUN" || true

cd "$ROOT"
"$PY" -m kytos.eval.facts --run "$RUN"
echo "[run_enrichment] done — rebuild frontend: $PY frontend/build.py"
