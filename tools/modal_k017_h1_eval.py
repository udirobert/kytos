"""Modal k017: offline H1-based context-C transfer evaluation.

Uses persisted artifacts on the kytos-vcc Modal volume:
  /kytos-vol/h1-2025-train/h1_train_deltas.npz
  /kytos-vol/paired-transfer/paired_transfer_train.npz
  /kytos-vol/paired-transfer/delta_matrix_src.npz

This evaluates whether a K562 -> H1 transfer map trained on the 2025 H1
training set improves prediction of held-out 2025 H1 validation deltas
relative to identity K562 deltas. It does NOT submit anything.

Run:
  modal run tools/modal_k017_h1_eval.py::inspect_inputs
  modal run tools/modal_k017_h1_eval.py::evaluate_h1_transfer
"""

from __future__ import annotations

import json
import time

import modal

app = modal.App("kytos-k017-h1-eval")
vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

IMAGE = modal.Image.debian_slim().pip_install("numpy", "scipy")

H1_TRAIN = "/kytos-vol/h1-2025-train/h1_train_deltas.npz"
PAIRED = "/kytos-vol/paired-transfer/paired_transfer_train.npz"
SRC_MATRIX = "/kytos-vol/paired-transfer/delta_matrix_src.npz"
OUT_DIR = "/kytos-vol/k017-h1-eval"


def _norm_rows(x):
    return (x * x).sum(axis=1) ** 0.5


def _topk_cosine(pred, true, k=200):
    import numpy as np

    vals = []
    k = min(k, true.shape[1])
    for i in range(true.shape[0]):
        t = true[i]
        idx = np.argpartition(np.abs(t), -k)[-k:]
        p = pred[i, idx]
        tt = t[idx]
        npred = float(np.linalg.norm(p))
        ntrue = float(np.linalg.norm(tt))
        vals.append(float(p @ tt / (npred * ntrue)) if npred > 1e-12 and ntrue > 1e-12 else 0.0)
    return float(np.mean(vals))


def _pearson_mean(pred, true):
    import numpy as np

    vals = []
    for i in range(len(pred)):
        p = pred[i]
        t = true[i]
        if p.std() < 1e-12 or t.std() < 1e-12:
            vals.append(0.0)
        else:
            vals.append(float(np.corrcoef(p, t)[0, 1]))
    return float(np.nanmean(vals))


def _metrics(pred, true):
    import numpy as np

    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    pred_norm = _norm_rows(pred)
    true_norm = _norm_rows(true)
    return {
        "top50_cos": _topk_cosine(pred, true, 50),
        "top200_cos": _topk_cosine(pred, true, 200),
        "top500_cos": _topk_cosine(pred, true, 500),
        "pearson_mean": _pearson_mean(pred, true),
        "delta_mse": float(np.mean((pred - true) ** 2)),
        "pred_norm_median": float(np.median(pred_norm)),
        "true_norm_median": float(np.median(true_norm)),
        "scale_ratio_pred_over_true_median": float(
            np.median(pred_norm / np.maximum(true_norm, 1e-12))
        ),
    }


def _with_target_reset(pred, targets, gene_index, source=None, value=-2.5):
    """Set the target gene coordinate to a fixed negative KD effect or source value."""
    import numpy as np

    out = np.array(pred, copy=True)
    for i, tgt in enumerate(targets):
        j = gene_index.get(tgt)
        if j is None:
            continue
        if source is not None:
            out[i, j] = source[i, j]
        else:
            out[i, j] = value
    return out


def _fit_global_scalar(X_train, Y_train):
    return float((X_train * Y_train).sum() / ((X_train**2).sum() + 1e-12))


def _fit_lowrank_from_bases(Bx, By, X_train, Y_train, rank):
    import numpy as np

    Bx = Bx[:rank].astype(np.float32)
    By = By[:rank].astype(np.float32)
    Xp = X_train @ Bx.T
    Yp = Y_train @ By.T
    lam = max(1.0, 0.1 * float(np.trace(Xp.T @ Xp)) / max(rank, 1))
    W = np.linalg.solve(Xp.T @ Xp + lam * np.eye(rank, dtype=np.float32), Xp.T @ Yp)

    def transform(X):
        return ((X.astype(np.float32) @ Bx.T) @ W) @ By

    return transform, rank


