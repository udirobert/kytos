# Kytos — the program after VCC 2026

Status: **ACTIVE** · Written **2026-11-20** · Owner: udingethe

VCC 2026 is concluded (final entry `kytos-k043-final-sagr-dm`; analysis in
[`vcc-postmortem.md`](vcc-postmortem.md)). Kytos continues as an **open
virtual-cell research program** — the same bet we ran during the challenge:
publish every run, its evidence, and its failure modes, and let the
methodology be the product. This doc ranks the avenues worth pursuing next,
ordered by expected leverage per unit of our actual constraints (solo, 8 GB
local, CPU VPS + Modal + occasional rented GPU).

Avenues A–D share one asset: the perturbation-response evidence engine the
post-mortem says we should have built. Avenues E–G are existing workstreams
that continue on their own tracks.

---

## A. Engine v2 — the statistical response atlas (flagship)

**What.** Rebuild the evidence layer around per-dataset statistics instead
of pooled mean shifts: per gene × target × dataset, extract **LFC +
standard error + BH significance** (covariate-adjusted regression where
the design allows, Welch-t otherwise), then combine across datasets with
inverse-variance / random-effects meta-analysis — the BioInsight
representation, on public data.

**Why.** The wrap-up confirms the diagnosis: every podium entry was a
modular transfer pipeline whose edge was *statistical depth*, not
architecture. Our PDS 0.62 proves the transfer substrate works; the
missing layers (DE-set prediction, precision weighting, noise-floor
calibration) are exactly what this engine provides, and each layer is
independently useful beyond VCC scoring.

**Phases (each is a shippable artifact).**

1. **DE-table harvest.** Re-extract our five existing sources (Replogle
   K562, X-Atlas HCT116/HEK293T, CD4, plus 2025 VCC data) as LFC+SE
   stores — the k036 per-sample re-extraction generalized. CPU-safe.
2. **Bulk corpus ETL.** ENCODE, LINCS, PerturbAtlas, KnockTF, ARCHS4 —
   the ~200-screen public harvest FlowState used (222 datasets / 128
   studies / 86 contexts, half bulk). Once the unit is LFC+SE, bulk and
   single-cell pool trivially. Pure CPU ETL + harmonization; the largest
   known gap in our 2026 coverage.
3. **Meta-analysis layer.** Per-gene/per-pert weights from noise,
   KD efficiency, control similarity, and between-source disagreement —
   fit by leave-one-line-out on our own sources (the k041 machinery,
   repurposed as a fitting harness rather than oracle auditing).
4. **DE-set + calibration heads.** Explicit "detectable response"
   predictor and effect sizes shrunk toward a 400-cell pseudobulk noise
   floor — where jac/reach/fid/nmae (2/3 of the VCC score) live. Winners
   themselves over-called DE by 3–20×, so this is an open problem, not a
   solved one.
5. **Context adaptation.** Small correction layer on top (SVD+ridge, or
   per-gene heads on one L40S). Organizers measured everyone's
   context-specific slope at 0.02–0.13 — a tiebreaker, not the ticket.

**Design:** [`engine-v2-design.md`](engine-v2-design.md) — evidence
schema, corpus inventory, meta-analysis, DE-set layer, eval harness,
k2NN run plan. Runs land on the Observatory as `k2NN-*` (VCC run-ID
namespace continues — the Observatory tracks experiments, not
competitions).

## B. VCC 2027 readiness

**What.** Arc confirmed the challenge returns next summer (annual, $100k,
CASP-style cadence). VCC 2027 will likely keep the zero-shot,
held-out-context shape with cell-eval2 scoring.

**Why.** We now have the winner-validated recipe, a pinned scorer, a
public submission pipeline (Modal builds → vcc CLI → receipts), and 78
days of run history showing exactly which axes were exhausted. Engine v2
(§A) *is* the 2027 entry — phases 1–3 alone plausibly land top-5 to
podium range (post-mortem estimate: ~0.35–0.43 on the 2026 test panel).

**Watch items.**

- New year, new failure modes: the 171 new-panel targets cost the field
  ~0.025 PDS each — coverage of *unscreened* targets (we fell back to
  STRING neighbors; ANG had zero coverage) is where 2027's margin lives.
- Test-panel context identity will differ — context adaptation (§A.5)
  is worth building before it's needed.
