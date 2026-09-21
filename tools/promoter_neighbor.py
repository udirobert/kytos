"""Promoter-neighbor prior (k024) -- pure helpers, no I/O side effects.

Ported from the public rank-82 MIT-licensed reference
(github.com/kaipengm2/Virtual-Cell-Challenge-2026, model.py::apply_promoter_prior
and prepare.py::pairs/prepare_promoters). The reference applies the prior in
probability space: for every (target, neighbor) pair whose TSS are within
+/-5000 bp on the same chromosome, the neighbor's expression probability is
capped at ``control_prob * remaining(distance)`` where

    remaining = fraction + (1 - fraction) * clip(log10(max(d, 500)/500), 0, 1)

i.e. 85% repression at <=500 bp decaying log-linearly to none at 5 kb. This
models CRISPRi local silencing spread.

The k022 diagnostic consumes *deltas* (mean log1p(raw) perturbed minus
control), so the prior is translated to delta space: if the neighbor's counts
are scaled by ``r = remaining`` the mean-log1p shift is ``log1p(r*M) -
log1p(M)`` with ``M`` the control raw-count mean for that gene (plug-in mean
approximation; exact in the high-expression limit where it tends to log(r)).
"""

from __future__ import annotations

import gzip
import math
import re

import numpy as np
import pandas as pd

WINDOW_BP = 5000
RAMP_FLOOR_BP = 500
FRACTION = 0.15

ATTR_RE = re.compile(r'(\w+) "([^"]*)"')


def parse_gencode_tss(gtf_path) -> pd.DataFrame:
    """Parse a gencode GTF(.gz) to a per-symbol TSS table.

    Keeps ``gene`` features only; TSS is gene start on +, gene end on -.
    Symbols duplicated across loci are kept here -- ``build_pairs`` drops
    them, matching the reference's ``~table.gene.duplicated(keep=False)``.
    """
    rows = []
    open_fn = gzip.open if str(gtf_path).endswith(".gz") else open
    with open_fn(gtf_path, "rt") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "gene":
                continue
            attrs = dict(ATTR_RE.findall(fields[8]))
            if "gene_name" not in attrs:
                continue
            rows.append(
                dict(
                    gene=attrs["gene_name"],
                    chromosome=fields[0],
                    strand=fields[6],
                    tss=int(fields[3] if fields[6] == "+" else fields[4]),
                )
            )
    return pd.DataFrame(rows, columns=["gene", "chromosome", "strand", "tss"])


def build_pairs(table: pd.DataFrame, targets, genes, window: int = WINDOW_BP) -> pd.DataFrame:
    """Find (target, neighbor) TSS pairs within ``window`` bp.

    ``targets``: symbols to explain; ``genes``: the consumer axis (neighbors
    are restricted to it). Symbols with duplicated gencode entries are
    excluded from both roles, matching the reference implementation.
    """
    unique = table[~table.gene.duplicated(keep=False)].set_index("gene")
    relevant = unique.loc[unique.index.intersection(genes)]
    rows = []
    for target in targets:
        if target not in unique.index:
            continue
        a = unique.loc[target]
        near = relevant[
            (relevant.chromosome == a.chromosome) & ((relevant.tss - a.tss).abs() <= window)
        ]
        for name, b in near.iterrows():
            if name == target:
                continue
            divergent = bool(
                a.strand != b.strand
                and ((a.strand == "+" and a.tss > b.tss) or (a.strand == "-" and a.tss < b.tss))
            )
            rows.append(
                dict(
                    target=target,
                    neighbor=name,
                    distance=abs(int(a.tss) - int(b.tss)),
                    chromosome=a.chromosome,
                    target_tss=int(a.tss),
                    neighbor_tss=int(b.tss),
                    target_strand=a.strand,
                    neighbor_strand=b.strand,
                    divergent=divergent,
                )
            )
    return pd.DataFrame(
        rows,
        columns=[
            "target",
            "neighbor",
            "distance",
            "chromosome",
            "target_tss",
            "neighbor_tss",
            "target_strand",
            "neighbor_strand",
            "divergent",
        ],
    )


def remaining_fraction(distance: float, fraction: float = FRACTION) -> float:
    """Residual expression fraction under the CRISPRi local-silencing cap."""
    scaled = math.log(max(float(distance), RAMP_FLOOR_BP) / RAMP_FLOOR_BP) / math.log(10)
    ramp = np.clip(scaled, 0, 1)
    return float(fraction + (1 - fraction) * ramp)


def promoter_delta(
    pairs: pd.DataFrame,
    target: str,
    gene_index: dict,
    control_mean_raw: np.ndarray,
    fraction: float = FRACTION,
) -> np.ndarray:
    """Delta-space prior for one target.

    Returns a vector on the consumer axis; nonzero only at neighbor
    positions, equal to ``log1p(r*M) - log1p(M)`` where ``r`` is the
    remaining fraction and ``M`` the gene's control raw-count mean.
    """
    delta = np.zeros(len(gene_index), dtype=np.float64)
    if pairs is None or pairs.empty:
        return delta
    sel = pairs[pairs.target == target]
    for row in sel.itertuples(index=False):
        j = gene_index.get(row.neighbor)
        if j is None or row.neighbor == target:
            continue
        r = remaining_fraction(row.distance, fraction)
        m = float(control_mean_raw[j])
        delta[j] = math.log1p(r * m) - math.log1p(m)
    return delta


def apply_promoter_cap(delta: np.ndarray, pn_delta: np.ndarray) -> np.ndarray:
    """Cap ``delta`` at the prior ceiling on neighbor positions.

    Faithful to the reference: the cap only bites where the assembled delta
    is less repressive than the prior ceiling; positions where the borrowed
    signal is already more repressive keep the borrowed value.
    """
    out = np.asarray(delta, dtype=np.float64).copy()
    mask = pn_delta != 0
    out[mask] = np.minimum(out[mask], pn_delta[mask])
    return out
