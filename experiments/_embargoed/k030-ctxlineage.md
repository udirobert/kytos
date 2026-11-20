# k030 — context-lineage weighting + complementary-corpus audit (embargoed)

Local-only working notes until Oct 22. Public side: code/tools only.

## 2026-09-24 — complementary-corpus audit (first pass)

Panel = 300 targets (2026). Existing source coverage: k562 272, hct116 300,
hek293t 300, cd4 251-quality/282-raw, h1-2025 13, essential screens 0.

New candidate sources found:

| Source | Lineage | Panel overlap | Format | Access |
|---|---|---|---|---|
| GSE249595 (Jurkat E6, genome-wide CRISPRi Perturb-seq, unstim+stim) | Jurkat (context A match) | **299/300** | 16× 10x channels, 3.75 GB RAW.tar | GEO, public |
| HIPSCI genome-scale iPSC CRISPRi (bioRxiv 2024.11.28.625833, figshare 26819743) | iPSC pluripotent (eval/C match) | **182/300** (219/343 incl eval targets) | published LFC tables (794 MB tsv.gz) | figshare, public |
| KOLF2.1J iPSC atlas (Nat Biotech s41587-026-03199-w, figshare 27261219) | iPSC pluripotent | **282/300** (obs/gene_target categories) | 46.7–189 GB h5ad | figshare, heavy |
| RPE1 Perturb-seq (Replogle 2022) | RPE1 (context B lean) | essentials only, 0/300 | — | dead end (again) |

Status:
- `deltas_hipsci.npz` extracted locally 2026-09-24 (219/343 covered, units
  = publisher lfc; self-KD 80% negative — sign OK; vs K562 unit cosine
  ~0.02 — near-orthogonal as expected).
- Jurkat extraction done 2026-09-24 (`tools/modal_k031_jurkat_extract.py`,
  run `jurkat-20260924-02`, app ap-IbOby93Fq6ZSxoA4hhXsi0): stim arm
  **341/343 covered** (median 60 cells/target, 3,448 stim NTCs);
  rest arm dead by design (~10% untreated × 1.4% panel-of-library →
  377 rest NTCs, 3 covered). Self-KD 76.5% negative (sign OK);
  vs K562 unit cosine ~0.003 — orthogonal, new signal. Deltas live at
  `experiments/k030-ctxlineage/src-deltas/deltas_jurkat_stim.npz` +
  `basal_jurkat.npz` on the volume (k031-jurkat/jurkat-20260924-02).
  Note: guide calls use unique-argmax at ≥1 UMI (assay ~0.76 nnz/cell).
- Offline screen: +jurkat uniform shifts consensus direction
  (median cos-to-4src 0.90; eb2 0.73; +hipsci adds more).
- Gate B arms uploaded: `k030-ctxlineage/newsrc-5j/` (cons_mean +
  cons_eb2 with jurkat) and `newsrc-6jhip/` (eb2 with jurkat+hipsci).
- Gate launched 2026-09-24: `modal_k030_ctxw_gate.py` run
  `gate-20260924-01`, app ap-XVlJEzCOb4t8sS5kkCIcBR — arms:
  cons_eb2_ref (anchor), cons_mean_j, cons_eb2_j, cons_eb2_jhip.
  ctxw arms auto-skip until CTXW_DIR populated (needs hek293t basal).
- KOLF2.1J obs/gene_target readable via fsspec ranges (189 GB file);
  delta extraction needs per-target cell expression reads — deferred
  until Jurkat+HIPSCI value is shown; Strong_Perturbations 46.7 GB is
  the medium-weight alternative.
- X-Atlas contains ONLY HCT116 + HEK293T (checked repo tree) — no hidden
  lineages.

## ctxw arm design (in flight)

- `tools/modal_ctxlineage_basal.py` — basal log1p control means for the 4
  sources (X-Atlas NTC scan; K562 bulk; CD4 baseMean median over Rest
  contrasts) + contexts A/B/C + eval (Atlas validation NTC). Similarity =
  pearson on top-2000 context-discriminative genes (k012 metric).
