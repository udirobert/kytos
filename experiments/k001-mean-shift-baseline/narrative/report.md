<!-- kytos narrative · generated_by=llm · provider=venice · model=stealth-ox-alpha · 2026-08-22T12:49:02+00:00 UTC -->

# Run Digest: `k001-mean-shift-baseline`

**Headline:** The basal mean-shift baseline achieved a DESigGenesRecall of 0.12 and a pearson_delta of 0.08 (facts: headline_metrics), leaving substantial headroom to the ceiling of 0.45 recall and 0.31 pearson_delta (facts: ceiling_headroom).

## Key Findings

- **Large gap to ceiling:** Baseline recall (0.12) sits well below the ceiling value of 0.45 (facts: headline_metrics.DESigGenesRecall; facts: ceiling_headroom.DESigGenesRecall), suggesting basal co-expression alone captures only a small fraction of cross-context transfer performance.
- **Preregistered hypothesis confirmed:** The run preregistered that "Basal co-expression alone explains <20% of cross-context transfer on DESigGenesRecall" — the observed 0.12 is consistent with this claim (facts: hypotheses_preregistered[0]; facts: headline_metrics.DESigGenesRecall).
- **Second hypothesis also consistent:** The prediction that the mean-shift baseline would sit below 50% of ceiling on pearson_delta holds: 0.08 is roughly a quarter of the 0.31 ceiling (facts: hypotheses_preregistered[1]; facts: headline_metrics.pearson_delta; facts: ceiling_headroom.pearson_delta).

## Audit Flags

- **Housekeeping shift (warn):** ACTB and GAPDH shifted up to +2.10 log2FC against a ±1.0 threshold, with ACTB peaking (facts: audit_flags[hk-stability]).
- **Pathway coherence (warn):** The `interferon_response` pathway shows mixed directionality among measured genes ISG15, IFIT1, MX1, and OAS1 — two up, two down (facts: audit_flags[pathway-interferon_response]).

## Provenance

Commit `2fe7bd7f4f0902b454d0f2face73f917e6e065d5`, seed 0, code hash `k001-mean-shift-v0` (facts: provenance).
