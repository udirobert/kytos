<!-- kytos narrative · generated_by=llm · provider=openai · model=gpt-4o-mini · 2026-08-22T13:14:14+00:00 UTC -->

## Basal Mean-Shift Baseline — Ceiling Headroom Probe

The run achieved a DESigGenesRecall of 0.12, indicating a significant gap from the ceiling headroom of 0.45 (facts: headline_metrics.DESigGenesRecall, ceiling_headroom.DESigGenesRecall). The pearson_delta was recorded at 0.08, which is also below the ceiling of 0.31 (facts: headline_metrics.pearson_delta, ceiling_headroom.pearson_delta).

### Audit Flags
Two warnings were raised during the analysis:
1. **Housekeeping Gene Shift**: The housekeeping genes ACTB and GAPDH exhibited a shift of up to +2.10 log2FC, surpassing the threshold of ±1.0, with ACTB showing the peak shift (facts: audit_flags[0].message).
2. **Pathway Coherence**: The 'interferon_response' pathway displayed mixed directionality, with two genes upregulated and two downregulated among those measured (facts: audit_flags[1].message).

### Hypotheses
The run was guided by two preregistered hypotheses: 
- Basal co-expression alone explains less than 20% of cross-context transfer on DESigGenesRecall.
- The mean-shift baseline is expected to remain below 50% of the ceiling on pearson_delta (facts: hypotheses_preregistered).

This analysis highlights the challenges in achieving high recall and coherence in gene expression studies, suggesting further investigation is needed to refine the model. 

![Hero Image](visual/hero.png)  
![Share Card](visual/share-card.png)
