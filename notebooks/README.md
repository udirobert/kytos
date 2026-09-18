# Kytos — Kaggle notebooks (free tier smoke)

Ratiocine two-phase pattern: validate data format + model wiring on Kaggle free GPU/CPU before burning paid 32GB Vast/RunPod.

## What's here

| Notebook | What it proves | Fits free tier |
|---|---|---|
| `kaggle_k004_smoke.ipynb` (+ `kaggle_k004_smoke.py`) | EDA on 2026 controls + **Exp A** real control-cell resampling baseline (dispersion-preserving) + **Exp B** `ContextConditionedTransfer` + `AdditiveTransportSampler` → cell-eval-ready `pred_*.h5ad` | 10 targets × 3 contexts = 12k cells (~140MB resample / ~1.2GB layer_a_b) in ~2 min; 20×3 = 24k cells ~2.4GB — keep 10-20 on free tier, 300 needs 32GB |

Local 8GB Mac can't run full `vcc prep` (28GB peak) or hold Atlas (13GB) — see `AGENTS.md:1` + `docs/architecture.md:114`.

## Kaggle setup (once)

1. **API token** — kaggle.com → Settings → API → Create New Token → downloads `kaggle.json`:
   ```bash
   mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json && chmod 600 ~/.kaggle/kaggle.json
   ```

2. **Dataset** — bundle the 632MB controls via `tools/kaggle_bundle.py`:
   ```bash
   .venv/bin/python tools/kaggle_bundle.py --out /tmp/kaggle-vcc2026-controls --username YOUR_USERNAME
   # check dataset-metadata.json -> id must be YOUR_USERNAME/vcc2026-controls
   .venv/bin/kaggle datasets create -p /tmp/kaggle-vcc2026-controls   # first time
   # later: .venv/bin/kaggle datasets version -p /tmp/kaggle-vcc2026-controls -m "v1"
   ```
   *License gate:* check Arc/VCC terms before making dataset public; gate as private if competition-only (`kaggle datasets create` defaults private).

3. **Notebook** — Kaggle → Create → Notebook → File → Import `notebooks/kaggle_k004_smoke.ipynb`
   - Add Input → search `vcc2026-controls` → Add
   - Settings → Internet **ON** if notebook clones `github.com/udirobert/kytos` (or attach repo as dataset and keep Internet OFF)
   - Accelerator: **CPU** is enough (no torch training yet); use T4×2 if you bump to larger `MAX_TARGETS`

4. **Run** — set `MAX_TARGETS` in cell 3:
   - Free tier smoke: `10` or `20` (verified locally: 10×3 = 1.2GB layer_a_b, 20×3 ~2.4GB)
   - Full 360k (300×400×3) → **don't run on free tier** — needs 32GB Vast/RunPod (see § Next)

5. **Collect** — `/kaggle/working/k004/pred_*.h5ad` + `meta_*.json` → Download. Commit only `meta_*.json` to `experiments/k004-kaggle-smoke/` (H5ADs gitignored via `experiments/**/*.h5ad`, live on HF/Kaggle).

## Local dry-run (8GB Mac — keep small)

```bash
.venv/bin/python notebooks/kaggle_k004_smoke.py --max-targets 5 --contexts A --out /tmp/k004_test
.venv/bin/python notebooks/kaggle_k004_smoke.py --max-targets 10 --contexts A,B,C --out /tmp/k004_10x3
ls -lh /tmp/k004_10x3/
```

## What to look for

- Cell 2 EDA top genes differ per context (HIST1H1B vs CLU vs ACTB) — confirms basal conditioning has signal.
- Cell 4 sanity: `layer_a_b mean` < `resample mean` for target genes (✓ knockdown). Barely-expressed targets (e.g. ABCD1 rank low) attenuate — by design in `src/kytos/models/layer_a.py:56`.
- Cell 6 pseudobulk top shifted genes — if they are the perturbed targets, Layer A is wired correctly. **Known quirk:** current `ContextConditionedTransfer` secondary diffusion hits all genes (see `layer_a.py:71` `delta += secondary_weights...`), so highly expressed genes (TMSB4X etc) also shift — tune `attenuation_factor` if top shifted aren't targets.

## Next after smoke passes

Bump `MAX_TARGETS=300` on **Vast/RunPod ≥32GB RAM** (hourly, ~$0.30-0.50/hr CPU):
```bash
python notebooks/kaggle_k004_smoke.py --max-targets 300 --contexts A,B,C --out experiments/k004-full
vcc prep --dry-run experiments/k004-full/pred_layer_a_b.h5ad   # then vcc submit (≤2/day guardrail)
```
