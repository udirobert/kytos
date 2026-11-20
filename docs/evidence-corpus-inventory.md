# Evidence corpus inventory (engine v2, k202)

> Status: **living document** — the catalog for the L0 evidence harvest.
> Each row is a candidate or harvested store under
> `/kytos-vol/k201-evidence/<dataset_id>/`. Spec order from
> `docs/engine-v2-design.md` §2. Harvest tool:
> `tools/modal_k202_harvest.py` (manifest-driven, one source per
> invocation); validator: `tools/modal_k201_validate.py`.

## Phase 0 — owned arms, re-extracted (k201, DONE 2026-11-20)

| dataset_id | context | targets | covered | se_kind | status |
|---|---|---|---|---|---|
| xatlas-hct116 | hct116 | 18,293 | 18,293 | welch-per-sample | `l0-20261120-01` |
| xatlas-hek293t | hek293t | 18,311 | 18,311 | welch-per-sample | `l0-20261120-01` |
| replogle-k562-gwps | k562 | 9,866 | 9,866 | welch-per-gemgroup | `l0-20261120-01` |
| cd4-marson2025 | cd4-tcell | 11,526 | 7,281 | publisher zscore (+derived se/p) | `l0-20261120-02` |
| vcc2025-h1 | h1-hesc | 150 | 150 | welch-per-batch | `l0-20261120-01` |

## Phase 1 — seeded harvest catalog

**Access note (2026-11-20):** the scPertEval bucket flipped to
**requester-pays** since the k039 audit — plain HTTPS now returns
`400 UserProjectMissing`. Those six sources stay catalogued but need a
GCP billing project to download. The figshare Replogle raw arms remain
open and are the first harvest targets.

Open figshare arms (verified 2026-11-20, ranged GET):

| dataset_id | size | context | assay | status |
|---|---|---|---|---|
| replogle22rpe1-raw | 8.7 GB | RPE1 | sc CRISPRi | **harvested `h202-20261120-01`** — 2,393 targets, welch-per-gem_group (56 groups); X is publisher-normalized despite filename |
| replogle22rpe1-bulk | 0.1 GB | RPE1 | bulk CRISPRi | **harvested `h202-20261120-01`** — 2,394 guide-level targets, welch-per-row |

scPertEval processed files (`X` = `log1p(normalize_total(1e4))`, no
raw counts; no obs batch column expected → pseudo-batch or pooled —
manifest flags `PSEUDOREP`/`none` and L1 downweights accordingly).
Base: `https://storage.googleapis.com/scperteval/processed/`
`<name>_processed_complete.h5ad`. **All six: requester-pays.**

| dataset_id | size | context | assay | k039 panel coverage | status |
|---|---|---|---|---|---|
| wessels23 | 0.2 GB | THP-1 | sc CRISPRi | small (essential) | blocked: requester-pays |
| replogle22rpe1 | 1.9 GB | RPE1 | sc CRISPRi | 0/300 (essential ~2,057) | blocked: requester-pays |
| nadig25jurkat | 2.0 GB | Jurkat | sc CRISPRi | 0/300 (essential) | blocked: requester-pays |
| nadig25hepg2 | 1.2 GB | HepG2 | sc CRISPRi | 0/300 (essential) | blocked: requester-pays |
| kaden25rpe1 | 5.6 GB | RPE1 | **sc CRISPRa** | 80/300 (activation — do NOT mix into KD) | blocked: requester-pays |
| arch1 | 4.4 GB | H1 hESC | sc CRISPRi | 13/300 | blocked: requester-pays |

Coverage figures are vs the 2026 panel (k039 audit); they are *not* the
harvest criterion — corpus breadth over targets is. Essential-gene
screens still contribute ~2k targets of evidence each.

## Phase 1 — pending URL/scope research (k203)

| source | context | scope | status |
|---|---|---|---|
| scPerturb 44 datasets | many | harmonized .h5ad portal (sanderlab) | per-dataset URLs + licenses needed |
| X-Atlas/Orion remainder | multiple lines | same Lance schema as hct116/hek293t | extend k201 xatlas stage |
| McFaline-Figueroa U-87MG kinome screen | u-87mg | context-relevant (final line; 21 test targets) | URL TBD |
| Parse-PBMC | pbmc | broad | URL TBD |
| IGVF perturb-seq | k562 + | broad | portal access TBD |
| Adamson 2016 | k562 | historic small | deprioritized vs newer |
| VIPerturb-seq | h1-hesc | broad | URL TBD |
| Jurkat VCC-2026 arm | jurkat | re-admit as source w/ own weight | uses existing extract |
| Tahoe-100M | many | 100M cells | **held-out reserve — harvest last** |

## Phase 2 — bulk screens (z-unit only)

ENCODE K562/HepG2 KDs, LINCS L1000 (ships LFC+p already), PerturbAtlas,
KnockTF, ARCHS4. Vote on *which* genes respond; no LFC magnitude
contribution (design doc §1: z is the cross-assay unit).

## Harvest invariants (from the design doc)

- `stats.npz` schema: genes/targets/covered/lfc/se/p/q/z/n_voting/kd_eff.
- `lfc_kind` + `se_kind` in every manifest — units never silently mixed
  (scPertEval `log1p-norm-mean` vs raw `log1p-sc` vs `log2fc-publisher`).
- Real sample units preferred (batch/gem/donor/sample); pseudo-batches
  flagged `PSEUDOREP`; pooled-only emits lfc with NaN stats.
- sha256 recorded per download; URLs plain-HTTPS only in the catalog.
- Each store gets a validator pass (`modal_k201_validate.py`) before the
  run is recorded in `experiments/`.