- Weights: `w_ctx[s] = BASE_W[s] * relu(disc_sim)^p` normalized to sum 5,
  p in {1,2} + `top` argmax. Fallback to BASE_W when all sims <= 0.
- `tools/build_ctxw_consensus.py` — per-context weighted consensus; eb2
  variant applies the UNWEIGHTED eb2 lam to the weighted mean (isolates
  the weighting change).
- Gate B arms (modal_k030_ctxw_gate.py): cons_ctxw2_eb2_ctr,
  cons_ctxw1_eb2_ctr, cons_ctxw2_ctr (no-eb ablation), cons_eb2_ref anchor.
- Gate B only tests the `eval` (hESC) weight vector; A/B/C weightings are
  validated only by mechanism, not per-context.

## Within-source reliability (k032, rel-20260924-01)

Replogle K562 single-cell (figshare 35775507, dense 1.99M x 8,248):
split cells by gem_group parity -> repA/repB deltas per target.
- Pooled-vs-k023 sanity: median cosine 0.957 (pipeline correct).
- 297/343 targets covered in both halves (>=30 cells/half).
- **Median replicate cosine 0.093** (p10 -0.085, p90 +0.348) —
  within-source shot noise dominates at ~65 cells/half; the top-decile
  tail is the gateable signal. This reframes the trust-gate failures:
  cross-source agreement was measuring noise-vs-noise.
- reliability_k562.json + deltas_k562_rep{A,B}.npz on volume
  (k032-replogle-rel/rel-20260924-01/).

## ctxlineage report (basal-20260924-01)

Discriminative-gene Pearson (context -> source basal):
- eval(hESC): hek293t .428 > k562 .359 > hct116 .343 >> cd4 .152
- A: cd4 .472 > k562 .401 > hek293t .308 > hct116 .249  (T-cell lean OK)
- B: hct116 .329 > hek293t .282 > k562 .230 > cd4 .172
- C: hct116 .431 > hek293t .297 > k562 .292 > cd4 .233
p2 eval weights: {k562:2.22, hek293t:1.57, hct116:1.01, cd4:0.20}.
ctxw variants built (build-ctxw/), 3 eval arms on volume at
k030-ctxlineage/basal-20260924-01/variants/; gate-20260924-02 queued.

## Gate B arm results (gate-20260924-01/02/03, avg_score from_replicate)

Anchor cons_eb2_ref = 0.2545.
- cons_mean_j (uniform +jurkat): 0.2578 (+0.003)
- cons_ctxw2_eb2_ctr (p2 ctxw): 0.2565 (+0.002)
- cons_ctxw1_eb2_ctr (p1 ctxw): 0.2565 (+0.002)
- cons_ctxw2_ctr (ctxw, no eb): 0.2515 (-0.003) -- eb does the work,
  not the weights
- cons_eb2_rel (delta x relu(cos_rep)): 0.2186 (-0.036) -- FALSIFIED
- cons_eb2_relsqrt (sqrt gate): 0.2255 (-0.029) -- FALSIFIED

Read: within-source reliability gating REMOVES signal (pds_cosine
0.72 -> 0.58); noisy-but-real deltas beat zeroed ones. ctxw basal
weighting ~neutral on eval context. Pending: cons_eb2_j / cons_eb2_jhip
(champion recipe + new sources) -- the decisive new-information test.

## Gate B final table (avg_score, from_replicate anchor; all 9 arms)

| arm | avg | d_ref | pds_cos | note |
|---|---|---|---|---|
| cons_eb2_ref | 0.2545 | -- | 0.7239 | champion recipe anchor |
| cons_mean_j | 0.2578 | +0.003 | 0.7649 | +jurkat plain mean: BIGGEST pds gain (+0.041) |
| cons_ctxw2_eb2_ctr | 0.2565 | +0.002 | 0.7316 | ctxw ~neutral |
| cons_ctxw1_eb2_ctr | 0.2565 | +0.002 | 0.7306 | ctxw ~neutral |
| cons_ctxw2_ctr | 0.2515 | -0.003 | 0.6916 | ctxw w/o eb hurts |
| cons_eb2_jhip | 0.2468 | -0.008 | 0.7201 | eb2 + 2 orthogonal sources |
| cons_eb2_j | 0.2452 | -0.009 | 0.7011 | eb2 + jurkat |
| cons_eb2_relsqrt | 0.2255 | -0.029 | 0.5973 | FALSIFIED |
| cons_eb2_rel | 0.2186 | -0.036 | 0.5868 | FALSIFIED |

