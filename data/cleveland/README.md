# Cleveland Clinic / GQAI 2026 — data manifest

Raw PDBs are downloaded to `raw/` (gitignored) via:

```bash
.venv-cleveland/bin/python tools/run_cleveland_c001.py --fetch-only
```

| Target | Apo | Holo | Chain | Domain mask | Active-site source (auth resseq) |
|---|---|---|---|---|---|
| KRAS G12C | 4OBE | 6OIM | A | full G domain | nucleotide pocket |
| BCR-ABL1 | 1OPL | 5MO4 | A | 229–515 | ATP site |
| Cardiac myosin | 5TBY | 6C1H (chain **P**) | A / P | 1–800 | ATP site |

Mavacamten known-site labels (post-hoc only): literature pocket contacts
`164, 167, 168, 666, 710, 711, 712, 721, 722` — see `src/cleveland/targets.py`.

| c-Myc/Max | 1NKP | — | A | full | DNA-basic region |

Canonical definitions live in `src/cleveland/targets.py`. Known allosteric
residue lists are **labels for later scoring only** — never model inputs.
