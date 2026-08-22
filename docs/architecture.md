# Kytos — Phase 0 Architecture & Decision Record

Status: **DRAFT** · Owner: udingethe · Started: **2026-08-22**
Companion to `NOTES.md §3 Honest Positioning` and `§4 Learnings`. This is the
decision record for the 2026 Virtual Cell Challenge stack. It is a *proposal*,
not a contract — each numbered decision has a gate below it that must be
re-checked before it is relied upon.

---

## 0. The input/output contract (from cell-eval)

Cell-eval compares **two cell × gene AnnData matrices** (`adata_pred` vs
`adata_real`), runs differential expression (pdex) on each independently, and
scores a panel of metrics. The perturbation identity lives in an **obs column**
(default `perturbation`), and a **`control` marker** denotes non-targeting /
basal cells. Gene identity is the **var axis** (`-g <expected_genelist>` in
`cell-eval prep`).

**Consequence**: the prediction is a **generated single-cell distribution per
knocked gene, plus a control group** — not a gene-level delta vector. A
point-estimate delta model can rank genes but cannot satisfy the
single-cell + DE-gated metrics. This is the load-bearing constraint on the
whole stack.

---

## 1. The metric panel (what we must move)

From `cell_eval.metrics` (registry current as of 2026-08-21). The 2026
challenge uses an aggregate of six; the registry is broader. All six of the
final panel share a core — *recover the genes that actually change, in the
right direction, in the right order, in a believable cell distribution* — so
the strategy below optimizes the shared core, not any single metric.

| Family | Metrics | What they reward |
|---|---|---|
| Array / error | `mse`, `mae`, `mse_delta`, `mae_delta`, `pearson_delta` | per-cell & per-gene closeness to real perturbed cells |
| Array / structure | `clustering_agreement`, `discrimination_score` | does prediction discriminate control vs perturbed like reality |
| DE-gated | `DESigGenesRecall`, `compute_pr_auc`, `compute_roc_auc`, `de_overlap_metric` | recovering the *set* of genes that change |
| DE / direction | `DEDirectionMatch`, `DESpearmanSignificant`, `DESpearmanLFC`, `DENsigCounts` | correct direction + monotone ordering of effects |

**Ceiling**: `cell-eval run --ceiling` computes per-metric upper bounds
(disjoint half-split + Spearman-Brown correction). Run this on the first
baseline — it tells us the noise-adjusted headroom *per metric* and prevents
chasing unreachable gains.

**Gate 1 (before modeling):** pin the final single six-metric aggregation. Not
needed to start; needed before tuning a submission. Acting early is low-risk
because all six share the core above.

---

## 2. The two-layer modeling frame

### Layer A — gene-level transfer (the science)
Map knocked gene *k* → gene-wise response field, in a **learned gene-embedding
space**, conditioned on a **context encoding derived only from the target
basal cells**. Context features (cheap, high signal at first):
- per-gene mean / quantile expression and rank in the target,
- gene–gene **co-expression / covariation structure of the target baseline**
  (a strong prior for how a knockdown propagates across genes in that context).

Purpose: **transfer the effect field between cell types**. This is the
scientifically central, auditable piece. "How much does basal-conditioning alone
buy" (NOTES open question 3) is the cheapest first experiment and steers
everything downstream.

### Layer B — conditional cell sample generator
Given target basal cells and Layer A's gene-delta field, **draw synthetic
post-perturbation cells** per gene and for the control. This is the
flow-matching / diffusion piece; it satisfies the single-cell and DE-gated
metrics rather than a point estimate.

**Two formulations, one decision**
- **Layer A:** favor an in-context-learning / gene-projection style regression
  (Stack-like) — best for *gene* coverage; the challenge's difficulty is
  *context* transfer, which the basal conditioning handles.