@app.function(image=IMAGE, volumes={"/kytos-vol": vol}, timeout=60 * 20, cpu=2, memory=4096)
def inspect_inputs() -> dict:
    import numpy as np

    out = {}
    h1 = np.load(H1_TRAIN, allow_pickle=True)
    out["h1_train"] = {k: list(getattr(h1[k], "shape", ())) for k in h1.files}

    paired = np.load(PAIRED, allow_pickle=True)
    out["paired"] = {k: list(getattr(paired[k], "shape", ())) for k in paired.files}

    src = np.load(SRC_MATRIX, allow_pickle=True)
    out["src_matrix_keys"] = list(src.files)
    out["src_matrix"] = {k: list(getattr(src[k], "shape", ())) for k in src.files}

    src_target_key = next(k for k in src.files if "target" in k.lower())
    src_gene_key = next(
        (k for k in src.files if k.lower() in {"genes", "gene_names", "gene"}), None
    )
    out["src_target_key"] = src_target_key
    out["src_gene_key"] = src_gene_key
    src_targets = {str(t).strip().upper() for t in src[src_target_key]}
    h1_targets = {str(t).strip().upper() for t in h1["targets"]}
    paired_targets = {str(t).strip().upper() for t in paired["paired_targets"]}

    out["overlap"] = {
        "h1_train_total": len(h1_targets),
        "h1_train_in_src_matrix": len(h1_targets & src_targets),
        "h1_train_missing_from_src_matrix": sorted(h1_targets - src_targets),
        "paired_total": len(paired_targets),
        "paired_in_src_matrix": len(paired_targets & src_targets),
        "paired_in_h1_train": sorted(paired_targets & h1_targets),
    }

    print(json.dumps(out, indent=2)[:12000], flush=True)
    vol.commit()
    return out


