"""k204 — L1 precision-weighted meta-analysis over k201/k202 L0 stores.

Reads every `stats.npz` + `manifest.json` under
`/kytos-vol/k201-evidence/<dataset>/<run>/`, combines per (target, gene)
across datasets, and emits ONE consensus store to
`/kytos-vol/k204-meta/<run_id>/`.

Design contract (docs/engine-v2-design.md §4):

- **z is the cross-assay unit.** z ~ N(0,1) under the null, so pooling z
  with DerSimonian-Laird uses unit within-study variance — weights are
  equal and tau²_z captures true between-study heterogeneity directly.
- **LFC is pooled only within lfc_kind groups** — units are never
  silently mixed. Per target, the `lfc_kind` with the most covering
  sources is the primary kind; `lfc_hat`/`se_hat` are the fixed-effect
  IV pool within that kind, with `se_hat` inflated by sqrt(Q/df) and
  `tau2_lfc` emitted so a later pass can re-weight.
- **Disagreement is signal**: `tau2_z`, `i2_z`, `votes_pos`/`votes_neg`
  are first-class outputs feeding the L2 DE-set predictor.
- **Assay filter**: activation arms (CRISPRa / overexpression) are
  excluded from knockdown consensus via the store manifest's `assay`
  tag (audit-complete stores still live on the volume untouched).

Single pass over stores (each ~1-2 GB npz) + a manifest/coverage
pre-pass for the union target axis and primary-kind assignment.

Run:
    modal run tools/modal_k204_meta.py            # full L1 build
    modal run -d tools/modal_k204_meta.py         # detached
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

APP_NAME = "kytos-k204-meta"
EVIDENCE_ROOT = Path("/kytos-vol/k201-evidence")
OUT_ROOT = Path("/kytos-vol/k204-meta")
RUN_ID = "h204-20261121-02"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "pandas==2.2.3",
        "scipy==1.15.3",
    )
    .add_local_file(str(Path(__file__).resolve()), "/root/modal_k204_meta.py")
)

app = modal.App(APP_NAME, image=image)
vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

# Assays excluded from knockdown consensus (activation / overexpression
# direction would corrupt KD evidence). Matched against manifest assay
# tags, lower-cased substring search.
# tokens matched after splitting on -/_ (catches sc-oe, crop-oe, crispa)
EXCLUDE_ASSAY_TOKENS = {"oe", "crispa", "crispra", "activation", "overexpression"}
EXCLUDE_ASSAY_SUBSTR = ("overexpress", "activation")


def _discover() -> list[dict]:
    """Return [{dir, manifest}] for every complete L0 store."""
    out = []
    for ds_dir in sorted(EVIDENCE_ROOT.iterdir()):
        if not ds_dir.is_dir():
            continue
        for run_dir in sorted(ds_dir.iterdir()):
            if (run_dir / "stats.npz").exists() and (run_dir / "manifest.json").exists():
                man = json.loads((run_dir / "manifest.json").read_text())
                man["_dataset"] = ds_dir.name
                man["_run"] = run_dir.name
                out.append({"dir": run_dir, "manifest": man})
    return out


def _excluded(man: dict) -> bool:
    assay = str(man.get("assay", "")).lower()
    toks = set(re.split(r"[-_ ]+", assay))
    return bool(toks & EXCLUDE_ASSAY_TOKENS) or any(s in assay for s in EXCLUDE_ASSAY_SUBSTR)


@app.function(
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=7200,
    volumes={"/kytos-vol": vol},
)
def meta(run_id: str = RUN_ID, exclude_datasets: list | None = None) -> dict:
    import numpy as np

    discovered = _discover()
    # newest run per dataset_id only (cd4 l0-01 superseded by l0-02)
    by_ds: dict[str, dict] = {}
    for e in discovered:
        key = e["manifest"]["_dataset"]
        if key not in by_ds or e["manifest"]["_run"] > by_ds[key]["manifest"]["_run"]:
            by_ds[key] = e
    superseded = [
        f"{e['manifest']['_dataset']}/{e['manifest']['_run']}"
        for e in discovered
        if by_ds[e["manifest"]["_dataset"]] is not e
    ]
    excl = set(exclude_datasets or [])
    entries = [
        e
        for e in by_ds.values()
        if not _excluded(e["manifest"]) and e["manifest"]["_dataset"] not in excl
    ]
    skipped = [
        e["manifest"]["_dataset"]
        for e in by_ds.values()
        if _excluded(e["manifest"]) or e["manifest"]["_dataset"] in excl
    ]
    if superseded:
        print(f"superseded runs ignored: {superseded}", flush=True)
    print(f"{len(entries)} stores included; excluded: {skipped}", flush=True)

    # ---- pass 1: union target axis + per-target primary lfc_kind ----
    from collections import Counter

    tgt_index: dict[str, int] = {}
    kind_votes: dict[str, Counter] = {}
    genes_ref = None
    store_map = []  # (run_dir, kind, row_idx array into union, cov mask)
    for e in entries:
        npz = np.load(e["dir"] / "stats.npz")
        tgts = npz["targets"].astype(str)
        cov = npz["covered"].astype(bool)
        g = npz["genes"].astype(str)
        if genes_ref is None:
            genes_ref = g
        else:
            assert (g == genes_ref).all(), f"gene axis mismatch: {e['dir']}"
        kind = str(e["manifest"].get("lfc_kind", "unknown"))
        idx = np.full(len(tgts), -1, dtype=np.int64)
        for i, t in enumerate(tgts):
            if not cov[i]:
                continue
            j = tgt_index.setdefault(t, len(tgt_index))
            kind_votes.setdefault(t, Counter())[kind] += 1
            idx[i] = j
        store_map.append({"dir": e["dir"], "kind": kind, "idx": idx, "cov": cov})
    T = len(tgt_index)
    targets = np.empty(T, dtype=object)
    for t, j in tgt_index.items():
        targets[j] = t
    primary_kind = np.empty(T, dtype=object)
    for t, c in kind_votes.items():
        primary_kind[tgt_index[t]] = c.most_common(1)[0][0]
    G = len(genes_ref)
    print(f"union: {T} targets x {G} genes from {len(entries)} stores", flush=True)

    # ---- pass 2: accumulate ----
    f32 = np.float32
    sum_z = np.zeros((T, G), f32)
    sum_z2 = np.zeros((T, G), f32)
    n_src = np.zeros((T, G), f32)
    vpos = np.zeros((T, G), np.int16)
    vneg = np.zeros((T, G), np.int16)
    nvote = np.zeros((T, G), np.int32)
    n_wsrc = np.zeros((T, G), f32)
    sum_w = np.zeros((T, G), f32)
    sum_wl = np.zeros((T, G), f32)
    sum_wl2 = np.zeros((T, G), f32)
    sum_w2 = np.zeros((T, G), f32)
    kd_sum = np.zeros(T, f32)
    kd_cnt = np.zeros(T, np.int16)

    for si, sm in enumerate(store_map):
        npz = np.load(sm["dir"] / "stats.npz")
        z = npz["z"].astype(f32)
        lfc = npz["lfc"].astype(f32)
        se = npz["se"].astype(f32)
        nv = npz["n_voting"].astype(np.float64)
        idx = sm["idx"]
        cov = sm["cov"]
        rows = idx[cov]  # unique within a store -> fancy += is safe
        zr = z[cov]
        ok = np.isfinite(zr)
        n_src[rows, :] += ok.astype(f32)
        sum_z[rows, :] += np.where(ok, zr, 0)
        sum_z2[rows, :] += np.where(ok, zr * zr, 0)
        vpos[rows, :] += zr > 1.96
        vneg[rows, :] += zr < -1.96
        nvote[rows, :] += np.nan_to_num(nv[cov], nan=0).astype(np.int32)
        # lfc pooling within this store's kind only where target primary == kind
        pmatch = np.array([primary_kind[j] == sm["kind"] for j in rows], dtype=bool)
        if pmatch.any():
            r2 = rows[pmatch]
            lr = lfc[cov][pmatch]
            sr = se[cov][pmatch]
            w = np.where(
                np.isfinite(lr) & np.isfinite(sr) & (sr > 0),
                1.0 / (sr.astype(np.float64) ** 2),
                0.0,
            )
            lv = np.where(np.isfinite(lr), lr.astype(np.float64), 0.0)
            w = w.astype(f32)
            sum_w[r2, :] += w
            sum_wl[r2, :] += (w * lv).astype(f32)
            sum_wl2[r2, :] += (w * lv * lv).astype(f32)
            sum_w2[r2, :] += (w * w).astype(f32)
            n_wsrc[r2, :] += (w > 0).astype(f32)
        kd = npz["kd_eff"]
        for t_i, j in zip(np.flatnonzero(cov), rows):
            if np.isfinite(kd[t_i]):
                kd_sum[j] += f32(kd[t_i])
                kd_cnt[j] += 1
        print(f"  [{si + 1}/{len(store_map)}] {sm['dir'].parent.name} done", flush=True)

    # ---- derive consensus (chunked over genes; f64 only per chunk) ----
    f32 = np.float32
    z_hat = np.full((T, G), np.nan, f32)
    se_z = np.full((T, G), np.nan, f32)
    tau2_z = np.zeros((T, G), f32)
    i2_z = np.zeros((T, G), f32)
    lfc_hat = np.full((T, G), np.nan, f32)
    se_hat = np.full((T, G), np.nan, f32)
    tau2_lfc = np.zeros((T, G), f32)
    CH = 4096
    for g0 in range(0, G, CH):
        g1 = min(g0 + CH, G)
        s = np.s_[:, g0:g1]
        n = n_src[s].astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            mz = np.where(n > 0, sum_z[s] / n, np.nan)
            z2m = np.where(n > 0, sum_z2[s] / n, np.nan)
            Q = n * (z2m - np.nan_to_num(mz) ** 2)
            df = np.clip(n - 1, 0, None)
            tau2_z[s] = np.where((n > 1) & (Q > df), (Q - df) / np.clip(df, 1, None), 0.0)
            i2_z[s] = np.where(Q > 0, np.clip(1 - df / np.where(Q > 0, Q, 1), 0, 1), 0.0)
            z_hat[s] = mz.astype(f32)
            se_z[s] = np.where(n > 0, np.sqrt((1 + tau2_z[s]) / n), np.nan)

            W = sum_w[s].astype(np.float64)
            lfc_hat[s] = np.where(W > 0, sum_wl[s] / W, np.nan)
            se_fe = np.where(W > 0, 1.0 / np.sqrt(W), np.nan)
            Ql = sum_wl2[s].astype(np.float64) - np.where(
                W > 0, (sum_wl[s].astype(np.float64) ** 2) / np.where(W > 0, W, 1), 0.0
            )
            dfl = np.clip(n_wsrc[s].astype(np.float64) - 1, 0, None)
            infl = np.where(dfl > 0, np.sqrt(np.clip(Ql / np.clip(dfl, 1, None), 1, None)), 1.0)
            se_hat[s] = se_fe * infl
            C = W - np.where(W > 0, sum_w2[s].astype(np.float64) / np.where(W > 0, W, 1), 0.0)
            tau2_lfc[s] = np.where(
                (dfl > 0) & (C > 0) & (Ql > dfl), (Ql - dfl) / np.where(C > 0, C, 1), 0.0
            )
        if g0 % (CH * 3) == 0:
            print(f"  derive {g1}/{G}", flush=True)

    covered = n_src > 0
    kd_eff = np.where(kd_cnt > 0, kd_sum / np.clip(kd_cnt, 1, None), np.nan).astype(f32)
    n_kind = np.zeros(T, np.int16)
    for t, c in kind_votes.items():
        n_kind[tgt_index[t]] = c.get(primary_kind[tgt_index[t]], 0)

    out = OUT_ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "stats.npz",
        genes=genes_ref,
        targets=targets.astype(str),
        covered=covered,
        z_hat=z_hat,
        se_z=se_z,
        tau2_z=tau2_z.astype(f32),
        i2_z=i2_z.astype(f32),
        votes_pos=vpos,
        votes_neg=vneg,
        n_sources=n_src.astype(np.int16),
        n_voting=nvote,
        lfc_hat=lfc_hat,
        se_hat=se_hat,
        tau2_lfc=tau2_lfc,
        kd_eff=kd_eff,
        n_kind_sources=n_kind,
    )
    manifest = {
        "run_id": run_id,
        "layer": "L1",
        "method": (
            "z_hat: DerSimonian-Laird random-effects pool of z across ALL "
            "included stores (unit within-study variance); "
            "lfc_hat/se_hat: fixed-effect IV pool restricted to each "
            "target's primary lfc_kind, se inflated by sqrt(Q/df); "
            "tau2_z/i2_z: DL heterogeneity stats; votes at |z|>1.96"
        ),
        "n_stores": len(entries),
        "stores": [
            {
                "dataset": e["manifest"]["_dataset"],
                "run": e["manifest"]["_run"],
                "lfc_kind": e["manifest"].get("lfc_kind"),
                "se_kind": e["manifest"].get("se_kind"),
                "context": e["manifest"].get("context"),
                "assay": e["manifest"].get("assay"),
            }
            for e in entries
        ],
        "excluded_assay": skipped,
        "n_targets": int(T),
        "n_covered": int(covered.any(axis=1).sum()),
        "weight_multipliers": "v0 uniform (LOLO-fitted weights are k205+)",
        "notes": (
            "LFC never pooled across lfc_kind groups; z is the cross-assay "
            "unit. tau2_lfc emitted for future RE re-weighting. PSEUDOREP "
            "stores contribute with their (inflated) SEs — downweight "
            "multiplier deferred to fitted weights (k205+)."
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    vol.commit()
    return {
        "status": "ok",
        "out": str(out),
        "targets": int(T),
        "covered": int(covered.any(axis=1).sum()),
        "excluded": skipped,
    }


@app.function(volumes={"/kytos-vol": vol}, timeout=1800)
def audit(run_id: str = RUN_ID) -> dict:
    """Spot-check the L1 store: self-KD sign, source multiplicities,
    tau2 signal on replicated targets."""
    import numpy as np

    npz = np.load(OUT_ROOT / run_id / "stats.npz")
    genes = npz["genes"].astype(str)
    targets = npz["targets"].astype(str)
    gpos = {g: i for i, g in enumerate(genes)}
    zh, sez, t2, i2 = npz["z_hat"], npz["se_z"], npz["tau2_z"], npz["i2_z"]
    nsrc, lh = npz["n_sources"], npz["lfc_hat"]
    covered = npz["covered"]

    self_z, self_ok = [], []
    for i, t in enumerate(targets):
        if covered[i].any() and t in gpos:
            v = zh[i, gpos[t]]
            if np.isfinite(v):
                self_z.append(float(v))
                self_ok.append(t)
    self_z = np.array(self_z)
    multi = nsrc >= 3
    rep = {
        "n_covered": int(covered.any(axis=1).sum()),
        "selfkd_neg": f"{int((self_z < 0).sum())}/{len(self_z)}",
        "selfkd_z_median": float(np.median(self_z)),
        "median_n_sources_over_cells": float(np.nanmedian(nsrc[covered])),
        "frac_cells_multi_source": float(multi[covered].mean()),
        "tau2_z_median_multi": float(np.nanmedian(np.where(multi, t2, np.nan))),
        "i2_z_median_multi": float(np.nanmedian(np.where(multi, i2, np.nan))),
        "lfc_finite_frac": float(np.isfinite(lh[covered]).mean()),
        "z_hat_absmax": float(np.nanmax(np.abs(zh[covered]))),
        "se_z_median": float(np.nanmedian(sez[covered])),
    }
    print(json.dumps(rep, indent=2))
    return rep


@app.local_entrypoint()
def main(run_id: str = RUN_ID, detach: bool = False, do_audit: bool = False) -> None:
    if do_audit:
        print(json.dumps(audit.remote(run_id), indent=2))
        return
    if detach:
        fc = meta.spawn(run_id)
        print(json.dumps({"spawned": fc.object_id, "run_id": run_id}))
    else:
        print(json.dumps(meta.remote(run_id), indent=2))
