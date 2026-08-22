# Kytos — Foundation Notes

> **Kytos** (κύτος, "hollow vessel") — the Greek root from which Hooke's "cell"
> descends. We are building the cell that was never grown: a model that predicts
> how an unseen cellular context responds to perturbation, from its unperturbed
> state alone.

Created **2026-08-22**. This file is the foundation: what we're building, why the
name, what the challenge demands, and — most importantly — the distilled
learnings from every project in this catalog that feeds into it.

---

## 1. The Task (2026 Virtual Cell Challenge)

Hosted by Arc Institute; sponsored by NVIDIA, 10x Genomics, Ultima Genomics.
Register at virtualcellchallenge.org.

- **Zero-shot across cellular contexts.** No challenge training set this year.
  Models must predict CRISPRi knockdown responses in **six cell lines never
  seen perturbed**, using only:
  1. expression profiles of cells expressing non-targeting guides (the
     **basal state**), and
  2. gene identifiers for the knockdown targets.
- **Predict:** post-perturbation expression profiles as measured by CRISPRi →
  10x Flex single-cell profiling. Arc's own measurements are withheld ground truth.
- **Split:** 3 cell lines for validation + live leaderboard; 3 held back for
  final scoring.
- **Scoring:** new `cell-eval` (built with NVIDIA). Final ranking uses an
  **aggregate of six metrics** — deliberately broad so nobody optimizes the
  metric instead of the biology. Last year proved no single metric captures
  model quality.
- **Data:** 2025's full dataset (train/val/held-out) is downloadable via the
  **Arc Virtual Cell Atlas**. Perturb-seq public data is abundant; any data,
  any modeling strategy allowed.
- **Timeline:**
  - Aug 20, 2026 — validation data live, leaderboard open
  - Oct 22, 2026 — final test set released
  - Nov 5, 2026 — final submissions due (11:59 pm UTC)
  - Mid-late November — winners announced
- **Prizes:** $100K / $50K / $25K (cash + NVIDIA Brev credits).
- **Reading before building:** Altos Labs' Generalist Prize-winning preprint
  (flow-matching approach to the 2025 task).

### Why this matters (Arc's framing)
Moving the Perturb-seq workhorse assay in silico, reliably and across contexts,
changes the scale at which biology can be reasoned about — contexts that can't
be cultured or perturbed directly (rare types, primary cells, diseased states)
become predictable from data we *can* collect. The stated ambition is an
AlphaFold/ImageNet moment for cellular modeling.