@app.function(image=IMAGE, volumes={"/kytos-vol": vol}, timeout=60 * 60, cpu=8, memory=16384)
def evaluate_h1_transfer() -> dict:
    import os

    import numpy as np

    t0 = time.time()

    h1 = np.load(H1_TRAIN, allow_pickle=True)
    paired = np.load(PAIRED, allow_pickle=True)
    src = np.load(SRC_MATRIX, allow_pickle=True)

    # delta_matrix_src.npz and paired_transfer_train.npz are already aligned to
    # the 2026 gene order.
    gene_order = [str(g) for g in paired["genes"]]
    gene_index = {g: i for i, g in enumerate(gene_order)}
    n_genes = len(gene_order)
    if int(src["deltas"].shape[1]) != n_genes:
        raise ValueError(f"src matrix has {src['deltas'].shape[1]} genes, expected {n_genes}")

    h1_genes = [str(g) for g in h1["genes"]]
    h1_to_src = np.array([gene_index.get(g, -1) for g in h1_genes], dtype=np.int64)
    valid_h1 = h1_to_src >= 0

    h1_targets = [str(t).strip().upper() for t in h1["targets"]]
    h1_deltas_raw = h1["deltas"].astype(np.float32)

    src_targets = [str(t).strip().upper() for t in src["targets"]]
    src_target_idx = {t: i for i, t in enumerate(src_targets)}
    src_deltas = src["deltas"].astype(np.float32)

    train_pairs = []
    for i, tgt in enumerate(h1_targets):
        if tgt in src_target_idx:
            train_pairs.append((tgt, i, src_target_idx[tgt]))

    train_targets = [p[0] for p in train_pairs]
    train_target_set = set(train_targets)
    X_train = np.stack([src_deltas[p[2]] for p in train_pairs]).astype(np.float32)
    Y_train = np.zeros((len(train_pairs), n_genes), dtype=np.float32)
    for row, (_, h1_i, _) in enumerate(train_pairs):
        Y_train[row, h1_to_src[valid_h1]] = h1_deltas_raw[h1_i][valid_h1]

    val_targets = [str(t).strip().upper() for t in paired["paired_targets"]]
    keep_val = np.array([t not in train_target_set for t in val_targets], dtype=bool)
    X_val_all = paired["delta_k562"].astype(np.float32)
    Y_val_all = paired["delta_hesc"].astype(np.float32)
    X_val = X_val_all[keep_val]
    Y_val = Y_val_all[keep_val]
    val_targets = [t for t, keep in zip(val_targets, keep_val) if keep]

    results = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_genes": n_genes,
        "n_h1_train_targets": len(h1_targets),
        "n_train_pairs": len(train_pairs),
        "n_val_targets": len(val_targets),
        "train_targets_sample": train_targets[:30],
        "val_targets": val_targets,
        "missing_h1_train_from_src": sorted(set(h1_targets) - set(train_targets)),
        "metrics": {},
        "elapsed_s": 0.0,
    }

    if len(train_pairs) < 20 or len(val_targets) < 5:
        results["error"] = "Not enough training/validation pairs"
        os.makedirs(OUT_DIR, exist_ok=True)
        out_path = f"{OUT_DIR}/h1_transfer_eval.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        vol.commit()
        print(json.dumps(results, indent=2)[:12000], flush=True)
        return results

    # Baselines
    results["metrics"]["identity"] = _metrics(X_val, Y_val)

    s = _fit_global_scalar(X_train, Y_train)
    results["metrics"]["global_scalar"] = {**_metrics(s * X_val, Y_val), "scale": s}

    # Per-gene shrinkage, same family as k015 but trained on H1 pairs.
    Xf = X_train.astype(np.float64)
    Yf = Y_train.astype(np.float64)
    den = (Xf**2).sum(axis=0)
    s_gene = (Xf * Yf).sum(axis=0) / (den + 1e-12)
    tau = float(np.median(den[den > 0])) if np.any(den > 0) else 1.0
    w = den / (den + tau + 1e-12)
    s_gene_shrunk = s + w * (s_gene - s)
    results["metrics"]["per_gene_shrunk"] = {
        **_metrics(X_val * s_gene_shrunk[np.newaxis, :].astype(np.float32), Y_val),
        "tau": tau,
        "s_global": s,
    }

    # Low-rank transfer. Compute SVD bases once, using max rank constrained by train size.
    best_name = None
    best_top200 = -1.0
    max_rank = min(64, max(1, len(train_pairs) - 1))
    try:
        _, _, vt_x = np.linalg.svd(X_train.astype(np.float64), full_matrices=False)
        _, _, vt_y = np.linalg.svd(Y_train.astype(np.float64), full_matrices=False)
    except Exception as exc:
        vt_x = vt_y = None
        results["svd_error"] = str(exc)

    preds_by_rank = {}
    if vt_x is not None and vt_y is not None:
        for rank in [2, 4, 8, 16, 32, 64]:
            if rank > max_rank:
                continue
            try:
                transform, used_rank = _fit_lowrank_from_bases(vt_x, vt_y, X_train, Y_train, rank)
                pred = transform(X_val)
                preds_by_rank[rank] = pred
                m = _metrics(pred, Y_val)
                m["rank"] = used_rank
                name = f"lowrank_{rank}"
                results["metrics"][name] = m

                pred_self_src = _with_target_reset(pred, val_targets, gene_index, source=X_val)
                results["metrics"][name + "_selfsrc"] = _metrics(pred_self_src, Y_val)

                pred_self_fixed = _with_target_reset(pred, val_targets, gene_index, value=-2.5)
                results["metrics"][name + "_selffixed"] = _metrics(pred_self_fixed, Y_val)

                if m["top200_cos"] > best_top200:
                    best_top200 = m["top200_cos"]
                    best_name = name
            except Exception as exc:
                results["metrics"][f"lowrank_{rank}"] = {"error": str(exc)}

    # Blends of identity and low-rank may preserve target-specific spikes.
    if best_name is not None:
        rank = int(best_name.split("_")[1])
        pred_lr = preds_by_rank.get(rank)
        if pred_lr is not None:
            for alpha in [0.25, 0.5, 0.75]:
                pred = alpha * pred_lr + (1.0 - alpha) * X_val
                results["metrics"][f"blend_a{str(alpha).replace('.', 'p')}"] = _metrics(pred, Y_val)
                pred_self = _with_target_reset(pred, val_targets, gene_index, source=X_val)
                blend_self_name = f"blend_a{str(alpha).replace('.', 'p')}_selfsrc"
                results["metrics"][blend_self_name] = _metrics(pred_self, Y_val)

    # Rank top methods by top200 cosine.
    ranking = []
    for name, m in results["metrics"].items():
        if isinstance(m, dict) and "top200_cos" in m:
            ranking.append((name, m["top200_cos"]))
    ranking.sort(key=lambda x: x[1], reverse=True)
    results["ranking_top200_cos"] = ranking[:20]
    results["elapsed_s"] = round(time.time() - t0, 1)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = f"{OUT_DIR}/h1_transfer_eval.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    vol.commit()

    print(json.dumps(results, indent=2)[:16000], flush=True)
    return results


