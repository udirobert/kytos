# Track 2 — Nebius provisioning + training-data spec

Companion to `docs/vcc-two-track-strategy.md`. Concrete setup for the
top-100 track: a trained perturbation model on a rented Nebius GPU VM.
Everything here assumes the Modal pipeline stays the build/submit path —
Nebius only produces trained-model artifacts (`.npz` weights / delta
matrices) that Modal-side builders consume.

## 1. Instance

| | Dev / conditional-MLP + GEARS | If scGPT fine-tune later |
|---|---|---|
| GPU | L40S 48 GB (A100 80 GB if priced close) | H100 |
| vCPU / RAM | 16 vCPU / 128 GB | 32 vCPU / 256 GB |
| Disk | 500 GB persistent SSD | 1 TB |
| Image | Nebius marketplace Ubuntu 24.04 + CUDA 12.x + drivers | same |
| Access | SSH key; open only port 22 | same |

Notes:

- 128 GB system RAM is for data staging, not training: the Atlas h5ad
  (6.5 GB) plus dense intermediate matrices want headroom.
- Persistent disk is the whole point — checkpoints, extracted training
  tensors, and corpus copies must survive stop/start. Take a snapshot
  after bootstrap so a rebuild is minutes.
- Provision via Nebius console, `nebius` CLI, or Terraform — whichever
  the account already uses. No special quota needed for a single VM.

## 2. Bootstrap script (run once on the VM)

```bash
# system
sudo apt-get update && sudo apt-get install -y git build-essential tmux htop
nvidia-smi   # sanity: driver + GPU visible

# python env
python3 -m venv ~/venvs/kytos && source ~/venvs/kytos/bin/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install anndata scanpy numpy scipy scikit-learn pandas pyarrow h5py
pip install vcc-cli   # if publishing controls download is needed on-box
```

Repo: `git clone https://github.com/udirobert/kytos.git ~/kytos` — the
training scripts live in `tools/track2/` (written, smoke-tested locally in
paired-only mode; see the README there); keep them in git so provenance
matches the Observatory record.

Logging: plain CSV + JSON metrics files committed back to
`experiments/k013-*/` — no wandb dependency unless wanted.

## 3. Training-data layout

Stage under `/data/` on the persistent disk:

```
/data/raw/
  atlas/adata_Validation.h5ad          # 6.5 GB — copy from Modal volume or re-download
  replogle/K562_gwps_raw_bulk_01.h5ad  # figshare 35774443 (358 MB)
  replogle/RPE1 arm                    # lineage-matched option for context B
  vcc2026/context_{A,B,C}.h5ad         # 2026 controls (3 × ~200 MB)
/data/derived/
  paired_transfer_train.npz            # output of tools/extract_paired_transfer.py
  context_basal.npy                    # 3 × 18,533 control-mean vectors
  delta_matrix_src.npz                 # all source deltas (Replogle ⊕ Atlas), [n_targets × 18,533]
  splits.json                          # held-out target list + context split, frozen
```

`tools/extract_paired_transfer.py` (Track 1, Modal) produces the same
`paired_transfer_train.npz` — build it once, use it on both tracks so
Track-2 eval is directly comparable to Track-1 LOO numbers.

## 4. Eval splits (freeze before training)

- **Target holdout**: ~30 of the 300 VCC targets (10%) never used in
  training — the in-corpus proxy for "unseen perturbation".
- **Context holdout**: train on source contexts (K562/Atlas-hESC),
  evaluate transfer into 2026 A/B/C control basals — the proxy for
  "unseen context". The final eval is 3 unseen cell lines, so this is
  the split that matters.
- Metrics: cosine(delta_hat, delta_true), DE-logFC Pearson on true-DE
  genes, ||delta_hat||/||delta_true|| magnitude calibration — same
  harness as `docs/k012-layer-a-pipeline.md`, so Track-1 vs Track-2
  comparisons are apples-to-apples.
- Rule unchanged: **no tuning on leaderboard scores**. Submission only
  after a frozen in-corpus winner.

## 5. Model order (same as strategy doc, made concrete)

1. **Conditional MLP baseline** — input: [learned target embedding (128d);
   context basal vector reduced to ~256d PCA]. Output: delta over 18,533
   genes via a low-rank head (e.g. 18,533 ← rank-64 bottleneck ← hidden
   1024) to keep parameter count sane. Loss: MSE + 0.1·(1−cosine).
   Trains in hours on L40S. This is the reference every fancier model
   must beat.
2. **GEARS-class GNN** — gene-interaction graph from STRING (already in
   repo from k007), target-conditioned message passing over the delta
   space. Strong literature track record on unseen-target generalization.
3. **scGPT / scFoundation fine-tune** — only if 1–2 plateau below the
   top-100 bar and pretrained weights are license-clean.

## 6. Path back to submission

```
Nebius: trained model → predicted delta matrix [300 × 18,533] per context
      → export prediction_deltas.npz (+ model card JSON)
Modal:  tools/run_k014_trained_model.py loads the .npz, drops it into
        build_context_predictions as the 'real' tier → .h5ad → vcc prep
      → submit_from_volume (unchanged flow)
```

(k014 is the run-ID prefix for Track-2 trained-model work; k013 was taken by
the per-context delta-scale experiment.)

The .npz is small (~22 MB per context at float32) — scp or Modal volume
`put`. The Nebius box never touches `vcc submit`.