### The core difficulty
Not interpolation within a context (2025's task) but **transfer**: inferring how
perturbation effects move and change between cell types. The basal state of the
new context is visible; its response to perturbation never is.

---

## 2. Why "Kytos"

Robert Hooke named cells after monk's cells (Latin *cella*, small room); the
Greek *kytos* ("hollow vessel") is the other etymological root that gave us
"cyto-" (cytoplasm, cytokine, cytosol). Naming the virtual cell after the word
that predates the thing itself fits the project: we build cells that were never
grown in a dish. Short, pronounceable, `.bio`-friendly, and distant from Arc's
own vocabulary (State, Stack, Evo, Atlas, Proto).

---

## 3. Honest Positioning

No project in this catalog is a virtual cell model. Kytos is a **fresh build**.
What the catalog contributes is infrastructure, workflow patterns, and hard-won
operational lessons — cataloged below.

**Problem and wedge (researched 2026-08-22):** Virtual cell competitions score
high-dimensional predictions on a leaderboard but provide no public layer for
biological interpretability of failure modes. Kytos Observatory fills that gap;
the predictor is the Nov 5 deliverable. Full demarcation:
[`docs/competitive-landscape.md`](docs/competitive-landscape.md).

The realistic path:

1. Baselines first (mean-shift / linear transfer from basal state) — establish
   the floor and wire up `cell-eval` locally.
2. Main model trained on public perturb-seq corpora (Atlas 2025 + Replogle /
   Norman-style datasets), flow-matching or in-context-learning formulation.
3. An agentic sanity layer (lemma-derived) that flags predictions that are
   numerically plausible but biologically implausible.
4. Disciplined submission cadence against the live leaderboard.
5. **Build in public via the Kytos Observatory** (`docs/observatory.md`) — a
   visual, engaging surface for experiment progress, audit flags, literature
   context, and external critique. Ships **day 1** (2026-08-22) as Milestone 0;
   partner enrichment (OpenAI narration, Tavily literature, fal visuals) wraps
   the deterministic core without touching the inference path.

---

## 4. Learnings From Our Projects (the actual foundation)

### lemma — evaluation philosophy & agentic science workflow
*An AI-scientist that audits scientific claims and distrusts itself.*

- **The transferable idea:** claims must be extracted, checked, and *distrusted*
  by default. Arc explicitly says the field needs people who "know when a model
  is wrong for biological rather than numerical reasons." Kytos should have a
  lemma-style audit layer over its own predictions: housekeeping-gene stability,
  pathway coherence, dose/direction consistency with known biology — separate
  from the six competition metrics.
- **Workflow pattern:** agent-generated artifacts each carry `meta.json` +
  reproducible pipeline (`reproduce/`), with generated outputs committed so the
  site needs no backend. Adopt for every experiment run: config + seed + code
  hash committed alongside predictions.
- **Lesson on scope:** lemma generalizes one audited workflow to any paper.
  Kytos should generalize one prediction formulation across all six contexts —
  resist per-cell-line hand-tuning; that's metric-gaming the biology.

### orbura — fine-tuning & release infrastructure
*Body Debt → AutoScientist Challenge submission plan.*

- **QVAC pipeline** (`scripts/qvac-worker.mjs`): quantized Qwen3 fine-tune with
  deterministic ground-truth generation. The reusable asset is the **release
  discipline**: adapted dataset AND trained weights published to Hugging Face +
  Kaggle, with measurable % improvement over baseline on a held-out set.
- **Deterministic ground-truth generators** produce unlimited labeled pairs
  without human annotation — for Kytos, the analog is simulation/pseudo-labels
  from stronger models (e.g., distilling a large perturbation model's transfers
  into a small fast one for iteration speed).
- **Structured output formats make evaluation deterministic** — no subjective
  rubric. Expression vectors are already maximally structured; keep every
  intermediate artifact (basal embeddings, predicted deltas) in fixed schemas.
- **Cautionary lesson:** orbura's domain (physiological text) ≠ this domain
  (high-dimensional regression). Reuse the harness, not the modeling assumptions.

### ratiocine — the two-phase prototyping pattern
*IOL-AI solver: Arkor rapid prototype → HF production pipeline.*

- **Phase 1 (minutes): validate the data format and approach with a fast loop**
  (Arkor studio, ~10 min/run) before committing to production training.
  **Phase 2: replicate the validated approach with standard tooling** (HF
  SFTTrainer) for the real submission. Kytos should do exactly this: validate
  formulations on 2025 Atlas data with quick small-scale runs, then scale only
  what survives.
- **Competition-harness discipline:** a `submission/script.py` that reads the
  official input paths and writes the official output format, tested against a
  frozen local copy long before deadline day. Ratiocine shipped this shape;
  Kytos must too (cell-eval expects specific prediction formats).
- **Hardware reality:** ratiocine targeted T4/16GB. Know the compute envelope
  early; NVIDIA Brev credits (part of prizes) arrive too late to design around.

### poker — operational lessons from a long-running autonomous system
*DevFun Arena agent: months of live decisions, shadow-LLM reviews, broken loops.*

- **Shadow-review linking:** reviews must be joined to decisions by explicit ID
  (`decision_id`), not by table/session — loose joins contaminated analysis at
  ~75× multiplier. Every Kytos experiment log gets run-ID-linked artifacts.
- **Provider fallback chains rot silently:** TokenRouter returned 403 on 529/529
  attempts for a week while the workhorse (Featherless) carried the load.
  Monitor every dependency continuously; a dead fallback discovered at deadline
  is a lost submission.
- **Advisory loops break quietly:** 5,469 policy suggestions, 3,136 errors,
  6 promoted. Feedback loops need health metrics or they die while appearing
  busy. The lemma-audit layer gets its own dashboard.
- **Format-change bug class:** a branch whose safety was an unstated side effect
  of a format that changed (heads-up → 2-6 handed tables silently broke an
  exploit). When the challenge releases validation data mid-run, re-validate
  every assumption conditioned on data shape — don't assume last month's
  distribution holds.
- **Spend guards:** `MAX_AUTO_REBUY_MON=0` default — no unbounded auto-spend.
  Equivalent here: cap cloud spend per experiment run, require manual override.

### weft — deterministic decisions, LLM narration only
*Post-award grant verification.*

- **The contrarian bet that works:** LLMs narrate; deterministic rules decide.
  Payment/verdict logic must be auditable and hallucination-free. For Kytos:
  the model produces numbers; any natural-language reporting about those
  numbers is generated *from* them, never independently. No LLM in the
  prediction path.
- **Fixed evidence checklists** beat open-ended judgment. Encode biological
  sanity checks as fixed, inspectable rules (gene sets, expected correlation
  structures), not vibes.

### matcha-hack — anti-hallucination as product thesis
*Café briefing: numbers computed by code, LLM for perception + prose only.*

- Every claim rendered anywhere must trace to a computed fact object. If Kytos
  has any human-facing surface (leaderboard tracker, audit report), it renders
  from a facts JSON — nothing else.
- Planted-signal methodology: seed known-answer cases (e.g., reproduce a
  published perturbation result end-to-end) to prove the pipeline finds what's
  there before trusting what it predicts.

### elcaro — serving predictions as a registered API
*Telegraph miner for injection detection.*

- Config-driven service description (`config.yaml`: endpoints, intents,
  request/response schemas, pricing) pinned to IPFS and registered on-chain.
  If Kytos predictions ever become a served capability (x402-metered inference
  for other agents), this is the pattern — post-challenge, not during.
- Untrusted-input discipline: treat all fetched content as untrusted text;
  introspect endpoint shapes before depending on them. Applies to scraping
  public perturbation databases.

### famile — literature grounding
*Mira's research layer: Firecrawl over 41M+ life-science papers.*

- Provenance, not prescription: retrieval grounds claims without turning papers
  into recommendations. The lemma-audit layer can cite supporting literature for
  flagged anomalies — evidence retrieval never takes the prediction path dark.
- Degradation posture: if the key is missing or the call fails, return empty
  context and continue — auxiliary enrichment must never block the core loop.

### stoppage / lenitnes / ligis — verification & provenance habits
- Cryptographic gating on verified proof (stoppage), notarization of results
  (lenitnes/HCS), portable credentials (ligis): if Kytos produces something
  worth trusting, hash-and-anchor the artifact (config + weights hash +
  prediction file) so any claimed result is reproducibly attributable.
- Pre-registration discipline (lenitnes): register hypotheses/expected effect
  directions before peeking at validation leaderboard feedback, to avoid
  overfitting the public split.

---

## 5. Synthesis — What Kytos Takes From Each

| Source | Take |
|---|---|
| lemma | Audit layer: distrust predictions biologically, not just numerically; meta.json + reproduce/ per run |
| orbura | Fine-tune→HF/Kaggle release harness; deterministic eval via structured outputs |
| ratiocine | Two-phase validate-then-scale; frozen-format submission script tested early |
| poker | Linked experiment logs; monitored dependencies; healthy feedback loops; spend caps; re-validate on data-shape change |
| weft | Deterministic core, LLM narration only; fixed checklist sanity rules |
| matcha-hack | Facts-JSON rendering; planted-signal pipeline proofs |
| elcaro | Config-driven API surface (later); untrusted-input hygiene |
| famile | Literature grounding with graceful degradation |
| stoppage/lenitnes/ligis | Artifact hashing/provenance; pre-registration against leaderboard overfitting |

## 6. Open Questions (to resolve during Phase 0)

1. Flow-matching (Altos' winning approach) vs in-context learning (Arc's Stack)
   vs simpler delta-prediction baselines — read the preprint first.
2. Which public corpora best cover tissue diversity for the six unseen lines?
   (Atlas 2025 first; then Replogle/Nadig-scale genome-wide screens.)
3. How much does basal-state conditioning alone buy? Build the "predict the
   mean shift scaled by context similarity" baseline before anything fancy.
4. Compute budget and where it comes from (local, cloud credits, Brev later).
5. Submission cadence policy: how often to touch the live leaderboard without
   overfitting the validation split (see lenitnes pre-registration lesson).

---

*Next (hackathon day, 2026-08-22): finish the live enrichment run (Dev A),
connect Netlify for the deployed Observatory (Dev B), record the
2-min Loom (Dev C). Science track: `cell-eval 0.8.2` + `anndata` are now
installed in **`.venv-science`** (native arm64 3.12.8 — the Rosetta x86_64
3.12 has no llvmlite/numba wheels) and the harness obs contract is **verified
against cell-eval source** (`target_gene` / `non-targeting`) and passes
`cell-eval prep`. Next: download Atlas 2025, run k001 through
`cell-eval run --ceiling`, register, read the Altos preprint, and publish the
first run page. Milestone 0 progress:
[`docs/milestone-0-worksplit.md`](docs/milestone-0-worksplit.md).*
