"""Build promoter-neighbor pairs from a UCSC gencode V47 table dump (k024).

The reference implementation (kaipengm2 prepare.py) parses the gene features
of ``gencode.v47.annotation.gtf.gz`` from ftp.ebi.ac.uk. EBI is currently
unreachable (TCP refused from both the dev network and Modal), so this
builder uses UCSC's ``wgEncodeGencodeCompV47`` table dump instead:

    https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/
        wgEncodeGencodeCompV47.txt.gz

That table is the same gencode V47 comprehensive annotation rendered as
transcript-level genePred rows. Gene-level TSS are derived by grouping on
the gene symbol (``name2``), chromosome, and strand: min(txStart) for
+ strand, max(txEnd) for - strand -- the same locus extent the GTF gene
feature reports. Symbols duplicated across loci are dropped downstream in
``build_pairs``, matching the reference's dedup rule.

Usage:
    python tools/build_promoter_pairs.py \
        --ucsc-dump /path/to/wgEncodeGencodeCompV47.txt.gz \
        --paired-npz /path/to/paired_transfer_train.npz \
        --out-dir experiments/k024-promoter-prior/pairs-YYYYMMDD-NN
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import promoter_neighbor as pn

UCSC_DUMP_URL = (
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/wgEncodeGencodeCompV47.txt.gz"
)
UCSC_SCHEMA_URL = (
    "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/wgEncodeGencodeCompV47.sql"
)
GENCODE_GTF_URL = (  # reference input, unreachable at build time -- recorded
    "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/"
    "gencode.v47.annotation.gtf.gz"
)

REPO = Path(__file__).resolve().parents[1]
PANEL_COUNTS = REPO / "data/raw/vcc2026/pert_counts.csv"
PANEL_GENES = REPO / "data/raw/vcc2026/gene_names.csv"


def tss_from_ucsc_dump(dump_path) -> tuple[pd.DataFrame, int]:
    """Aggregate transcript-level genePred rows to per-locus TSS."""
    agg: dict[tuple[str, str, str], list] = {}
    n_tx = 0
    with gzip.open(dump_path, "rt") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            n_tx += 1
            symbol, chrom, strand = fields[12], fields[2], fields[3]
            tx_start, tx_end = int(fields[4]), int(fields[5])
            key = (symbol, chrom, strand)
            if key not in agg:
                agg[key] = [
                    symbol,
                    chrom,
                    strand,
                    tx_start if strand == "+" else tx_end,
                ]
            elif strand == "+":
                agg[key][3] = min(agg[key][3], tx_start)
            else:
                agg[key][3] = max(agg[key][3], tx_end)
    tss = pd.DataFrame(agg.values(), columns=["gene", "chromosome", "strand", "tss"])
    return tss, n_tx


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ucsc-dump", type=Path, required=True)
    parser.add_argument("--paired-npz", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    out = args.out_dir
    pairs_path = out / "promoter_pairs.csv"
    if pairs_path.exists():
        raise FileExistsError(f"{pairs_path} already exists -- use a new out dir")
    out.mkdir(parents=True)

    panel_targets = pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).tolist()
    with np.load(args.paired_npz, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    targets = sorted(set(panel_targets) | set(eval_targets))
    genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    tss, n_tx = tss_from_ucsc_dump(args.ucsc_dump)
    pairs = pn.build_pairs(tss, targets, genes)
    pairs.to_csv(pairs_path, index=False)
    tss.to_csv(out / "gencode_tss.csv", index=False)

    manifest = {
        "run_id": out.name,
        "coordinate_source": {
            "ucsc_table_dump": UCSC_DUMP_URL,
            "ucsc_schema": UCSC_SCHEMA_URL,
            "ucsc_dump_sha256": sha256_file(args.ucsc_dump),
            "reference_gencode_gtf": GENCODE_GTF_URL,
            "note": (
                "EBI ftp.ebi.ac.uk was TCP-refused from both the dev network "
                "and Modal at build time; TSS were derived from UCSC's "
                "wgEncodeGencodeCompV47 transcript table (same gencode V47 "
                "comprehensive annotation) by min(txStart)/max(txEnd) per "
                "symbol-chromosome-strand locus."
            ),
        },
        "n_transcript_rows": n_tx,
        "n_gene_loci": int(len(tss)),
        "n_unique_symbols": int((~tss.gene.duplicated(keep=False)).sum()),
        "window_bp": pn.WINDOW_BP,
        "ramp_floor_bp": pn.RAMP_FLOOR_BP,
        "fraction": pn.FRACTION,
        "targets_requested": len(targets),
        "eval_targets": eval_targets,
        "n_pairs": int(len(pairs)),
        "n_targets_with_pairs": int(pairs.target.nunique()),
        "eval_targets_with_pairs": sorted(set(pairs.target.unique()) & set(eval_targets)),
        "outputs": {
            "pairs": str(pairs_path),
            "tss": str(out / "gencode_tss.csv"),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