## 7. Honest risks

- **The 50-pair overlap problem applies here too** — a trained model
  learns K562→hESC transfer from the same thin paired set, OR learns
  "predict a good K562-like delta" and relies on Track-1-style context
  conditioning for the rest. The context-holdout split is designed to
  catch fooling ourselves.
- **pds=0.70 may require single-cell training signal**, not pseudobulk —
  Atlas perturbed cells are the only true-sc source we have; worth
  including per-cell residuals, not just mean deltas.
- **Cost**: L40S-class is ~$1–2/hr; a week of iteration is a few hundred
  dollars worst case. Checkpoint + snapshot early so stop/start is cheap.

## 8. Experiment log

### k014-run-1: Conditional MLP baseline (2026-09-18) — NEGATIVE

- **Setup**: L40S VM (Nebius, eu-north1, project-e00sz92bpr005x5c3r80zr),
  CUDA 12.4, torch 2.6.0. Data: `paired_transfer_train.npz` (47 paired
  targets) + `delta_matrix_src.npz` (9,869 targets, mostly K562-only).
- **Config**: 200 epochs (early-stopped at ~90), lr=1e-3, batch=256,
  emb_dim=128, ctx_dim=256, hidden=1024, bottleneck=64.
- **Results**: best eval cosine = 0.0425 (10 held-out hESC targets).
  Identity baseline (raw K562 transplant) cosine = 0.1406.
  **Improvement over identity: −0.098** (model is worse than doing nothing).
  Magnitude ratio collapsed to 0.35 (model predicts near-zero deltas).
- **Diagnosis**: With only 47 paired examples and 9,822 K562-only targets,
  the model has no cross-context signal to learn. It converges to predicting
  small-magnitude noise. The architecture is sound but the data is
  fundamentally insufficient for this task.
- **Conclusion**: Do NOT submit. The conditional MLP baseline confirms that
  naive paired transfer (even with a learned model) cannot beat identity
  transplant on this data. Need either (a) much more paired data across
  contexts, or (b) a fundamentally different approach (e.g., GEARS-style
  GNN that leverages gene-gene interaction structure, or foundation-model
  fine-tuning on per-cell Atlas data).

### VM provisioning notes (for future sessions)

- **Profile**: `nebius profile create kytos --auth-method federation`
  → opens browser OAuth → select account → picks tenant/project.
- **Current tenant**: tenant-e00znds1hwpckd5vna (NOT the old suspended one)
- **Current project**: project-e00sz92bpr005x5c3r80zr
- **Subnet**: vpcsubnet-e00pbj53wtjbf7c6e9 (default-subnet-od2iiilq)
- **SSH security group**: vpcsecuritygroup-e00ac0vv3g60xcp6h7
  (name: kytos-ssh-sg, allows TCP/22 from 0.0.0.0/0)
- **Instance spec**: gpu-l40s-a / 1gpu-16vcpu-64gb / 500GB network_ssd /
  image computeimage-e00q003g5k851wjgpn (Ubuntu 24.04 + CUDA 12)
- **SSH user**: `ubuntu` (NOT root — cloud-init root key injection is
  unreliable on this image; use top-level `ssh_authorized_keys` or
  `users: [{name: ubuntu, ...}]`)
- **Cloud-init that works**:
  ```yaml
  #cloud-config
  users:
    - name: ubuntu
      ssh_authorized_keys:
        - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEsq2UpnLyOLm2rr0gf1pH2Qf8ykKZTK7Vq9bnZSLz2q
      sudo: ALL=(ALL) NOPASSWD:ALL
      shell: /bin/bash
  ```
- **To recreate** (instance was deleted after k014-run-1 to save cost):
  ```bash
  nebius compute instance create \
    --parent-id project-e00sz92bpr005x5c3r80zr \
    --name kytos-track2-gpu \
    --resources-platform gpu-l40s-a \
    --resources-preset 1gpu-16vcpu-64gb \
    --boot-disk-attach-mode read_write \
    --boot-disk-managed-disk-name kytos-track2-disk \
    --boot-disk-managed-disk-source-image-id computeimage-e00q003g5k851wjgpn \
    --boot-disk-managed-disk-size-gibibytes 500 \
    --boot-disk-managed-disk-type network_ssd \
    --network-interfaces '[{"name":"eth0","subnet_id":"vpcsubnet-e00pbj53wtjbf7c6e9","ip_address":{},"public_ip_address":{},"security_groups":[{"id":"vpcsecuritygroup-e00jth18f0j9zbct6g"},{"id":"vpcsecuritygroup-e00ac0vv3g60xcp6h7"}]}]' \
    --cloud-init-user-data "$(cat <<'EOF'
  #cloud-config
  users:
    - name: ubuntu
      ssh_authorized_keys:
        - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEsq2UpnLyOLm2rr0gf1pH2Qf8ykKZTK7Vq9bnZSLz2q
      sudo: ALL=(ALL) NOPASSWD:ALL
      shell: /bin/bash
  EOF
  )" \
    --async
  ```
- **Data staging**: `modal volume get kytos-vcc /paired-transfer/{file} /tmp/`
  then `scp /tmp/{file} ubuntu@<ip>:/data/derived/`
- **Cost**: ~$0.50–1.00/hr for L40S 16vCPU/64GB. Delete when not training.
