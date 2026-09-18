#!/usr/bin/env bash
# Upload trained model artifacts from local (or Nebius) to Modal volume.
# Run this after training completes and you want to deploy to Modal for submission.
#
# Prerequisites:
#   - modal CLI installed and authenticated
#   - prediction_deltas.npz and model_card.json exist in experiments/k014-track2-mlp/
#
# Usage: bash tools/track2/upload_to_modal.sh [experiment_dir]

set -euo pipefail

EXPERIMENT_DIR="${1:-experiments/k014-track2-mlp}"

if [ ! -f "${EXPERIMENT_DIR}/prediction_deltas.npz" ]; then
    echo "ERROR: ${EXPERIMENT_DIR}/prediction_deltas.npz not found"
    echo "Run train_conditional_mlp.py first."
    exit 1
fi

echo "Uploading to Modal volume kytos-vcc at /kytos-vol/k014/ ..."

modal volume put kytos-vcc /k014/prediction_deltas.npz "${EXPERIMENT_DIR}/prediction_deltas.npz"
modal volume put kytos-vcc /k014/model_card.json "${EXPERIMENT_DIR}/model_card.json" 2>/dev/null || true

echo "Done. Now run:"
echo "  modal run -d tools/modal_k014_trained_model.py::build_and_prep"
