# k039 — new lineage-matched sources (RPE1 ×2, Jurkat #2, THP-1, HepG2, hESC)

> Status: **audit complete (2026-10-12) — negative on new knockdown
> sources.** No processed public dataset adds usable panel-target KD
> deltas. Findings (numbers embargoed,
> `experiments/_embargoed/k039-lineage-audit/`):
>
> - `replogle22rpe1`, `nadig25jurkat`, `nadig25hepg2`, `wessels23` are
>   essential-or-small-library screens covering **0/300** panel targets
>   (same wall as the k013 audit).
> - `kaden25rpe1` covers **80/300** — but it is **CRISPRa** (TF activation,
>   Kaden 2025), not knockdown; activation deltas cannot enter a knockdown
>   consensus. Its ~zero cross-source agreement is consistent with
>   opposite-direction perturbation, not noise (deep cells/target).
> - `arch1` (H1 hESC) covers 13/300 — marginal.
> - Basal-match byproduct: context-lineage evidence *sharpened* — a true
>   Jurkat basal leads context A on discriminative genes, both independent
>   RPE1 basals lead context B, epithelial sources lead C, and the eval
>   context basal is effectively identical to H1 hESC.
> - Tool written: `tools/extract_scperteval_source.py` (h5ad →
>   panel-axis `deltas_<src>.npz` + manifest, VPS-runnable);
>   `tools/audit_k039_sources.py` (coverage/basal/agreement audit).
>
> Original motivation (k038 close-out): the two slot-eligible mechanisms
> were *more samples per source* (k036 — hct116 complete on the volume,
> hek293t resumed and merging shards 2026-10-12) and *a lineage-matched
> second source* (this audit — closed, negative).

## Why now

The k013 audit recorded "figshare GWPS is K562-only" — true for the
genome-wide arm, but the **essential-gene RPE1 screen exists processed**, and
a second independent RPE1 Perturb-seq (Kaden 2025) exists too. The k030
ctxlineage build (`experiments/k030-ctxlineage/`) covers sources
`k562, hct116, hek293t, cd4` + `jurkat` + `hipsci` — **no RPE1 source has
ever entered the consensus**, and a context was previously flagged
RPE1-like by marker analysis (k012 lineage note). If that match is real,
RPE1 is the only missing lineage in the current source set.

## Data (all verified live 2026-10-12, plain HTTPS, no key)

| dataset | size | lineage | scope |
|---|---|---|---|
| `replogle22rpe1` | 1.9 GB | RPE1 | ~2,057 essential-gene CRISPRi |
| `kaden25rpe1` | 5.6 GB | RPE1 | second screen (Kaden 2025) |
| `nadig25jurkat` | 2.0 GB | Jurkat | second Jurkat source |
| `wessels23` | 196 MB | THP-1 | myeloid |
| `nadig25hepg2` | 1.2 GB | HepG2 | liver |
| `arch1` | 4.4 GB | H1 hESC | hESC (low priority — k012 says contexts not hESC) |

Base URL: `https://storage.googleapis.com/scperteval/processed/<name>_processed_complete.h5ad`

Fallback for exact-unit raw data: figshare `35775606`
(`rpe1_raw_singlecell_01.h5ad`, referenced by the GEARS preprocessing
notebook) and `gwps.wi.mit.edu` `Rpe1_normalized_bulk_01.h5ad`.

**Units caveat.** scPertEval files are `normalize_total`+`log1p` processed,
not raw counts — a per-target delta computed on them is a
log-normalized-mean shift, not the `mean(log1p(raw))` shift used elsewhere.
Record `units` in the manifest (same pattern as the CD4 log2-FC caveat) and
prefer the figshare raw arm for the primary extract if unit parity matters;
the processed files are still fine for the cheap coverage/basal audit.

## Plan

1. **Fetch** to `snapflip-vultr` (all ≤5.6 GB; VPS has disk/RAM headroom —
   no Modal needed). Stage under `/opt/kytos/repo/data/raw/` (gitignored).
2. **Extract** pooled per-target deltas on the 18,533-gene panel axis with
   the existing `tools/consensus_deltas.py` machinery (same
   `deltas_<source>.npz` contract as k023: `genes/targets/delta/covered/
   n_cells` + manifest). Essential-gene h5ads are small — dense group
   accumulation is safe. New tool: `tools/extract_scperteval_source.py`
   (h5ad → panel-axis npz), runnable on the VPS.
3. **Coverage + basal-match audit** (decisive, cheap, do first):
   - panel ∩ source targets per dataset (expect modest for essential-gene
     screens; kaden25rpe1 scope TBD — may be wider);
   - extend the ctxlineage basal-similarity report with the new sources —
     if any context matches RPE1/THP-1/HepG2 better than the current five
     sources, that is evidence of a real lineage gap being filled;
   - cross-source agreement on shared targets vs the existing sources
     (sanity: deltas should correlate with same-lineage sources).
4. **Decision gate for a slot** (per the measurement-probe protocol):
   proceed to a consensus variant only if the source covers a useful
   fraction of the 300-panel AND basal-matches a context. Build via
   `tools/build_consensus_deltas_v2.py` as an added source (per-context
   source weighting is NOT revived — k013/k030 teach that global
   composition changes need a probe, not a constant). Pre-declare
   component predictions in an embargoed note before any submit.
5. **k036** (independent track): launch
   `tools/modal_k036_xatlas_samplestats.py` `--detach` for `hct116` and
   `hek293t` — resumable, ~120/200 GB shard intermediates on the volume.
   Per-sample sign agreement (78–116 samples/target median) is the
   stronger form of the "confidently-signed genes" mechanism.

## Embargo

Coverage tables, basal-match numbers, cross-source cosines and any gate
results → `experiments/_embargoed/` (local-only). Public artifacts may say
"an RPE1 source was added/dropped" but not the diagnostic values.

## Risks / honest expectations

- Essential-gene screens cover a minority of the panel; expected gain is
  bounded to the RPE1-matched context channel. `kaden25rpe1` scope is the
  swing factor.
- k030 taught that adding a source can regress overall even when it is the
  only real signal for a context (Jurkat mean → −0.017 vs champion). The
  probe protocol stands: measure, don't assume.
- None of this closes the leaderboard-scale gap to top-10 by itself; it is
  the highest-EV move the current method class still has open, and it
  directly buys robustness for the Oct-22 unseen cell lines.
