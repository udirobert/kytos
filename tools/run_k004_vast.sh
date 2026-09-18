#!/usr/bin/env bash
# Kytos k004 — full 300-target run on Vast/RunPod 32GB (not on 8GB Mac)
# - Downloads Kaggle dataset udingethe/vcc2026-controls (632 MB, private) via KAGGLE_API_TOKEN
# - Runs notebooks/kaggle_k004_smoke.py at full scale (360k cells × 18.5k genes, sparse ~8GB data, needs 32GB RAM)
# - Never runs locally; Mac stays thin (orchestration + docs only) per AGENTS.md:1
#
# Usage on Vast/RunPod (Ubuntu 22.04, 32GB RAM, pick ≥32GB system RAM):
#   export KAGGLE_API_TOKEN=KGAT_xxx  # from .env
#   export VCC_TOKEN=vcc_pat_xxx      # from .env
#   git clone https://github.com/udirobert/kytos.git && cd kytos
#   bash tools/run_k004_vast.sh 2>&1 | tee /tmp/k004_full.log
#
# Or dry-run first: bash tools/run_k004_vast.sh --max-targets 20
#
set -euo pipefail

MAX_TARGETS="${1:-300}"
CONTEXTS="${2:-A,B,C}"
OUT="${3:-experiments/k004-full}"
RAW_DIR="/tmp/vcc2026-controls"

echo "=== k004 Vast full run: max_targets=$MAX_TARGETS contexts=$CONTEXTS out=$OUT ==="
echo "free RAM:"; free -h || vmstat -s | head
echo "disk:"; df -h / | head -5

# 1. deps (no space bloat: pip only, no local H5AD commit)
echo "--- pip install ---"
python3 -m pip install -q anndata scanpy h5py scipy pandas kaggle 2>&1 | tail -5

# 2. Kaggle dataset (private, needs token)
if [[ -z "${KAGGLE_API_TOKEN:-}" ]]; then echo "Set KAGGLE_API_TOKEN env (from .env)"; exit 2; fi
mkdir -p /tmp
if [[ ! -f "$RAW_DIR/gene_names.csv" ]]; then
  echo "--- kaggle download udingethe/vcc2026-controls ---"
  KAGGLE_API_TOKEN="$KAGGLE_API_TOKEN" kaggle datasets download -d udingethe/vcc2026-controls -p /tmp --unzip 2>&1 | tail -20
  # kaggle downloads as zip to /tmp/vcc2026-controls.zip then unzip? handle both
  if [[ -f /tmp/vcc2026-controls.zip ]]; then unzip -q /tmp/vcc2026-controls.zip -d "$RAW_DIR" 2>&1 | tail -5; fi
  # if already unzipped to /tmp, move
  if [[ -d /tmp/vcc2026-controls ]]; then mkdir -p "$RAW_DIR"; mv /tmp/vcc2026-controls/* "$RAW_DIR"/ 2>&1 | tail -5; fi
  ls -lh "$RAW_DIR" | head -10
else
  echo "RAW_DIR already exists $RAW_DIR"
  ls -lh "$RAW_DIR" | head -10
fi

# 3. run smoke at full scale (never on Mac)
echo "--- run notebooks/kaggle_k004_smoke.py ---"
python3 notebooks/kaggle_k004_smoke.py --raw-dir "$RAW_DIR" --max-targets "$MAX_TARGETS" --contexts "$CONTEXTS" --out "$OUT" --mode both

echo "--- outputs ---"
ls -lh "$OUT" | head -20
du -sh "$OUT"/* 2>&1 | head -20

# 4. vcc validation (if vcc installed)
if command -v vcc >/dev/null 2>&1; then
  echo "--- vcc prep --dry-run ---"
  vcc prep --dry-run "$OUT/pred_layer_a_b.h5ad" 2>&1 | tail -20 || echo "dry-run failed (check gene_order / obs cols)"
  if [[ -n "${VCC_TOKEN:-}" ]]; then
    echo "--- vcc submit (≤2/day guardrail) ---"
    echo "Run: vcc submit --help  and check daily limit before live submit"
  fi
else
  echo "vcc not installed — install via: pip install vcc  (needs vcc 0.2.0)"
  echo "Then: vcc prep --dry-run $OUT/pred_layer_a_b.h5ad"
fi

echo "=== done: $OUT ==="
echo "Artifacts to keep (small): $OUT/meta_*.json -> commit to git"
echo "H5ADs stay on Vast/Kaggle, not in git (experiments/**/*.h5ad gitignored)"
