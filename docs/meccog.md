# MecCog — kytos's role

**Challenge:** [MecCog "Papers and Findings, Step 1"](https://huggingface.co/spaces/MecCog/meccog-challenge) —
open science pilot in preclinical biology: find papers bearing on five APOE4 →
endosome-function hypotheses for late-onset Alzheimer's, and extract each
experimental finding (verbatim quote, figure/table location, effect size,
p-value, sample size, with per-stat provenance and a directness-of-evidence
grade) into a validated spreadsheet. Opened **2026-11-17**, deadline
**2027-01-15**. Humans or agents; journal publication planned with authorship
for participants in good standing.

The pipeline lives in **lemma** (`/Users/udingethe/Dev/lemma`, `MECCOG.md`
there is the plan of record). Kytos's role is the **domain counterpart**:

- **Biology judgement for directness grading.** The submission's hardest
  column pair — directness class (was A itself perturbed, or a surrogate A′?
  was B itself measured, or a surrogate B′?) and strength — is a cell-biology
  call. Kytos already works in exactly this world: CRISPRi perturbation
  response in unseen cellular contexts, endosomal/lysosomal readouts,
  astrocyte/microglia biology. Its job is to supply the surrogate-vocabulary
  (e.g. LysoSensor/LysoTracker ratio for endosomal pH, transferrin-uptake or
  surface-biotinylation for receptor recycling, cholesterol stains/filipin for
  lipid handling) and to sanity-check that extracted experiments actually bear
  on the hypothesis as worded ("non-Alzheimer's, non-aged human brain cells"
  vs the model systems papers inevitably use).
- **Observability precedent.** The Kytos Observatory pattern — per-run
  literature evidence, biological audit flags, provenance published for
  community scrutiny — is the model for how the MecCog submission should make
  its extraction trace inspectable.

## The five hypotheses (for reference)

| ID | Short name | Seed PMID |
|----|-----------|-----------|
| H1 | Lower endosome pH (astrocytes etc.) | 29946028 |
| H2 | Impaired ARF6-related receptor recycling | 31641056 |
| H3 | Increased APOE4 aggregation in endo-lysosome | 39419029 |
| H4 | Tighter APOE4 adhesion to recycling receptors | 30375977 |
| H5 | Lipid-metabolism disruption → impaired late endosome/lysosome | 37777962 |

## Working agreement

- MecCog artifacts that live here (domain notes, surrogate-vocabulary tables,
  hypothesis-boundary judgements) go under `docs/meccog/` or this file —
  **not** `experiments/`; this is a knowledge workstream, not a VCC-style run.
- No `kNNN`/`cNNN` prefixes, no VCC scorer infrastructure, no embargo rules —
  MecCog submissions are public by design (method README + commit SHA are
  required).
- Pipeline code, fetch/extract/validate drivers, and the submission sheets
  live in lemma (`meccog/`). If a biology-relevant helper (e.g. a cell-type /
  assay tagger) gets built, prefer writing it into lemma and linking it here.

## Open questions for kytos to answer

1. Per hypothesis, which assays count as **direct measurement of B** vs a
   surrogate (e.g. for H1: pHluorin/measure of endosomal pH itself vs
   LysoSensor intensity vs cathepsin activity as downstream proxy)?
2. Which experimental systems in the seed papers are "non-Alzheimer's,
   non-aged human brain cells" vs model systems — and how to phrase that in
   the Experimental system column honestly?
3. Are there second-generation iPSC/organoid APOE4 papers (post-2023) that the
   38-agent collab likely missed because they postdate its candidate pool?
