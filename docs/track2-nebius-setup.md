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
training scripts live in `tools/track2/` (to be written); keep them in
git so provenance matches the Observatory record.

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
Modal:  tools/run_k013_transfer_model.py loads the .npz, drops it into
        build_context_predictions as the 'real' tier → .h5ad → vcc prep
      → submit_from_volume (unchanged flow)
```

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
