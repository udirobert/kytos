"""Kytos k020 (Track 2) — GEARS-style cross-lineage GNN.

Predict the *panel-lineage* perturbation delta (Jurkat=A / RPE1=B / HepG2=C)
from the K562 GWPS delta, conditioning on (a) WHICH gene is perturbed and
(b) the context's basal expression, propagating through a gene-gene graph.

Why a GNN (grounded in k019): on the OOD-proxy split, identity transplant on
A/B is anti-correlated with the true lineage delta (cos ~ -0.08); per-gene
maps don't extrapolate; only ACROSS-GENE structure flips OOD positive. A
message-passing net is the strongest prior for that.

Conditioning is the whole point (fixes an earlier bug that fed zeros):
  node j input = [ node_emb(j) ; target_emb(tg) ; ctx_emb(c) ;
                   src_delta_j ; src_delta_tg ; ctx_basal_j ; ctx_basal_tg ]
  graph        = co-perturbation correlation over genes (top-k, symmetrised)
  body         = L GCN rounds with residual
  loss         = MSE on DE genes (top-k |dst|) + lam*(1 - cosine(full))
  validation   = SAME in-dist vs OOD-proxy conservation split as k019 (never
                 ship an in-distribution-only win like k015 did).

Run:
  # CPU code-path smoke (synthetic, no data):
  python tools/track2/train_gnn_crosslineage.py --smoke
  # real training (Nebius GPU):
  python tools/track2/train_gnn_crosslineage.py \
      --npz /data/derived/essential_transfer_data.npz \
      --gene-names data/raw/vcc2026/gene_names.csv \
      --out-dir experiments/k020-gnn-crosslineage --epochs 300
  # panel inference (after training; emits prediction_deltas.npz for
  # tools/run_k014_trained_model.py):
  python tools/track2/train_gnn_crosslineage.py \
      --predict --ckpt experiments/k020-gnn-crosslineage/gnn.pt \
      --panel-deltas /data/derived/panel_k562_deltas.npz \
      --out-dir experiments/k020-gnn-crosslineage
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

LINEAGES = {"jurkat": "k562_to_jurkat", "rpe1": "k562_to_rpe1", "hepg2": "k562_to_hepg2"}
CTX_OF_LINEAGE = {"jurkat": "A", "rpe1": "B", "hepg2": "C"}
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------------------------------------------------------------- graph build
def build_graph(x: np.ndarray, top_k: int = 32, ridge: float = 1e-3) -> torch.Tensor:
    """Symmetric-normalised adjacency from co-perturbation correlation.

    x: (n_targets, n_genes) source deltas -> correlation across targets ->
    functional edges. Returns A_hat (G,G) with self-loops, sym-normalised.
    """
    z = x - x.mean(0, keepdims=True)
    z = z / (z.std(0) + 1e-6)
    C = (z.T @ z) / max(z.shape[0], 1)
    np.fill_diagonal(C, 0.0)
    G = C.shape[0]
    k = min(top_k, G - 1)
    idx = np.argpartition(-C, k, axis=1)[:, :k]
    rows = np.repeat(np.arange(G), k)
    A = np.zeros((G, G), dtype=np.float32)
    A[rows, idx.ravel()] = 1.0
    A = np.maximum(A, A.T)
    A[np.arange(G), np.arange(G)] = 1.0
    dn = 1.0 / np.sqrt(A.sum(1) + ridge)
    return torch.tensor((A * dn[:, None]) * dn[None, :], dtype=torch.float32)


# --------------------------------------------------------------------- model
class CrossLineageGNN(nn.Module):
    def __init__(self, n_genes: int, n_ctx: int, emb: int = 64, hid: int = 128, layers: int = 2):
        super().__init__()
        self.node = nn.Embedding(n_genes, emb)
        self.ctx = nn.Embedding(n_ctx, emb)
        in_dim = 3 * emb + 4
        self.gcn = nn.ModuleList([nn.Linear(in_dim if i == 0 else hid, hid) for i in range(layers)])
        self.res = nn.ModuleList([nn.Linear(in_dim if i == 0 else hid, hid) for i in range(layers)])
        self.head = nn.Sequential(nn.Linear(hid, hid), nn.ReLU(), nn.Linear(hid, 1))
        self.emb = emb

    def forward(self, node_idx, src_delta, target_idx, ctx_id, ctx_basal, A):
        """node_idx (G,), src_delta (B,G), target_idx (B,), ctx_id (B,),
        ctx_basal (B,G) [basal of each sample's context, in gene order], A (G,G)."""
        B, G = src_delta.shape
        ne = self.node(node_idx).unsqueeze(0).expand(B, G, self.emb)  # (B,G,emb) node
        te = self.node(target_idx).unsqueeze(1).expand(B, G, self.emb)  # (B,G,emb) target
        ce = self.ctx(ctx_id).unsqueeze(1).expand(B, G, self.emb)  # (B,G,emb) context
        s_j = src_delta.unsqueeze(-1)  # (B,G,1)
        s_t = src_delta.gather(1, target_idx[:, None])[:, None, :].expand(B, G, 1)
        cb_j = ctx_basal.unsqueeze(-1)  # (B,G,1)
        cb_t = ctx_basal.gather(1, target_idx[:, None])[:, None, :].expand(B, G, 1)
        h = torch.cat([ne, te, ce, s_j, s_t, cb_j, cb_t], dim=-1)  # (B,G,in_dim)
        for i, layer in enumerate(self.gcn):
            m = layer(torch.matmul(A, h)) + self.res[i](h)
            h = torch.relu(m) if i == 0 else torch.relu(m + h)
        return self.head(h).squeeze(-1)  # (B,G)


# --------------------------------------------------------------------- data
def _norm_basal(b):
    b = np.log1p(np.clip(np.asarray(b, dtype=np.float32), 0, None))
    return (b - b.mean()) / (b.std() + 1e-6)


def load_real(npz_path: Path, gene_cap: int):
    """Returns samples: list of dict(target_symbol, src[G], dst[G], ctx_name,
    basal[G]); n_genes; ctx_names; basals_by_ctx; gene-keep indices absent
    (columns assumed gene_names order)."""
    d = np.load(npz_path, allow_pickle=False)
    samples, basals, keep = [], {}, None
    for lin, pref in LINEAGES.items():
        if f"{pref}_src" not in d:
            continue
        x = np.asarray(d[f"{pref}_src"], dtype=np.float32)
        y = np.asarray(d[f"{pref}_dst"], dtype=np.float32)
        targs = (
            np.asarray(d[f"{pref}_targets"]).astype(str)
            if f"{pref}_targets" in d
            else np.array(["?"] * len(x))
        )
        bk = f"basal_{lin}"
        basal = d[bk] if bk in d else np.zeros(x.shape[1], dtype=np.float32)
        if keep is None and x.shape[1] > gene_cap:
            keep = np.argsort(-y.var(0))[:gene_cap]
        if keep is not None:
            x, y, basal = x[:, keep], y[:, keep], np.asarray(basal, dtype=np.float32)[keep]
        basal = _norm_basal(basal)
        basals[lin] = basal
        for b in range(len(x)):
            samples.append({"ctx": lin, "targ": targs[b], "src": x[b], "dst": y[b]})
    return samples, (samples[0]["src"].shape[0]), basals, keep


def build_tensors(samples, gene_index, ctx_ids, basals):
    src, dst, tidx, cid, cbas = [], [], [], [], []
    used = []
    for s in samples:
        ti = gene_index.get(s["targ"], -1)
        if ti < 0:
            continue
        src.append(s["src"])
        dst.append(s["dst"])
        tidx.append(ti)
        cid.append(ctx_ids[s["ctx"]])
        cbas.append(basals[s["ctx"]])
        used.append(s["targ"])
    return (
        np.stack(src).astype(np.float32),
        np.stack(dst).astype(np.float32),
        np.asarray(tidx, dtype=np.int64),
        np.asarray(cid, dtype=np.int64),
        np.stack(cbas).astype(np.float32),
        used,
    )


def conservation_split(src, dst):
    c = (src * dst).sum(1) / (np.linalg.norm(src, axis=1) * np.linalg.norm(dst, axis=1) + 1e-9)
    order = np.argsort(c)
    q = len(c) // 4
    return set(order[:q].tolist()), set(order[-q:].tolist())


def cos_loss(pred, tgt, eps=1e-9):
    return 1.0 - ((pred * tgt).sum(1) / (pred.norm(dim=1) * tgt.norm(dim=1) + eps)).mean()


# -------------------------------------------------------------------- train
def train_epoch(model, A, data, idx, node_idx, epochs, lr, bs, de_topk, lam_cos):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    X, Y, TI, CI, CB = (torch.tensor(v, device=DEVICE) for v in data)
    idx = torch.as_tensor(idx, dtype=torch.long, device=DEVICE)
    for ep in range(epochs):
        perm = idx[torch.randperm(len(idx), device=DEVICE)]
        tot = 0.0
        for s in range(0, len(perm), bs):
            b = perm[s : s + bs]
            xb, yb = X[b], Y[b]
            mask = yb.abs().topk(min(de_topk, yb.shape[1]), dim=1).indices
            m = torch.zeros_like(yb, dtype=torch.bool).scatter_(1, mask, True)
            pred = model(node_idx, xb, TI[b], CI[b], CB[b], A)
            loss = ((pred[m] - yb[m]) ** 2).mean() + lam_cos * cos_loss(pred, yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        if (ep + 1) % max(1, epochs // 5) == 0:
            print(f"  epoch {ep + 1:3d}  loss {tot / len(perm):.4f}", flush=True)


def eval_cos(model, A, data, node_idx, rows):
    model.eval()
    X, Y, TI, CI, CB = data
    with torch.no_grad():
        pred = (
            model(
                node_idx,
                torch.tensor(X[rows], device=DEVICE),
                torch.tensor(TI[rows], device=DEVICE),
                torch.tensor(CI[rows], device=DEVICE),
                torch.tensor(CB[rows], device=DEVICE),
                A,
            )
            .cpu()
            .numpy()
        )
    tgt = Y[rows]
    src = X[rows]
    cc = (pred * tgt).sum(1) / (np.linalg.norm(pred, axis=1) * np.linalg.norm(tgt, axis=1) + 1e-9)
    ic = (src * tgt).sum(1) / (np.linalg.norm(src, axis=1) * np.linalg.norm(tgt, axis=1) + 1e-9)
    return pred, cc, ic


# ------------------------------------------------------------------- predict
def predict_panel(model, A, panel, node_idx):
    """panel: dict with src (T,G), target_idx (T,), ctx_id (T,), ctx_basal (T,G)."""
    model.eval()
    with torch.no_grad():
        pred = (
            model(
                node_idx,
                torch.tensor(panel["src"], device=DEVICE),
                torch.tensor(panel["target_idx"], device=DEVICE),
                torch.tensor(panel["ctx_id"], device=DEVICE),
                torch.tensor(panel["ctx_basal"], device=DEVICE),
                A,
            )
            .cpu()
            .numpy()
        )
    return pred.astype(np.float32)


# --------------------------------------------------------------------- smoke
def synth_pair(lin, ctx_id, n=140, g=260, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, (n, g)).astype(np.float32)
    tg = rng.integers(0, g, n)
    # lineage-specific per-gene transfer + a target-gene effect (so conditioning matters)
    w = rng.normal(0.4, 0.2, g).astype(np.float32)
    y = x * w + 0.3 * (x**2).clip(-3, 3)
    for i in range(n):
        y[i] += 0.5 * np.eye(g, dtype=np.float32)[tg[i]].ravel() * x[i, tg[i]]
    basal = _norm_basal(np.abs(rng.normal(0, 1, g)))
    samples = [{"ctx": lin, "targ": None, "src": x[i], "dst": y[i]} for i in range(n)]
    return samples, np.arange(g), tg, basal


# ---------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--npz", type=Path)
    ap.add_argument("--gene-names", type=Path)
    ap.add_argument(
        "--panel-deltas", type=Path, help="npz: targets(str),deltas(T,G),gene_names(order)"
    )
    ap.add_argument("--out-dir", type=Path, default=Path("experiments/k020-gnn-crosslineage"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--predict", action="store_true")
    ap.add_argument(
        "--norm-match",
        action="store_true",
        help="rescale each GNN delta to its borrowed K562 signature's L2 norm (predict only)",
    )
    ap.add_argument("--ckpt", type=Path)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--gene-cap", type=int, default=4000)
    ap.add_argument("--top-k", type=int, default=32)
    ap.add_argument("--de-topk", type=int, default=200)
    ap.add_argument("--lam-cos", type=float, default=0.3)
    args = ap.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)

    if args.predict:
        return run_predict(args)

    # ---- assemble (ctx_ids, basals, gene index, samples) ----
    if args.smoke:
        ctx_ids = {"jurkat": 0, "rpe1": 1}
        all_samples, basals = [], {}
        gene_ids = np.arange(260)
        for lin, seed in [("jurkat", 0), ("rpe1", 1)]:
            s, gi, tg, basal = synth_pair(lin, ctx_ids[lin], seed=seed)
            for i, smp in enumerate(s):
                smp["targ"] = f"G{tg[i]}"  # synthetic target symbol per sample
            all_samples += s
            basals[lin] = basal
        gene_order = [f"G{i}" for i in gene_ids]
        n_genes = len(gene_order)
        ctx_names = list(ctx_ids)
    else:
        if not args.npz or not args.npz.exists():
            raise SystemExit("need --npz (or use --smoke)")
        import pandas as pd

        all_samples, n_genes, basals, keep = load_real(args.npz, args.gene_cap)
        gene_order = pd.read_csv(args.gene_names, header=None, skiprows=1)[0].tolist()
        gene_order = [gene_order[g] for g in keep] if keep is not None else gene_order[:n_genes]
        ctx_names = list(basals)
        ctx_ids = {c: i for i, c in enumerate(ctx_names)}

    gene_index = {g: i for i, g in enumerate(gene_order)}
    X, Y, TI, CI, CB, used = build_tensors(all_samples, gene_index, ctx_ids, basals)
    if len(X) < 20:
        raise SystemExit("too few aligned samples — check target symbol/gene-order alignment")
    print(f"[data] {len(X)} samples, {n_genes} genes, contexts {ctx_names}", flush=True)

    ood, indist = conservation_split(X, Y)
    perm = np.random.default_rng(7).permutation(len(X))
    te = perm[: max(len(X) // 5, 30)]
    tr = np.setdiff1d(np.arange(len(X)), te)

    A = build_graph(X[tr], top_k=args.top_k).to(DEVICE)
    node_idx = torch.arange(n_genes, device=DEVICE)
    model = CrossLineageGNN(n_genes, len(ctx_names), emb=64, hid=128, layers=2).to(DEVICE)
    data = (X, Y, TI, CI, CB)
    print(f"[fit] device={DEVICE} n_train={len(tr)} n_test={len(te)}", flush=True)
    train_epoch(
        model, A, data, tr, node_idx, args.epochs, args.lr, args.batch, args.de_topk, args.lam_cos
    )

    _, cc, ic = eval_cos(model, A, data, node_idx, te)
    ood_m = np.array([t in ood for t in te])
    ind_m = np.array([t in indist for t in te])
    report = {
        "device": str(DEVICE),
        "n_test": int(len(te)),
        "n_genes": int(n_genes),
        "identity": {
            "cos_all": float(ic.mean()),
            "cos_ood": float(ic[ood_m].mean()),
            "cos_indist": float(ic[ind_m].mean()),
        },
        "gnn": {
            "cos_all": float(cc.mean()),
            "cos_ood": float(cc[ood_m].mean()),
            "cos_indist": float(cc[ind_m].mean()),
        },
    }
    print(json.dumps(report, indent=2), flush=True)
    (args.out_dir / "gnn_eval.json").write_text(json.dumps(report, indent=2))
    torch.save(model.state_dict(), args.out_dir / "gnn.pt")  # tensors only -> weights_only-safe
    meta = {
        "n_genes": int(n_genes),
        "n_ctx": len(ctx_names),
        "gene_order": gene_order,
        "ctx_ids": ctx_ids,
        "basals": {k: basals[k].tolist() for k in basals},
    }
    (args.out_dir / "gnn_meta.json").write_text(json.dumps(meta))
    return 0


def run_predict(args) -> int:
    if not (args.ckpt and args.panel_deltas and args.ckpt.exists()):
        raise SystemExit("--predict needs --ckpt and --panel-deltas")
    meta = json.loads(Path(str(args.ckpt).replace("gnn.pt", "gnn_meta.json")).read_text())
    n_genes, n_ctx = meta["n_genes"], meta["n_ctx"]
    model = CrossLineageGNN(n_genes, n_ctx).to(DEVICE)
    model.load_state_dict(torch.load(args.ckpt, map_location=DEVICE, weights_only=True))
    gene_index = {g: i for i, g in enumerate(meta["gene_order"])}
    basals = {k: np.asarray(v, dtype=np.float32) for k, v in meta["basals"].items()}
    gsub = [str(g) for g in meta["gene_order"]]  # (n_genes,) subset symbols
    pdat = np.load(args.panel_deltas, allow_pickle=False)
    ptargets = np.asarray(pdat["targets"]).astype(str)
    full_order = [str(g) for g in np.asarray(pdat["gene_names"])]  # (G_full,) consumer gene order
    pdeltas_full = np.asarray(pdat["deltas"], dtype=np.float32)  # (T, G_full)
    covered = (
        np.asarray(pdat["covered"], dtype=bool)
        if "covered" in pdat
        else np.ones(len(ptargets), dtype=bool)
    )
    full_pos = {g: i for i, g in enumerate(full_order)}
    sub_to_full = np.array([full_pos.get(g, -1) for g in gsub])
    good = sub_to_full >= 0
    T = len(ptargets)
    src_sub = np.zeros((T, n_genes), dtype=np.float32)
    src_sub[:, good] = pdeltas_full[:, sub_to_full[good]]
    node_idx = torch.arange(n_genes, device=DEVICE)
    A = build_graph(src_sub, top_k=32).to(DEVICE)  # graph from panel co-perturbation
    results = {}
    for lin, ci in meta["ctx_ids"].items():
        ti = np.array([gene_index.get(t, 0) for t in ptargets], dtype=np.int64)
        panel = {
            "src": src_sub,
            "target_idx": ti,
            "ctx_id": np.full(T, ci, dtype=np.int64),
            "ctx_basal": np.tile(basals[lin], (T, 1)),
        }
        results[lin] = predict_panel(model, A, panel, node_idx)
    lin_list = [lin for lin in results if lin in CTX_OF_LINEAGE]
    contexts = [CTX_OF_LINEAGE[lin] for lin in lin_list]
    deltas = np.zeros((len(contexts), T, len(full_order)), dtype=np.float32)  # (C,T,G_full)
    k562_sub = pdeltas_full[:, sub_to_full[good]]  # (T, n_good) borrowed magnitudes
    kn = np.linalg.norm(k562_sub, axis=1, keepdims=True)
    scale_report = {}
    for ci, lin in enumerate(lin_list):
        pred_sub = np.asarray(results[lin], dtype=np.float32)[:, good]  # (T, n_good) GNN direction
        if args.norm_match:
            pn = np.linalg.norm(pred_sub, axis=1, keepdims=True)
            scale = np.where(pn > 1e-9, kn / pn, 0.0)
            pred_sub = pred_sub * scale
            if covered.any():
                scale_report[CTX_OF_LINEAGE[lin]] = float(np.median(scale[:, 0][covered]))
        deltas[ci][:, sub_to_full[good]] = pred_sub
    mask = np.tile(covered[None, :], (len(contexts), 1))  # uncovered -> neighbour/fallback tier
    np.savez_compressed(
        args.out_dir / "prediction_deltas.npz",
        contexts=np.array(contexts),
        vcc_targets=ptargets,
        deltas=deltas,
        coverage_mask=mask,
    )
    print(
        json.dumps(
            {
                "contexts": contexts,
                "n_targets": int(T),
                "norm_match": bool(args.norm_match),
                "median_gnn_to_k562_scale": scale_report,
                "covered_per_ctx": [int(mask[i].sum()) for i in range(len(contexts))],
                "gene_dim": int(deltas.shape[2]),
                "shape": list(deltas.shape),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
