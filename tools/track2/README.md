# Track 2 — Trained Perturbation Models (Nebius GPU)

Goal: Reach top-100 on the VCC 2026 leaderboard (~+0.16 overall score)
by training a model that predicts context-conditioned perturbation deltas.

## Files

| File | Purpose |
|------|---------|
| `bootstrap_nebius.sh` | One-time VM setup (packages, repo clone) |
| `stage_data.sh` | Download/stage training data to persistent disk |
| `train_conditional_mlp.py` | Model 1: Conditional MLP baseline |
| `upload_to_modal.sh` | Push trained artifacts to Modal volume for submission |

## Workflow

```
1. Provision Nebius VM (L40S 48GB, 128GB RAM, 500GB SSD)
2. SSH in, run: bash tools/track2/bootstrap_nebius.sh
3. Stage data:    bash tools/track2/stage_data.sh
   - Copy paired_transfer_train.npz + delta_matrix_src.npz from Modal volume
     (use `modal volume get kytos-vcc /paired-transfer/<file> .` on your laptop,
      then scp to the Nebius box at /data/derived/)
4. Train:         source ~/venvs/kytos/bin/activate
                  python tools/track2/train_conditional_mlp.py \
                    --paired /data/derived/paired_transfer_train.npz \
                    --src-matrix /data/derived/delta_matrix_src.npz \
                    --out-dir experiments/k014-track2-mlp
5. Upload:        bash tools/track2/upload_to_modal.sh experiments/k014-track2-mlp
6. Build + Prep:  modal run -d tools/modal_k014_trained_model.py::build_and_prep
7. Submit:        modal run -d tools/modal_k014_trained_model.py::submit_from_volume
```

## Model Architecture (Conditional MLP)

```
Input:  [target_embedding(128d) ; context_basal_pca(256d)]
Hidden: Linear(384→1024) → ReLU → Linear(1024→1024) → ReLU
Output: Linear(1024→64) → ReLU → Linear(64→18533)
Loss:   MSE + 0.1 × (1 − cosine_similarity)
```

## Evaluation Protocol

- **Context-holdout**: 10 of 47 paired targets held out from hESC training set
- **Metrics**: cosine similarity, DE-logFC Pearson (top-200), magnitude ratio
- **Acceptance**: must beat identity baseline (cosine ~0.126) by ≥0.05 to ship
- **No leaderboard tuning** — submit only after frozen in-corpus winner

## Key Data

- `paired_transfer_train.npz`: 47 paired targets (K562 + hESC deltas + basals)
- `delta_matrix_src.npz`: ~9,900 targets with combined source deltas
- Context basals for A, B, C included in paired npz

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Only 47 paired examples for context transfer | Use all 9.8k K562 samples for embedding pre-training |
| Model overfits to K562 patterns | Context-holdout eval catches this |
| Uncovered targets (28/300) | Fall back to neighbor-imputation tier |
| Magnitude miscalibration | Track magnitude_ratio in eval; tune delta_scale post-hoc |