Cross-run check: gate-01/gate-02 scored shared arms bit-identically --
harness deterministic, cross-run comparison safe.

## Interpretation (2026-09-25)

1. Jurkat signal is REAL: adding it to a plain mean lifts pds_cosine
   +0.041 (0.724 -> 0.765), largest discrimination gain observed.
   But it only helps as an additive mean component.
2. eb2 agreement shrinkage is INCOMPATIBLE with orthogonal new sources:
   jurkat/hipsci (cos~0 vs K562) register as disagreement -> shrinkage ->
   signal destroyed (cons_eb2_j -0.009 vs cons_mean_j +0.003).
3. Trust-gate via within-source replicate cosine: FALSIFIED.
   relu/sqrt gating craters pds (-0.13/-0.14). Noisy-but-real deltas
   beat zeroed ones; within-source noise != non-transferability.
4. ctxw basal weighting ~neutral on eval ctx (+/-0.003). Per-context
   weights exist but don't move the needle under this recipe.
5. NEXT VARIANT hypothesis: eb2 shrinkage on the ORIGINAL 4 sources
   only, then jurkat added post-shrinkage as fixed-weight additive
   component (optionally A-context only). Isolates jurkat's signal
   from the agreement computation. 1-2 gate arms to test.
6. Submission bar not met: best arm +0.003 << 0.02-0.03 transfer
   threshold. No slot spent. k027 stays champion.

## Post-shrinkage + anchor arms (gate-20260925-01/02/03)

| arm | avg | d_ref | pds_cos |
|---|---|---|---|
| cons_mean_ref (4-src plain mean) | 0.2584 | +0.004 | 0.7535 |
| cons_mean_ctr_ref (mean + ctr) | 0.2546 | +0.000 | 0.7354 |
| cons_w_ref (weighted 2:1:1:1) | 0.2530 | -0.002 | 0.7516 |
| cons_eb2post_j2 (eb2 4src + jurkat post a=0.2) | 0.2473 | -0.007 | 0.7173 |
| cons_eb2post_j2_ctr (+ ctr) | 0.2466 | -0.008 | 0.7106 |
| cons_w_ctr_ref (K027 CHAMPION recipe) | 0.2464 | -0.008 | 0.7144 |
| cons_eb2post_j4_ctr (a=0.4) | 0.2245 | -0.030 | 0.6258 |

## MAJOR FINDING: Gate B recipe ordering is INVERTED vs official

k027's actual deltas (consensus_w_ctr) rank ~12/16 locally (0.2464),
yet beat k029's eb2 recipe officially by +0.015 (0.1262 vs 0.1115).
Locally eb2 > w_ctr by +0.008. Sign flip, not just attenuation.

Mechanism: Gate B's eval subset is hESC-only (47 paired targets);
the official test spans contexts A/B/C (Jurkat-like, RPE1-leaning,
hESC-leaning). K562-upweighting + ctr hurts on hESC eval but wins on
the real mixed-context test. Gate B therefore (a) catches catastrophic
failures (rel-gate correctly flagged), (b) validates generation
mechanics, but (c) CANNOT arbitrate source-mixing recipes — its recipe
ordering anti-predicts the official one.

Secondary findings:
- Jurkat adds pds_cosine +0.011 on plain mean (0.7535->0.7649) but is
  net-neutral on avg (+0.003 vs mean is -0.0006). Because the eval
  subset under-weights context-A relevance, Jurkat's true official
  value is UNMEASURED locally -- cons_mean_j could be better than
  Gate B suggests.
- eb2 shrinkage is locally net-negative vs plain mean (-0.004) and
  officially negative (k029 -0.0147 vs k027). Agreement shrinkage on
  4 noisy sources removes more signal than it keeps.
