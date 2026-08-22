<!-- kytos narrative · generated_by=llm · provider=venice · model=stealth-ox-alpha · 2026-08-22T17:02:25+00:00 UTC -->

# Run Digest: k001-mean-shift-baseline

**Headline:** The basal mean-shift baseline lands far below ceiling on both metrics, confirming that basal co-expression alone carries only a small fraction of cross-context transfer signal.

## Results

The probe reached a DESigGenesRecall of 0.12 against a ceiling headroom of 0.45, and a pearson_delta of 0.08 against a ceiling of 0.31. Both preregistered hypotheses were consistent with the outcome: recall of 0.12 falls under the 20% threshold proposed for basal co-expression explaining cross-context transfer, and the pearson_delta sits well below half of its ceiling value.

## Audit Flags

Two warnings were raised:

- **Housekeeping stability (hk-stability):** The housekeeping genes ACTB and GAPDH shifted up to +2.10 log2FC, exceeding the ±1.0 threshold, with ACTB at the peak. This suggests the basal normalization assumptions underlying the mean-shift baseline may be compromised in this run.
- **Pathway coherence (interferon_response):** The interferon_response pathway shows mixed directionality among measured genes — 2 up and 2 down across ISG15, IFIT1, MX1, and OAS1 — so pathway-level interpretation should be treated cautiously.

## Caveats

This run is labeled as a probe, not a full submission. The housekeeping shift flag in particular warrants follow-up before drawing strong conclusions from the baseline's low absolute scores.

## Provenance

Commit `2fe7bd7f4f0902b454d0f2face73f917e6e065d5`, seed 0, code hash `k001-mean-shift-v0`. Hero, share card, and briefing visuals are available in the run's visual directory.
