"""Track 2 — Conditional MLP baseline for context-conditioned delta prediction.

Trains on paired (source_delta, context_basal) -> target_delta examples
from Replogle K562 + 2025 Atlas, then predicts deltas for the 2026 panel
targets across all three contexts.

Architecture (per docs/track2-nebius-setup.md §5):
  Input:  [target_embedding (128d) ; context_basal_pca (256d)]
  Hidden: Linear(384 -> 1024) -> ReLU -> Linear(1024 -> 1024) -> ReLU
  Output: Linear(1024 -> 64) -> ReLU -> Linear(64 -> G)   [rank-64 bottleneck]
  Loss:   MSE + 0.1 * (1 - cosine_similarity)

Training data:
  - ~9,866 K562 examples:  (emb[t], basal_k562) -> delta_k562[t]
  - ~50   hESC examples:   (emb[t], basal_hesc)  -> delta_hesc[t]
  (47 targets appear in both; 3 are hESC-only)

Eval (frozen before training):
  - Context-holdout: leave out 10 of the 47 paired targets; train on
    remaining 37 + all K562-only; predict hESC deltas for held-out 10.
  - Metrics: cosine, DE-logFC Pearson (top-200), magnitude ratio.

Usage:
  python tools/track2/train_conditional_mlp.py \
    --paired experiments/k012-paired-transfer/paired_transfer_train.npz \
    --src-matrix /data/derived/delta_matrix_src.npz \
    --out-dir experiments/k014-track2-mlp \
    --epochs 200 --lr 1e-3 --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:
    print("ERROR: torch not installed. Activate the venv first.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ConditionalMLP(nn.Module):
    """Predicts gene-delta vector from (target_emb, context_basal_pca)."""

    def __init__(
        self,
        n_targets: int,
        emb_dim: int = 128,
        ctx_dim: int = 256,
        hidden: int = 1024,
        bottleneck: int = 64,
        n_genes: int = 18533,
    ):
        super().__init__()
        self.embedding = nn.Embedding(n_targets, emb_dim)
        self.net = nn.Sequential(
            nn.Linear(emb_dim + ctx_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, bottleneck),
            nn.ReLU(),
            nn.Linear(bottleneck, n_genes),
        )

    def forward(self, target_idx: torch.Tensor, ctx_feat: torch.Tensor) -> torch.Tensor:
        emb = self.embedding(target_idx)  # (B, emb_dim)
        x = torch.cat([emb, ctx_feat], dim=-1)  # (B, emb_dim + ctx_dim)
        return self.net(x)  # (B, n_genes)


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------


def hybrid_loss(pred: torch.Tensor, target: torch.Tensor, cos_weight: float = 0.1):
    mse = nn.functional.mse_loss(pred, target)
    cos = 1.0 - nn.functional.cosine_similarity(pred, target, dim=-1).mean()
    return mse + cos_weight * cos


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def prepare_data(
    paired_path: str, src_matrix_path: str | None, n_holdout: int = 10, seed: int = 42
):
    """Load npz files and build train/eval splits.

    Returns dict with all tensors as numpy arrays (caller converts to torch).
    """
    rng = np.random.default_rng(seed)
    paired = np.load(paired_path, allow_pickle=False)

    genes = paired["genes"]
    n_genes = len(genes)
    paired_targets = paired["paired_targets"].tolist()
    vcc_targets = paired["vcc_targets"].tolist()
    contexts = paired["contexts"].tolist()

    delta_k562 = paired["delta_k562"]  # (P, G)
    delta_hesc = paired["delta_hesc"]  # (P, G)
    basal_k562 = paired["basal_k562_log1p"]  # (G,)
    basal_hesc = paired["basal_hesc_log1p"]  # (G,)
    basal_ctx = paired["basal_ctx_log1p"]  # (C, G)

    # Build unified target list: all Replogle targets + atlas-only targets
    if src_matrix_path and Path(src_matrix_path).exists():
        src = np.load(src_matrix_path, allow_pickle=False)
        all_src_targets = src["targets"].tolist()
        all_src_deltas = src["deltas"]  # (N, G)
        # Identify which are K562-only vs atlas
        paired_set = set(paired_targets)
        k562_only_indices = [i for i, t in enumerate(all_src_targets) if t not in paired_set]
        # For paired targets, use the K562 delta from paired npz (identical)
        print(
            f"[data] src_matrix: {len(all_src_targets)} targets, "
            f"{len(k562_only_indices)} K562-only",
            flush=True,
        )
    else:
        # Fallback: use only paired data
        all_src_targets = paired_targets
        all_src_deltas = delta_k562
        k562_only_indices = list(range(len(paired_targets)))
        print("[data] no src_matrix found; using paired-only mode", flush=True)

    # Build target vocabulary
    all_targets = list(dict.fromkeys(all_src_targets))  # preserve order, dedupe
    target_to_idx = {t: i for i, t in enumerate(all_targets)}
    n_targets = len(all_targets)

    # Context feature: random projection of basal log1p vectors
    # Fixed projection matrix (seeded) for reproducibility
    proj_dim = 256
    proj_rng = np.random.default_rng(seed + 1000)
    proj_matrix = proj_rng.standard_normal((n_genes, proj_dim)).astype(np.float32)
    proj_matrix /= np.sqrt(proj_dim)  # approximate isometry scaling

    def project_basal(basal_vec: np.ndarray) -> np.ndarray:
        return basal_vec @ proj_matrix  # (proj_dim,)

    # Basal projections
    basal_k562_proj = project_basal(basal_k562)
    basal_hesc_proj = project_basal(basal_hesc)
    basal_ctx_proj = np.stack([project_basal(basal_ctx[i]) for i in range(len(contexts))])

    # --- Build training examples ---
    # K562 examples: all targets with known K562 delta
    train_target_ids = []
    train_ctx_feats = []
    train_deltas = []

    for i, tgt in enumerate(all_src_targets):
        idx = target_to_idx[tgt]
        train_target_ids.append(idx)
        train_ctx_feats.append(basal_k562_proj)
        train_deltas.append(all_src_deltas[i])

    # hESC examples: paired targets (use delta_hesc)
    for i, tgt in enumerate(paired_targets):
        idx = target_to_idx[tgt]
        train_target_ids.append(idx)
        train_ctx_feats.append(basal_hesc_proj)
        train_deltas.append(delta_hesc[i])

    train_target_ids = np.array(train_target_ids, dtype=np.int64)
    train_ctx_feats = np.array(train_ctx_feats, dtype=np.float32)
    train_deltas = np.array(train_deltas, dtype=np.float32)

    # --- Context-holdout split ---
    # Hold out n_holdout of the paired targets from hESC side
    paired_indices = np.arange(len(paired_targets))
    holdout_indices = rng.choice(
        paired_indices, size=min(n_holdout, len(paired_indices)), replace=False
    )
    # Split: remove held-out hESC examples from training
    n_k562 = len(all_src_targets)
    train_mask = np.ones(len(train_target_ids), dtype=bool)
    for hi in holdout_indices:
        train_mask[n_k562 + hi] = False  # hESC examples are appended after K562

    eval_target_ids = train_target_ids[~train_mask]
    eval_ctx_feats = train_ctx_feats[~train_mask]
    eval_deltas = train_deltas[~train_mask]

    train_target_ids = train_target_ids[train_mask]
    train_ctx_feats = train_ctx_feats[train_mask]
    train_deltas = train_deltas[train_mask]

    print(
        f"[split] train={len(train_target_ids)}, eval={len(eval_target_ids)} "
        f"(holdout={len(holdout_indices)} hESC targets)",
        flush=True,
    )

    return {
        "n_genes": n_genes,
        "n_targets": n_targets,
        "genes": genes,
        "all_targets": all_targets,
        "target_to_idx": target_to_idx,
        "vcc_targets": vcc_targets,
        "contexts": contexts,
        "proj_matrix": proj_matrix,
        "basal_k562_proj": basal_k562_proj,
        "basal_hesc_proj": basal_hesc_proj,
        "basal_ctx_proj": basal_ctx_proj,
        "basal_ctx_log1p": basal_ctx,
        "train_target_ids": train_target_ids,
        "train_ctx_feats": train_ctx_feats,
        "train_deltas": train_deltas,
        "eval_target_ids": eval_target_ids,
        "eval_ctx_feats": eval_ctx_feats,
        "eval_deltas": eval_deltas,
        "holdout_indices": holdout_indices,
        "paired_targets": paired_targets,
        "delta_k562": delta_k562,
        "delta_hesc": delta_hesc,
    }


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------


def evaluate_model(model, data, device, top_k=200):
    """Evaluate on held-out context examples."""
    model.eval()
    tids = torch.tensor(data["eval_target_ids"], dtype=torch.long, device=device)
    ctx = torch.tensor(data["eval_ctx_feats"], dtype=torch.float32, device=device)
    true = torch.tensor(data["eval_deltas"], dtype=torch.float32, device=device)

    with torch.no_grad():
        pred = model(tids, ctx)

    pred_np = pred.cpu().numpy()
    true_np = true.cpu().numpy()

    cosines = []
    de_pearsons = []
    mag_ratios = []
    for i in range(len(pred_np)):
        p, t = pred_np[i], true_np[i]
        # cosine
        norm_p, norm_t = np.linalg.norm(p), np.linalg.norm(t)
        cos = float(p @ t / (norm_p * norm_t + 1e-8)) if norm_p > 1e-8 and norm_t > 1e-8 else 0.0
        cosines.append(cos)
        # DE pearson on top-k by |true delta|
        k = min(top_k, len(t))
        top_idx = np.argsort(np.abs(t))[-k:]
        if np.std(t[top_idx]) > 1e-8 and np.std(p[top_idx]) > 1e-8:
            de_pearsons.append(float(np.corrcoef(p[top_idx], t[top_idx])[0, 1]))
        else:
            de_pearsons.append(0.0)
        # magnitude ratio
        mag_ratios.append(norm_p / (norm_t + 1e-8))

    return {
        "mean_cosine": float(np.mean(cosines)),
        "median_cosine": float(np.median(cosines)),
        "de_pearson": float(np.nanmean(de_pearsons)),
        "magnitude_ratio": float(np.mean(mag_ratios)),
        "n_eval": len(cosines),
        "per_target_cosine": [round(c, 4) for c in cosines],
    }


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(data, epochs=200, lr=1e-3, batch_size=256, seed=42, device="cpu"):
    torch.manual_seed(seed)
    np.random.seed(seed)

    n_targets = data["n_targets"]
    n_genes = data["n_genes"]

    model = ConditionalMLP(
        n_targets=n_targets, emb_dim=128, ctx_dim=256, hidden=1024, bottleneck=64, n_genes=n_genes
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    train_ds = TensorDataset(
        torch.tensor(data["train_target_ids"], dtype=torch.long),
        torch.tensor(data["train_ctx_feats"], dtype=torch.float32),
        torch.tensor(data["train_deltas"], dtype=torch.float32),
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    best_cosine = -1.0
    best_state = None
    patience = 30
    no_improve = 0

    print(
        f"[train] {len(train_ds)} samples, {n_targets} targets, {n_genes} genes, device={device}",
        flush=True,
    )

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for tids, ctx, deltas in train_loader:
            tids, ctx, deltas = tids.to(device), ctx.to(device), deltas.to(device)
            optimizer.zero_grad()
            pred = model(tids, ctx)
            loss = hybrid_loss(pred, deltas)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item() * len(tids)
        scheduler.step()
        avg_loss = epoch_loss / len(train_ds)

        # Evaluate every 10 epochs
        if (epoch + 1) % 10 == 0 or epoch == 0:
            metrics = evaluate_model(model, data, device)
            print(
                f"  epoch {epoch + 1:4d} | loss {avg_loss:.4f} | "
                f"eval cos {metrics['mean_cosine']:.4f} | "
                f"deP {metrics['de_pearson']:.4f} | "
                f"mag {metrics['magnitude_ratio']:.3f}",
                flush=True,
            )
            if metrics["mean_cosine"] > best_cosine:
                best_cosine = metrics["mean_cosine"]
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
            if no_improve >= patience // 10:
                print(f"  [early stop] no improvement for {no_improve * 10} epochs", flush=True)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    print(f"[train] best eval cosine: {best_cosine:.4f}", flush=True)
    return model, best_cosine


# ---------------------------------------------------------------------------
# Export predictions for all 300 VCC targets × 3 contexts
# ---------------------------------------------------------------------------


def export_predictions(model, data, device="cpu"):
    """Generate delta predictions for all VCC panel targets in all contexts."""
    model.eval()
    vcc_targets = data["vcc_targets"]
    contexts = data["contexts"]
    target_to_idx = data["target_to_idx"]
    basal_ctx_proj = data["basal_ctx_proj"]

    # Identify which targets have embeddings (seen during training)
    covered = []
    uncovered = []
    for t in vcc_targets:
        if t in target_to_idx:
            covered.append(t)
        else:
            uncovered.append(t)

    print(f"[export] {len(covered)} covered, {len(uncovered)} uncovered targets", flush=True)

    all_deltas = {}  # context -> {target: delta}
    for ci, ctx in enumerate(contexts):
        ctx_feat = basal_ctx_proj[ci]
        # Batch all covered targets at once for efficiency
        tids = torch.tensor([target_to_idx[t] for t in covered], dtype=torch.long, device=device)
        cfs = torch.tensor(np.tile(ctx_feat, (len(covered), 1)), dtype=torch.float32, device=device)
        with torch.no_grad():
            preds = model(tids, cfs).cpu().numpy()
        all_deltas[ctx] = {tgt: preds[i].astype(np.float32) for i, tgt in enumerate(covered)}

    return all_deltas, covered, uncovered


def save_export(all_deltas, covered, uncovered, data, out_dir: Path, best_cosine: float, args):
    """Save prediction_deltas.npz and model_card.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    contexts = data["contexts"]
    vcc_targets = data["vcc_targets"]
    n_genes = data["n_genes"]

    # Build dense array: (C, T, G) — zeros for uncovered
    C, T = len(contexts), len(vcc_targets)
    deltas_arr = np.zeros((C, T, n_genes), dtype=np.float32)
    coverage_mask = np.zeros((C, T), dtype=bool)

    target_pos = {t: i for i, t in enumerate(vcc_targets)}
    for ci, ctx in enumerate(contexts):
        for tgt, delta in all_deltas[ctx].items():
            ti = target_pos[tgt]
            deltas_arr[ci, ti] = delta
            coverage_mask[ci, ti] = True

    np.savez_compressed(
        out_dir / "prediction_deltas.npz",
        contexts=np.array(contexts),
        vcc_targets=np.array(vcc_targets),
        deltas=deltas_arr,
        coverage_mask=coverage_mask,
    )

    model_card = {
        "model": "ConditionalMLP",
        "run_id": "k014-track2-mlp",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "best_eval_cosine": round(best_cosine, 4),
        "n_train_samples": int(len(data["train_target_ids"])),
        "n_eval_samples": int(len(data["eval_target_ids"])),
        "n_targets_total": data["n_targets"],
        "n_vcc_covered": len(covered),
        "n_vcc_uncovered": len(uncovered),
        "uncovered_targets": uncovered,
        "epochs": args.epochs,
        "lr": args.lr,
        "seed": args.seed,
        "architecture": {
            "emb_dim": 128,
            "ctx_dim": 256,
            "hidden": 1024,
            "bottleneck": 64,
            "n_genes": n_genes,
        },
        "loss": "MSE + 0.1*(1-cosine)",
        "note": "Uncovered targets should fall back to neighbor/fallback tier in builder.",
    }
    (out_dir / "model_card.json").write_text(json.dumps(model_card, indent=2) + "\n")
    print(f"[export] wrote {out_dir / 'prediction_deltas.npz'} and model_card.json", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paired", type=Path, required=True, help="Path to paired_transfer_train.npz")
    ap.add_argument(
        "--src-matrix",
        type=Path,
        default=None,
        help="Path to delta_matrix_src.npz (optional, for full training)",
    )
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / "k014-track2-mlp")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--holdout", type=int, default=10, help="Number of paired targets to hold out for eval"
    )
    ap.add_argument("--device", type=str, default="auto", help="cpu / cuda / auto")
    ap.add_argument(
        "--eval-only", action="store_true", help="Load checkpoint and only run eval + export"
    )
    ap.add_argument("--checkpoint", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    print(f"[device] {device}", flush=True)

    t0 = time.time()
    data = prepare_data(
        str(args.paired),
        str(args.src_matrix) if args.src_matrix else None,
        n_holdout=args.holdout,
        seed=args.seed,
    )

    if args.eval_only and args.checkpoint:
        model = ConditionalMLP(n_targets=data["n_targets"], n_genes=data["n_genes"]).to(device)
        model.load_state_dict(torch.load(args.checkpoint, map_location=device))
        best_cosine = -1.0
    else:
        model, best_cosine = train(
            data,
            epochs=args.epochs,
            lr=args.lr,
            batch_size=args.batch_size,
            seed=args.seed,
            device=device,
        )

    # Save checkpoint
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = args.out_dir / "model.pt"
    torch.save(model.state_dict(), ckpt_path)
    print(f"[save] checkpoint -> {ckpt_path}", flush=True)

    # Final eval
    final_metrics = evaluate_model(model, data, device)
    print(
        f"\n[final eval] cosine={final_metrics['mean_cosine']:.4f} "
        f"deP={final_metrics['de_pearson']:.4f} "
        f"mag_ratio={final_metrics['magnitude_ratio']:.3f}",
        flush=True,
    )

    # Compare against baselines
    print("\n--- Baseline comparison (identity = raw K562 transplant) ---")
    # Identity baseline: predict delta_k562 for hESC targets
    holdout_idx = data["holdout_indices"]
    cosines_identity = []
    for hi in holdout_idx:
        pred_id = data["delta_k562"][hi]
        true_id = data["delta_hesc"][hi]
        norm_p, norm_t = np.linalg.norm(pred_id), np.linalg.norm(true_id)
        cos = float(pred_id @ true_id / (norm_p * norm_t + 1e-8)) if norm_p > 1e-8 else 0.0
        cosines_identity.append(cos)
    print(f"  identity cosine: {np.mean(cosines_identity):.4f}")
    print(f"  model cosine:    {final_metrics['mean_cosine']:.4f}")
    improvement = final_metrics["mean_cosine"] - np.mean(cosines_identity)
    print(f"  improvement:     {improvement:+.4f}")

    # Export predictions
    all_deltas, covered, uncovered = export_predictions(model, data, device)
    save_export(all_deltas, covered, uncovered, data, args.out_dir, best_cosine, args)

    # Write eval report
    report = {
        "run_id": "k014-track2-mlp",
        "created": time.strftime("%Y-%m-%d"),
        "headline": f"ConditionalMLP context-holdout cosine={final_metrics['mean_cosine']:.4f} "
        f"vs identity={np.mean(cosines_identity):.4f}",
        "eval_metrics": final_metrics,
        "identity_baseline_cosine": float(np.mean(cosines_identity)),
        "improvement_over_identity": float(improvement),
        "n_covered_vcc_targets": len(covered),
        "n_uncovered_vcc_targets": len(uncovered),
        "elapsed_s": round(time.time() - t0, 1),
        "device": device,
    }
    report_path = args.out_dir / "eval_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n[report] {report_path}", flush=True)
    print(f"[done] total time: {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