- Post-shrinkage jurkat does NOT rescue under eb2 (a=0.2: -0.008,
  a=0.4: -0.030; clean dose response). Dead end confirmed.
- ctr centering costs ~0.004 locally on mean recipe.

## Strategic conclusion (2026-09-25)

Local gating of source-mixing recipes is exhausted -- the eval context
bias means recipe choices must be decided on priors + scarce official
slots. Remaining levers that local gates CAN still arbitrate:
generation-side mechanics (dm params, library cap) since those are
context-agnostic; catastrophic-failure screens for new variants.
For source mixing: either submit structurally distinct candidates
(cons_mean_j is the most defensible: real new signal, cheapest
interpretation) or build a context-matched eval (needs labeled
perturbation data in A/B/C-like contexts -- Jurkat stim IS context-A-
like and is self-evaluable: leave-out targets within Jurkat as an
A-context gate).

## Source self-eval (context-matched delta transfer; tools/source_selfeval.py)

Held-out in-source ground truth: predict each source S's measured
per-target deltas from OTHER sources only; unit-cosine vs real delta.
Report: experiments/_embargoed/k030-selfeval/report.json.

| eval ctx | best single | consensus mean | w_k562x2 | oracle |
|---|---|---|---|---|
| jurkat_stim (ctxA-like) n=341 | k562 +0.002 (!) | -0.007 | -0.005 | +0.082 |
| hipsci iPSC (hESC-like) n=219 | k562 +0.026 | +0.016 | +0.018 | +0.051 |
| k562_repA n=300 | k562-pooled +0.708 | +0.144 | +0.231 | +0.708 |
| k562_repB n=298 | k562-pooled +0.716 | +0.147 | +0.235 | +0.716 |
| hct116 n=343 | hek293t +0.247 | +0.059 | +0.053 | +0.304 |
| hek293t n=343 | hct116 +0.247 | +0.055 | +0.047 | +0.317 |
| cd4 n=282 | hek293t +0.030 | +0.019 | +0.019 | +0.051 |

Reads:
1. CONTEXT-A IS UNSERVED: no available source predicts Jurkat
   responses (all ~0, consensus slightly NEGATIVE). Champion's
   context-A directions are baseline-quality. jurkat_stim deltas are
   the ONLY real A-context signal in existence for us -- strongest
   possible prior for cons_mean_j-style inclusion.
2. Trust-gate ceiling is context-dependent and mostly LOW:
   oracle +0.05-0.08 for jurkat/hipsci/cd4; +0.30 only for the
   epithelial pair (real cross-lineage transfer exists ONLY between
   related lineages: hek293t<->hct116 +0.247).
3. Within-source consistency is HIGH at pooled level (k562 pooled ->
   rep 0.71): the earlier 0.093 was rep-vs-rep shot noise at ~65
   cells/half. Deltas are reliable; transfer is what fails.
4. For a K562-context eval, w_k562x2 > mean (+0.23 vs +0.14) --
   upweighting the matched source wins, consistent with w_ctr's
   official win. Mixing only helps when sources are comparable.
5. Dilution hurts when a matched source exists (hct116 eval:
   hek293t alone +0.247 vs mean +0.059). For contexts WITHOUT a
   matched source, mixing ~ nothing to lose anyway (all ~0).

## k030 official result (entry A1N2nYKZ07jKewReEUMp)

score_avg +0.1088, rank 442 -- REGRESSION -0.0174 vs k027 (+0.1262).
Components: pds 0.557, mse 0.00176, nmae +0.0735, fid -0.0197,
reach +0.0393, jac +0.0012.

Third consecutive regression (k028 -0.0023, k029 -0.0147, k030 -0.0174).
Confounded: cons_mean_j changed BOTH recipe (w_ctr -> plain mean, no
ctr, no k562 upweight) AND added jurkat -- cannot decompose officially.
Either jurkat's A-context signal didn't pay, or losing w_ctr's
K562-upweight + ctr cost more than jurkat added. The local self-eval
prior (ctxA unserved) remains true, but the aggregate score shows the
recipe change was net-negative. k027 stays champion; submission slots
should now be treated as exhausted for recipe-level experiments --
remaining levers are generation-side or genuinely new data.
