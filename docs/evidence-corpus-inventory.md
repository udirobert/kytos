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

Phase-1 additions (`h202-20261120-01`, validated):

| dataset_id | context | targets | covered | se_kind | units |
|---|---|---|---|---|---|
| replogle22rpe1-raw | RPE1 | 2,393 | 2,393 | welch-per-gem_group (n=56) | norm-mean-diff |
| replogle22rpe1-bulk | RPE1 | 2,394 | 2,394 | welch-per-row (guide-level) | norm-mean-diff |
| replogle22k562-gwps-bulk | K562 | 9,867 | 9,867 | welch-per-row (guide-level) | norm-mean-diff |
| replogle22k562-ess-bulk | K562 | 2,058 | 2,058 | welch-per-row (guide-level) | norm-mean-diff |
| datlinger17-jurkat | Jurkat | 32 | 32 | welch-per-replicate | log1p-sc |
| shifrut18-tcell | CD8 T | 20 | 20 | welch-per-replicate | log1p-sc |
| dixit16-dc | dendritic | 44 | 44 | welch-pseudobatch8 (PSEUDOREP) | log1p-sc |
| nadig24-jurkat | Jurkat | ~2,270 | landed | welch-per-gem_group (n=55) | log1p-norm |
| nadig24-hepg2 | HepG2 | landed | landed | welch-per-gem_group | log1p-norm |

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

## Phase 1 — scPerturb (Zenodo) + Altos HF mirror (k203 wave, spawned 2026-11-20)

**scPerturb resolved:** the harmonized corpus lives openly on Zenodo
record `10044268` (`/records/10044268/files/<name>?download=1` — the
`/api/` content route 429s Modal's datacenter IPs). Raw CSR counts →
`log1p-sc` unit parity with k201. `target`/`perturbation`/`replicate`
columns confirmed (harvester takes separate `control_col`). Note:
Zenodo throttles bursts — keep spawn rate modest.

**Altos HF mirror resolved:** `altoslabs/primeflow-vcc-datasets`
(`/resolve/main/<name>_preprocessed.h5ad.gz`) mirrors the blocked
scPertEval arms *plus* new contexts. Peeked `nadig24_jurkat`: CSR
log1p-norm (max~6.1), `gem_group` n=55, `gene` with 'non-targeting'
controls — Replogle-family schema, pinned in catalog.

| dataset_id | source | context | status 2026-11-20 |
|---|---|---|---|
| datlinger17-jurkat | zenodo | Jurkat | **landed** — 32 targets |
| shifrut18-tcell | zenodo | CD8 T | **landed** — 20 targets |
| dixit16-dc | zenodo | dendritic | **landed** — 44 (PSEUDOREP) |
| replogle22k562-gwps-bulk | figshare 35774443 | K562 | **landed** — 9,867 targets |
| replogle22k562-ess-bulk | figshare | K562 | **landed** — 2,058 targets |
| nadig24-jurkat / nadig24-hepg2 | altos HF | Jurkat/HepG2 | **landed** (gem_group batches confirmed) |
| adamson16-k562-s1/s5/s10 | zenodo | K562 | respawned |
| datlinger21-k562, papalexi21-pbmc | zenodo | K562/PBMC | respawned |
| tian19-ipsc/neuron, tian21-crnispri/crispa | zenodo | iPSC/neuron | respawned after pert_col fallback fix (crispa arm = activation, audit-only) |
| schiebinger19-1, zhao21-brain | zenodo | reprogram/brain | respawned |
| norman19-k562, frangieh21-melanoma | zenodo | K562/melanoma | respawned |
| replogle22k562-ess (sc) | zenodo | K562 | respawned |

## Still pending (k203 backlog)

| source | context | scope | status |
|---|---|---|---|
| mcfaline23-gxe | U-87MG+A172+T98G | kinome CRISPRi x drug GxE — **U-87MG is a VCC-final context** | catalogued on HF; needs DMSO-arm filter spec |
| feng24-ipsc (10.3 GB) | iPSC lines | trans-regulation map | catalogued; peek cols first |
| jiang24-pathway (10 GB) | mixed | pathway screens | catalogued; peek cols first |
| X-Atlas/Orion remainder | multiple lines | same Lance schema | extend k201 xatlas stage |
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
