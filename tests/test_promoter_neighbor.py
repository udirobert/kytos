from __future__ import annotations

import gzip
import math
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pn = import_module("promoter_neighbor")


def _tss_table():
    return pd.DataFrame(
        [
            dict(gene="AAA", chromosome="chr1", strand="+", tss=1000),
            dict(gene="BBB", chromosome="chr1", strand="-", tss=2000),
            dict(gene="CCC", chromosome="chr1", strand="+", tss=20000),
            dict(gene="DDD", chromosome="chr2", strand="+", tss=1000),
            # duplicated symbol -- must be excluded from both roles
            dict(gene="DUP", chromosome="chr1", strand="+", tss=1500),
            dict(gene="DUP", chromosome="chr3", strand="+", tss=9000),
        ]
    )


def test_parse_gencode_tss_reads_gene_features(tmp_path: Path):
    gtf = tmp_path / "toy.gtf.gz"
    lines = [
        "# comment",
        'chr1\tsrc\tgene\t100\t200\t.\t+\t.\tgene_id "E1"; gene_name "AAA";',
        'chr1\tsrc\ttranscript\t100\t200\t.\t+\t.\tgene_id "E1"; gene_name "AAA";',
        'chr1\tsrc\tgene\t300\t400\t.\t-\t.\tgene_id "E2"; gene_name "BBB";',
        'chr1\tsrc\tgene\t500\t600\t.\t+\t.\tgene_id "E3";',
    ]
    with gzip.open(gtf, "wt") as handle:
        handle.write("\n".join(lines) + "\n")
    table = pn.parse_gencode_tss(gtf)
    assert list(table.gene) == ["AAA", "BBB"]  # transcript and nameless dropped
    # + strand TSS = start; - strand TSS = end
    assert table.set_index("gene").tss.to_dict() == {"AAA": 100, "BBB": 400}


def test_build_pairs_window_and_dedup():
    pairs = pn.build_pairs(
        _tss_table(), targets=["AAA", "DUP"], genes=["AAA", "BBB", "CCC", "DDD", "DUP"]
    )
    # AAA(1000) -> BBB(2000, dist 1000) in-window; CCC(20000) out; DDD wrong chr.
    assert set(pairs.target) == {"AAA"}
    row = pairs.iloc[0]
    assert (row.neighbor, row.distance, row.chromosome) == ("BBB", 1000, "chr1")
    # AAA is upstream of BBB but strands differ and AAA.tss < BBB.tss -> tandem,
    # not divergent.
    assert not row.divergent
    # DUP was dropped as a target (duplicated symbol).
    assert "DUP" not in set(pairs.target)


def test_build_pairs_divergent_flag():
    table = pd.DataFrame(
        [
            dict(gene="T", chromosome="chr1", strand="+", tss=5000),
            dict(gene="N", chromosome="chr1", strand="-", tss=4000),
        ]
    )
    pairs = pn.build_pairs(table, targets=["T"], genes=["T", "N"])
    assert pairs.iloc[0].divergent  # N upstream of + target, opposite strand


def test_remaining_fraction_ramp():
    assert pn.remaining_fraction(0) == pn.remaining_fraction(500) == 0.15
    assert pn.remaining_fraction(5000) == 1.0
    mid = pn.remaining_fraction(1632)  # log10(1632/500) ~ 0.51
    assert 0.15 < mid < 1.0


def test_promoter_delta_translation():
    genes = ["T", "N", "X"]
    gi = {g: i for i, g in enumerate(genes)}
    pairs = pd.DataFrame([dict(target="T", neighbor="N", distance=400)])
    control_mean = np.array([10.0, 8.0, 5.0])
    d = pn.promoter_delta(pairs, "T", gi, control_mean)
    r = pn.remaining_fraction(400)  # = 0.15 (below ramp floor)
    assert d[1] == math.log1p(r * 8.0) - math.log1p(8.0)
    assert d[0] == 0 and d[2] == 0
    # repression: negative for nonzero expression
    assert d[1] < 0
    # no pairs -> zero vector
    assert not pn.promoter_delta(pairs, "MISSING", gi, control_mean).any()


def test_apply_promoter_cap_only_tightens():
    borrowed = np.array([0.5, -0.9, 0.3])
    pn_delta = np.array([0.0, -0.4, 0.0])  # only gene 1 is a neighbor
    capped = pn.apply_promoter_cap(borrowed, pn_delta)
    # borrowed already more repressive at neighbor -> kept
    assert capped[1] == -0.9
    # non-neighbor positions untouched (pn=0 must not zero them out)
    assert capped[0] == 0.5 and capped[2] == 0.3
    borrowed2 = np.array([0.5, 0.7, 0.3])
    capped2 = pn.apply_promoter_cap(borrowed2, pn_delta)
    assert capped2[1] == -0.4  # positive borrowed value capped to prior ceiling
