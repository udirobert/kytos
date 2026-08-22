<!-- kytos narrative · generated_by=llm · provider=venice · model=stealth-ox-alpha · 2026-08-22T18:53:20+00:00 UTC -->

# Run Digest: k002 — Mean-Shift Floor vs VCC 2025 Validation

**Headline:** First real cell-eval run on the VCC 2025 validation split (H1 hESC, 50 targets) confirms the zero-shift floor: a constant mean-shift prediction yields a DE significant-genes recall of exactly **0.0**, with no Pearson delta computed.

## What was run
A mean-shift baseline (code hash `k002-mean-shift-vcc2025-v0`, commit `86a5b5b0f23c294216ecc0bf2513ed7c10af2eac`, seed 0) evaluated against the H1 hESC validation set with 50 perturbation targets. Data status is real — no synthetic or placeholder inputs.

## Results
- **DE sig genes recall: 0.0.** As preregistered, a constant prediction has no differentially expressed genes to recall, so recall lands at zero.
- **Pearson delta: not computed** for this run.
- **Ceiling headroom:** the computed ceilings stand at 0.494 for DE sig genes recall and 0.667 for Pearson delta, quantifying how much room any real model has above this floor.
- **Audit flags: none.** The run passed all integrity checks cleanly.

## Interpretation
Both preregistered hypotheses held: the zero-shift floor behaves as expected, and the gap between floor and ceiling now defines the measurable space for future submissions. This run establishes the calibration anchor for the competition pipeline rather than a competitive result — subsequent model runs should be judged against the ceiling values reported here.

*Provenance: run created 2026-08-22; seed 0; commit `86a5b5b`.*
