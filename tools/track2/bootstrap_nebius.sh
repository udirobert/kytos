#!/usr/bin/env bash
# Track 2 — Nebius VM bootstrap (run once after provisioning).
# See docs/track2-nebius-setup.md §2 for instance spec.
#
# Usage: ssh into the Nebius VM and run:
#   bash bootstrap_nebius.sh
set -euo pipefail

echo "=== [1/4] System packages ==="
sudo apt-get update -qq
sudo apt-get install -y -qq git build-essential tmux htop curl unzip

echo "=== [2/4] GPU sanity check ==="
nvidia-smi
echo "GPU driver OK"

echo "=== [3/4] Python environment ==="
python3 -m venv ~/venvs/kytos
source ~/venvs/kytos/bin/activate
pip install --upgrade pip -q
pip install torch --index-url https://download.pytorch.org/whl/cu124 -q
pip install anndata scanpy numpy scipy scikit-learn pandas pyarrow h5py -q
# Optional: vcc-cli if publishing controls download is needed on-box
# pip install vcc-cli -q

echo "=== [4/4] Clone repo ==="
if [ -d ~/kytos ]; then
    cd ~/kytos && git pull
else
    git clone https://github.com/udirobert/kytos.git ~/kytos
fi

echo ""
echo "=== Bootstrap complete ==="
echo "Next: run 'bash tools/track2/stage_data.sh' to download training data"
echo "Then: 'source ~/venvs/kytos/bin/activate && python tools/track2/train_conditional_mlp.py --paired /data/derived/paired_transfer_train.npz --src-matrix /data/derived/delta_matrix_src.npz'"