def _map_to_val_genes(mat, src_genes, val_genes):
    import numpy as np

    src_idx = {g: i for i, g in enumerate(src_genes)}
    cols = np.array([src_idx.get(g, -1) for g in val_genes], dtype=np.int64)
    valid = cols >= 0
    out = np.zeros((mat.shape[0], len(val_genes)), dtype=np.float32)
    out[:, valid] = mat[:, cols[valid]]
    return out


@app.function(image=IMAGE, volumes={"/kytos-vol": vol}, timeout=60 * 60, cpu=8, memory=32768)
def sweep_h1_transfer() -> dict:
    """Delta-level sweep: self-gene handling x delta_scale on held-out H1 validation."""
    import os

    import numpy as np

    t0 = time.time()
    h1 = np.load(H1_TRAIN, allow_pickle=True)
    paired = np.load(PAIRED, allow_pickle=True)
    src = np.load(SRC_MATRIX, allow_pickle=True)

    val_genes = [str(g) for g in paired["genes"]]
    val_index = {g: i for i, g in enumerate(val_genes)}
    n_genes = len(val_genes)

    # Training source: delta_matrix_src rows for H1-training targets, mapped to val genes.
    src_targets = [str(t).strip().upper() for t in src["targets"]]
    src_target_idx = {t: i for i, t in enumerate(src_targets)}
    h1_targets = [str(t).strip().upper() for t in h1["targets"]]
    h1_genes = [str(g) for g in h1["genes"]]

    train_pairs = []
    for i, tgt in enumerate(h1_targets):
        if tgt in src_target_idx:
            train_pairs.append((tgt, i, src_target_idx[tgt]))
    if len(train_pairs) < 20:
        return {"error": f"too few train pairs: {len(train_pairs)}"}

    X_train_raw = np.stack([src["deltas"][p[2]] for p in train_pairs]).astype(np.float32)
    # The source matrix is already in the same 2026/validation gene order.
    X_train = _map_to_val_genes(X_train_raw, val_genes, val_genes)

    Y_train = np.zeros((len(train_pairs), n_genes), dtype=np.float32)
    h1_idx = {g: i for i, g in enumerate(h1_genes)}
    h1_to_val = np.array([h1_idx.get(g, -1) for g in val_genes], dtype=np.int64)
    valid_h1 = h1_to_val >= 0
    for row, (_, h1_i, _) in enumerate(train_pairs):
        Y_train[row, valid_h1] = h1["deltas"][h1_i][h1_to_val[valid_h1]].astype(np.float32)

    # Self-gene effect from training data only (no val leakage).
    self_vals = []
    for tgt, h1_i, _ in train_pairs:
        j = val_index.get(tgt)
        if j is not None:
            self_vals.append(float(Y_train[train_pairs.index((tgt, h1_i, _)), j]))
    self_median = float(np.median(self_vals)) if self_vals else -1.5

    # Fit rank-64 low-rank map.
    rank = 64
    _, _, vt_x = np.linalg.svd(X_train, full_matrices=False)
    _, _, vt_y = np.linalg.svd(Y_train, full_matrices=False)
    Bx = vt_x[:rank].astype(np.float32)
    By = vt_y[:rank].astype(np.float32)
    Xp = X_train @ Bx.T
    Yp = Y_train @ By.T
    lam = max(1.0, 0.1 * float(np.trace(Xp.T @ Xp)) / max(rank, 1))
    W = np.linalg.solve(Xp.T @ Xp + lam * np.eye(rank, dtype=np.float32), Xp.T @ Yp)

    def transform(x):
        return ((x.astype(np.float32) @ Bx.T) @ W) @ By

    # Validation source/true from paired transfer npz.
    val_targets = [str(t).strip().upper() for t in paired["paired_targets"]]
    X_val = paired["delta_k562"].astype(np.float32)
    Y_val = paired["delta_hesc"].astype(np.float32)

    metrics = {}
    pred_lr = transform(X_val)
    base_mats = {
        "identity": X_val,
        "h1lr64": pred_lr,
    }

    def set_self(mat, value, scale=1.0):
        out = mat.copy()
        for i, tgt in enumerate(val_targets):
            j = val_index.get(tgt)
            if j is not None:
                out[i, j] = value * scale
        return out

    for base_name, base in base_mats.items():
        for scale in [1.0, 1.3, 1.7, 2.0]:
            scaled = base * scale
            key = f"{base_name}_ds{str(scale).replace('.', 'p')}"
            metrics[key] = _metrics(scaled, Y_val)
            metrics[key]["delta_scale"] = scale

            self_scaled = set_self(base, self_median, scale=scale)
            metrics[key + "_selfTrainScaled"] = _metrics(self_scaled, Y_val)
            metrics[key + "_selfTrainScaled"]["delta_scale"] = scale
            metrics[key + "_selfTrainScaled"]["self_value"] = self_median * scale

            self_raw = set_self(base, self_median, scale=1.0)
            metrics[key + "_selfTrain"] = _metrics(self_raw, Y_val)
            metrics[key + "_selfTrain"]["delta_scale"] = scale
            metrics[key + "_selfTrain"]["self_value"] = self_median

    ranking = []
    for name, m in metrics.items():
        score = (
            m["top200_cos"] * 0.5
            + m["pearson_mean"] * 0.3
            - min(m["delta_mse"], 0.02) * 10.0
            + min(m["scale_ratio_pred_over_true_median"], 1.5) * 0.1
        )
        ranking.append(
            (
                score,
                name,
                m["top200_cos"],
                m["pearson_mean"],
                m["delta_mse"],
                m["scale_ratio_pred_over_true_median"],
            )
        )
    ranking.sort(reverse=True)

    result = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_train_pairs": len(train_pairs),
        "n_val_targets": len(val_targets),
        "self_median_train": self_median,
        "ranking_top30": [
            {
                "name": name,
                "composite": float(score),
                "top200_cos": float(top200),
                "pearson_mean": float(pearson),
                "delta_mse": float(mse),
                "scale_ratio": float(ratio),
            }
            for score, name, top200, pearson, mse, ratio in ranking[:30]
        ],
        "metrics": metrics,
        "elapsed_s": round(time.time() - t0, 1),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/h1_transfer_sweep.json", "w") as f:
        json.dump(result, f, indent=2)
    vol.commit()
    print(json.dumps(result["ranking_top30"], indent=2), flush=True)
    return result


@app.local_entrypoint()
def main(action: str = "evaluate"):
    if action == "inspect":
        out = inspect_inputs.remote()
        print(json.dumps(out, indent=2))
    elif action == "evaluate":
        out = evaluate_h1_transfer.remote()
        print(json.dumps(out, indent=2)[:20000])
    elif action == "sweep":
        out = sweep_h1_transfer.remote()
        print(json.dumps(out.get("ranking_top30", out), indent=2)[:20000])
    else:
        raise ValueError(f"unknown action: {action}")