- cell-eval2 is [open source](https://github.com/ArcInstitute/cell-eval2)
  now — pin it and re-run our full audit suite against it.

## C. Standing benchmarks — score the engine where there's no deadline

**What.** Run engine-v2 outputs against public benchmarks that are open
year-round:

- **OpenProblems `task_perturbation_prediction`** (OP3, NeurIPS 2023 →
  standing benchmark): chemical perturbations in PBMCs, held-out
  (compound, cell-type) pairs. Different modality (small molecules, not
  CRISPRi) — a clean generality test for a target-agnostic evidence
  engine. Submissions are PRs, not leaderboards with deadlines.
- **Tahoe-100M** (public 100M-cell perturbation atlas) as a held-out
  corpus: harvest it as a *source* in §A.2, or hold it out to evaluate
  cross-atlas transfer the way the winners used internal held-outs.
- **Arc State models** (SE-600M, ST-Tahoe/Parse/Replogle, non-commercial
  HF weights): usable as a *baseline to beat* and as a potential source
  of per-gene responses where measurements are absent (X-team used a
  foundation model exactly this way — as a gating oracle over measured
  effects, not a generator).

**Why.** VCC gave us a scoreboard that resets annually. Standing
benchmarks give continuous signal on whether engine v2 is actually
getting better — and published OP3 results are a citation-grade
artifact, not just a leaderboard row.

## D. The audit layer — Kytos's differentiator

**What.** The Observatory already publishes what no competitor does:
per-run audit flags, ceiling headroom, literature-grounded evidence, and
confession banners. Post-VCC, extend that into scorer-level analysis:
cell-eval2 is open, the metrics preprint is out, and the wrap-up credits
"community analysts whose work changed how we score" — that lane is real
(see GlioState's PDS-amplitude analysis, Team Outlier's arXiv critique).

**Why.** Our strongest muscle this season wasn't prediction, it was
*measurement* — byte-identical rescoring, pinned scorers, probe
discipline, the pds↔reach anticorrelation result. Publishing cell-eval2
failure-mode analyses (e.g., where each of the six metrics rewards
non-biological behavior) is cheap, fits the 8 GB machine, and builds
exactly the reputation the organizers explicitly value.

**Next artifact:** a `tools/cell_eval2_audit/` series — each audit ships
as an Observatory run page + a short chronicle note.

## E. Quantum allostery (Cleveland / GQAI) — separate track

Continues under `cNNN-*` rules. c008 proved the pipeline: protein
contact-graph coupling maps → Moth `graph-v1` on IBM `ibm_fez`,
Pearson 0.98 tomography read-back, and our own Laplacian CTQW compiled
to OpenQASM (Pearson 0.991 vs expm). Engine-blocked at the hackathon
deadline; the avenue is retrying `tomography-api-v2` (now
deadline-free), then scaling to the distal-lever hypothesis where myosin
rank-3 is the live result. `/quantum/` stays as the public exhibit.

## F. MecCog — literature-mechanism extraction (deadline 2027-01-15)

APOE4/endosome evidence extraction; pipeline lives in `lemma`, kytos
supplies directness grading and surrogate-assay vocabulary. Same muscle
as §A.3 (weighting evidence sources by reliability) applied to papers
instead of screens — and a near-term deadline, so it precedes heavy
engine work.

## G. The Observatory itself

The site is now the program's standing surface rather than a competition
companion. Ongoing: publish the formerly-embargoed receipts (done —
`experiments/_embargoed/` is tracked as of 2026-11-20), keep the
chronicle short-form channel, and treat each avenue's first artifact as
a run page. Candidate external surfaces if a piece lands: a JOSS-style
paper or workshop demo on the audit layer (§D).

---

## Ecosystem tailwinds (deep research, 2026-11-20)

The macro bet behind §A–D is stronger than it looked from inside the
competition:

- **A data flood is coming.** CZI/Biohub's Virtual Biology Initiative is a
  **$1.8B global commitment** (announced April 2026, $500M Biohub anchor)
  to generate AI-ready open datasets. The Billion Cells Project (10x,
  Ultima, Scale Bio) and the Tahoe–Arc–Biohub perturbation-atlas effort
  (Jan 2026) mean the public corpus we under-harvested in 2026 will be
  much larger by 2027. The bottleneck shifts from *having* data to
  *weighting* it — exactly engine v2's job.
- **Our niche is unoccupied.** scPerturb (44 datasets) and PerturbSeq.db
  harmonize *raw* perturbation data; OpenProblems/scPerturBench/
  xianglin226's model library standardize *benchmarks*; nobody ships a
  cross-dataset **statistical consensus layer** (LFC + SE + significance,
  precision-weighted, disagreement-aware). That gap is the product.
- **The evaluation lane is a real venue.** The "community analysts whose
  work changed how we score" line in the wrap-up is backed by an active
  literature — scPerturBench, the Science Advances systematic
  comparison, and the July-2026 "Towards Principled Evaluation"
  preprint. cell-eval2 audits (§D) land in a field that publishes and
  cites this work.
- **Quantum allostery just went mainstream.** Cleveland Clinic + RIKEN +
  IBM simulated a 12,635-atom protein on quantum hardware (May 2026) and
  are Gordon Bell finalists — and Cleveland Clinic is the same
  institution behind our GQAI workstream. Their lane is electronic
  structure; ours (CTQW transport on contact graphs) is orthogonal
  dynamics. The institution's appetite for quantum-bio work is proven.
- **Standing channels exist for everything.** OpenChallenges.io (Sage
  Bionetworks) aggregates biomedical challenges — VCC, DREAM, CACHE —
  so the next venue is discoverable without watching individual orgs.

## Funding & revenue (deep research, 2026-11-20)

Ranked by fit × effort. Kytos is an independent open research program —
non-dilutive money first.

**Grants — high fit, apply as artifacts land.** (We are **not US-based**;
US small-business programs like NIH SBIR/STTR are off the table.)

- **Emergent Ventures** (Mercatus / Tyler Cowen) — $1k–$50k+, solo- and
  high-risk-friendly. **Applied, awaiting decision** (2026-11).
- **CZI Essential Open Source Software for Science (EOSS)** — recurring
  cycles, **$50k–$250k** per award, open worldwide incl. individuals via
  fiscal sponsors/orgs. Requires "demonstrated impact" — so sequence
  after engine v2 has published artifacts (§A.1–2) and OP3 results (§C).
- **CZI AI Meets Biology GPU Compute RFA** — compute grants aimed at
  exactly our resource constraint (engine v2's heavier phases).
- **NIH PAR-26-040** (NLM R01: AI/ML bioinformatics/computational
  biology) — foreign institutions and small businesses both eligible;
  bigger lift, but "evidence-engineering infrastructure for
  perturbation biology" is squarely in scope.
- **Fast Grants lineage** — Biswas Family Foundation now runs the
  program (early-career pivots into ambitious fields); New Science funds
  independent young researchers.

**Non-US structural options (if an entity exists or is formed).**

- **EIC Accelerator** (EU/Horizon Europe) — grant-only track up to
  **€2.5M** (+optional equity) for deep-tech SMEs in EU member states or
  associated countries; UK companies are currently eligible for the
  grant component. Needs a for-profit SME — real money, real lift.
- **Innovate UK** — Smart Grants paused since Jan 2025 (no FY25/26
  rounds); themed competitions do recur (Frontier AI SME Champions ran
  Oct 2026). Watch the Innovation Funding Service for life-sciences /
  digital AI calls rather than waiting for Smart.
- **Horizon Europe health topics** (€528M, 2027 deadlines) —
  consortium-scale; likely out of scope solo, listed for completeness.

**Prizes — what we already know how to win.**

- **VCC 2027**: $100k grand + $50k/$25k podium tiers; annual cadence.
- **OpenChallenges.io** (Sage Bionetworks) aggregates DREAM/CACHE-style
  biomedical challenges — quarterly venue scan, prize pools recur.
- Quantum hackathons (Moth/IBM ecosystem) for the allostery track.

**Opportunistic.**

- **Commercial services** — the funded virtual-cell startups (Tahoe,
  Xaira, Isomorphic, Isomorphic-adjacent DMTA shops like Rivercell at
  $25M seed) own the *prediction* lane. Nobody owns the
  *evidence/audit* lane. As the VBI data flood lands, labs generating
  perturbation screens will need QC, DE-evidence extraction, and
  scoring-calibration tooling — a services/API wedge exists if we want
  it, but it trades against research time; keep it opportunistic.
- **GitHub Sponsors / open collective** — near-zero revenue but zero
  cost and signals community support in grant applications.

**Cheapest credibility assets we already have:** 26k-word public run
history, the post-mortem, published receipts (embargoed tree now open),
and a working transparency site. Every grant above reads as evidence,
not promise.

## Explicitly not pursuing

- **A foundation model.** The podium says the leverage is in evidence
  statistics; X-Cell's own team demoted their model to a gating
  function. If a pretrained oracle is needed, Arc's State weights are
  public (§C) — training our own is out of scope at our compute tier.
- **Private data moats.** Illumina's billion-cell atlas won first place;
  the public-data path is FlowState's proof. Our edge is method +
  transparency, not corpus scale.
- **Leaderboard chasing.** No more probe-by-submission workflows; every
  avenue above produces a citable artifact with or without a scoreboard.

## Near-term checklist

| # | Action | Track |
|---|---|---|
| 1 | Retrieve k043 final score — snapflip-vultr is **decommissioned**; path is re-authing the `vcc` CLI locally with the virtualcellchallenge.org account, or the final board going public | housekeeping |
| 2 | ~~`docs/engine-v2-design.md`~~ **done** (2026-11-20) — DE-table schema, corpus inventory, LOLO fitting plan | A |
| 3 | Re-extract Replogle + X-Atlas per-sample LFC/SE stores on Modal | A.1 |
| 4 | cell-eval2 pinned install + audit harness port | D |
| 5 | OP3 task_perturbation_prediction — read the API, scope a baseline submission | C |
| 6 | MecCog directness-grading pass (deadline Jan 15) | F |
| 7 | Track CZI EOSS / AI-Meets-Biology RFA cycles for an engine-v2 proposal | funding |
| 8 | Bookmark OpenChallenges.io; set a quarterly venue scan | housekeeping |
| 9 | Emergent Ventures — applied 2026-11, awaiting decision | funding |
| 10 | Watch Innovate UK IFS for frontier-AI / life-sciences calls (Smart Grants paused); EIC Accelerator needs a for-profit entity decision | funding |
