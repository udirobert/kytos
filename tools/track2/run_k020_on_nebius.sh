#!/usr/bin/env bash
# k020 Path B -- one-shot GNN cross-lineage training + panel inference on the
# Nebius L40S VM. Run this ON the VM after bootstrap_nebius.sh + data staging.
#
# Prereqs (run from the laptop, not here):
#   modal volume get kytos-vcc k015-essential-transfer/essential_transfer_data.npz /tmp/
#   modal volume get kytos-vcc paired-transfer/delta_matrix_src.npz /tmp/
#   scp /tmp/{essential_transfer_data,delta_matrix_src}.npz ubuntu@<vm>:/data/derived/
#   scp -r tools/track2 data ubuntu@<vm>:~/kytos/            # (or git pull on VM)
#
# Then on the VM:  bash tools/track2/run_k020_on_nebius.sh
set -euo pipefail

REPO="${REPO:-$HOME/kytos}"
DERIVED="${DERIVED:-/data/derived}"
OUT="${OUT:-experiments/k020-gnn-crosslineage}"
EPOCHS="${EPOCHS:-300}"
GENE_CAP="${GENE_CAP:-4000}"   # co-perturbation graph is O(G^2); 4000 genes ~ 64MB dense A

cd "$REPO"
source ~/venvs/kytos/bin/activate   # torch+CUDA from bootstrap_nebius.sh

echo "=== [1/3] train (OOD-proxy validated) ==="
python tools/track2/train_gnn_crosslineage.py \
  --npz "$DERIVED/essential_transfer_data.npz" \
  --gene-names data/raw/vcc2026/gene_names.csv \
  --gene-cap "$GENE_CAP" \
  --epochs "$EPOCHS" --lr 2e-3 --batch 128 \
  --out-dir "$OUT"

echo "=== [2/3] panel K562 deltas for inference ==="
python tools/track2/make_panel_deltas.py \
  --src-matrix "$DERIVED/delta_matrix_src.npz" \
  --gene-names data/raw/vcc2026/gene_names.csv \
  --pert-counts data/raw/vcc2026/pert_counts.csv \
  --out "$DERIVED/panel_k562_deltas.npz"

echo "=== [3/3] predict -> prediction_deltas.npz ==="
python tools/track2/train_gnn_crosslineage.py \
  --predict --ckpt "$OUT/gnn.pt" \
  --panel-deltas "$DERIVED/panel_k562_deltas.npz" \
  --out-dir "$OUT"

echo
echo "DONE. Check OOD gate before shipping:"
echo "  cat $OUT/gnn_eval.json   # gnn cos_ood must clearly beat identity cos_ood"
echo "Get the artifact off the VM (laptop):"
echo "  scp ubuntu@<vm>:$REPO/$OUT/prediction_deltas.npz /tmp/"
echo "  modal volume put kytos-vcc /tmp/prediction_deltas.npz /k020/prediction_deltas.npz"
echo "Then build + prep + submit (Modal): reuse run_k014_trained_model.py on /k020/..."