- **Layer B:** flow-matching (Altos' 2025 winning approach fits) — natural fit
  for generating the cell distribution cell-eval rewards.
- Ensemble at *eval*, not per-metric (NOTES: resist per-cell-line hand-tuning).

**Gate 2 (Phase 1/2):** choose the Layer A formulation (ICL regression vs a
transfer field learned via the flow model). Evidence = how much Layer A alone
improves over the mean-shift baseline on held-out simulated zero-shot (train on
Replogle multi-line; validate on an all-split-out cell type).

---

## 3. Data stack

| Priority | Corpus | Role |
|---|---|---|
| 1 | **Arc Atlas 2025** | in-distribution assay prior; fast baseline validation; intra-context covariance |
| 2 | **Replogle / Nadig genome-wide CRISPRi screens** | the **cross-context supervision**: CRISPRi knockdowns across multiple cell lines — trains the transfer itself |
| 3 | Basal-only cell-expression reference (Gene Atlas, etc.) | target-context conditioning; detect overlap between challenge lines & publicly perturbed data (legit edge if so) |

**Gene-space alignment**: an early, deterministic layer maps every corpus to one
gene namespace under the `expected_genelist`. Wraps in a reproducible artifact
(`meta.json` + seed + code hash) per the lemma/orbura habit.

---

## 4. Compute ladder (do not design around Brev)

| Window | Envelope | Use |
|---|---|---|
| Phase 0–1 | T4 / 16 GB | gene-level head smoke tests; baseline + ceiling |
| Phase 2+ | cloud / Brev (post-prize) | Layer B cell sampling at scale |

`ratiocine` lesson: know the envelope early; a prize-time credit is too late to
design around.

---

## 5. Engineering & hygiene (from the catalog)

- **Submission harness first** (`ratiocine`): `submission/script.py` reads
  official inputs (basal AnnData + gene list + expected_genelist), returns a
  cell-eval-ready prediction AnnData. Tested locally against a **frozen**
  `cell-eval run -ap … -ar …` before ever touching the live leaderboard.
- **No LLM in the inference path** (`weft`); LLM narration only for audit /
  leaderboard prose, rendered from facts JSON (`matcha-hack`).
- **Biological audit layer** (`lemma`-derived): housekeeping for gene-cat
  stability, control-group sanity, gene-group coherence, known dose/direction. **Sidecar**:
  it blocks impossible-in-vivo genes; it never fits one biomarker to climb a metric.
- **Shadow-review linking** (`poker`): run-ID-linked logs, monitored deps, spend
  caps + manual overrides.
- **Pre-registration** (`lenitnes`): lock expected effect directions before
  reading leaderboard feedback.

---

## 5b. Kytos Observatory (build-in-public)

Parallel to the prediction stack, the **Observatory** (`docs/observatory.md`) is
the **public accountability layer** for VCC experiments: metrics, biological
audit flags, literature, provenance, and video briefings. It does not sit on
the inference path. Problem, evidence, and wedge:
[`docs/competitive-landscape.md`](competitive-landscape.md).

| Layer | Role | Partner / stack |
|---|---|---|
| Render contract | `facts.json` per run — metrics, flags, provenance, visual paths | deterministic (`src/kytos/eval/`) |
| Narration | Run digest, briefing script — **from facts only** | OpenAI (weft / matcha) |
| Literature | Evidence sidebar for audit-flagged genes | Tavily (famile; degrade empty) |
| Stills | Hero imagery, share cards | **fal** (image gen) |
| Video briefings | Run explainers from committed artifacts | **fal** [`veed/fabric-1.0`](https://fal.ai/models/veed/fabric-1.0) (VEED Fabric) |
| Critique | Pre-registered hypotheses, Discussions per flag | GitHub |

**Milestone 0 (2026-08-22):** ship static Observatory + k001 run page as the
{Tech: Europe} × VEED Hackathon entry — initial milestone toward Nov 5, not a
detour from the science track.

---

## 6. Phase-0 sequencing to deadline (Nov 5, 2026)

| Window | Milestone |
|---|---|
| **2026-08-22 (today)** | Observatory Milestone 0: `frontend/`, `facts.json`, enrichment tools, k001 page; hackathon submit |
| **Late Aug** | install `cell-eval`; baseline through harness → `cell-eval run --ceiling` |
| **Early Sep** | inspect validation basal: gene-set overlap with public corpora; unlock Level-A context features; lock normalization |
| **Mid Sep** | gene-level transfer head; train on Replogle multi-line; simulate held-out-cell; pre-register rules |
| **Early Oct** | decide Layer A/B split; freeze + test submission with exact gene list & AnnData gating |
| **Late Oct → Nov 5** | test set (Oct 22); audit → ensembled final → capped submissions |

**Status (2026-08-22, hackathon day):** Milestone 0 landed and deployed —
facts assembler, audit rules, k001 seed, four enrichment tools
(degrade-verified), frontend (`frontend/build.py` → `dist/`, Playwright-verified
desktop + mobile), deploy via Netlify (`netlify.toml`). Live enrichment run in
progress; harness e2e tests added. Next
scientific step: `cell-eval` + `anndata` on **Python 3.12** (torch has no 3.14
wheel) and k001 `run --ceiling`.

---

## 7. Open decisions pending gates

1. (Gate 1) the final **six-metric aggregate**; assume the shared core until then.
2. (Gate 2) **Layer A internal resolution**: ICL vs flow transfer field,
   steered by the cheap basal-conditioning experiment.
3. (Hygiene) **counts vs log-normalized** submission encoding — must match what
   `cell-eval prep` expects (check `tutorials/vcc` + `-g` handling early).
4. (Data) whether any of the six unseen lines are already perturbed in a public
   corpus — check on validation release; legitimate if so.

*Next: Observatory Milestone 0 (today) — see `docs/observatory.md`. Then install
cell-eval (uv), stand up the harness, run the mean-shift baseline + `--ceiling`.
See `submission/README.md` and `experiments/README.md`.*
