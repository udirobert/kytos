"""Pure helpers for multi-lineage consensus perturbation deltas (k023).

Delta convention matches ``tools/perturbation_priors.py`` and the k022
audit: a source delta is ``mean(log1p(raw))`` over perturbed cells minus
``mean(log1p(raw))`` over control cells, on the 2026 panel gene axis.

Everything here operates on plain arrays/dicts so it is testable without
Modal, SLAF, or h5ad inputs. Provenance and units are explicit: X-Atlas
deltas are computed from raw counts; CD4 deltas are publisher log2FC
values (different units -- consumers must normalize before mixing).
"""

from __future__ import annotations

import numpy as np


def map_gene_axis(source_gene_ids, panel_genes):
    """Map a source's gene axis onto the panel axis.

    Returns (positions, missing) where ``positions[i]`` is the source-row
    index whose symbol equals ``panel_genes[i]`` (or -1 when absent) and
    ``missing`` is the sorted list of uncovered panel symbols. Identity is
    by exact symbol only -- no suffix stripping or fuzzy matching.
    """
    position = {}
    for i, symbol in enumerate(source_gene_ids):
        position.setdefault(str(symbol), i)
    positions = np.array([position.get(g, -1) for g in panel_genes], dtype=np.int64)
    missing = sorted(g for g, p in zip(panel_genes, positions) if p < 0)
    return positions, missing


def deltas_from_group_sums(group_sums, group_cells, group_keys, control_label):
    """Compute pooled and batch-paired deltas from per-(sample,label) sums.

    ``group_sums``: (n_groups, n_genes) array of summed log1p counts over
    the cells in each (sample, label) group.
    ``group_cells``: (n_groups,) cell counts per group.
    ``group_keys``: list of (sample, label) tuples; ``control_label`` marks
    control groups.

    Pooled delta[target] = sum over perturbed groups / total perturbed
    cells minus pooled control mean. Batch-paired delta[target] =
    cell-weighted mean over samples of (group mean - that sample's
    control mean); targets absent from a sample contribute nothing.
    Returns dict target -> {"pooled", "batch", "n_cells", "n_samples"}.
    """
    group_sums = np.asarray(group_sums, dtype=np.float64)
    group_cells = np.asarray(group_cells, dtype=np.int64)
    if group_sums.shape[0] != len(group_keys) or len(group_keys) != len(group_cells):
        raise ValueError("Group arrays must share the same row count")
    if (group_cells <= 0).any():
        raise ValueError("Every group must contain at least one cell")

    ctrl_by_sample = {}
    ctrl_sums, ctrl_cells = [], []
    targets = {}
    for i, (sample, label) in enumerate(group_keys):
        if label == control_label:
            ctrl_by_sample[sample] = group_sums[i] / group_cells[i]
            ctrl_sums.append(group_sums[i])
            ctrl_cells.append(group_cells[i])
        else:
            targets.setdefault(label, []).append(i)
    if not ctrl_sums:
        raise ValueError("No control groups present")
    pooled_ctrl = np.sum(ctrl_sums, axis=0) / np.sum(ctrl_cells)

    out = {}
    for target, idx in targets.items():
        sums = group_sums[idx]
        cells = group_cells[idx]
        pooled = sums.sum(axis=0) / cells.sum() - pooled_ctrl
        paired_terms, weights = [], []
        for k, i in enumerate(idx):
            sample = group_keys[i][0]
            if sample in ctrl_by_sample:
                paired_terms.append(sums[k] / cells[k] - ctrl_by_sample[sample])
                weights.append(cells[k])
        batch = (
            np.average(np.stack(paired_terms), axis=0, weights=weights)
            if paired_terms
            else np.zeros(group_sums.shape[1])
        )
        samples = sorted({group_keys[i][0] for i in idx})
        out[target] = {
            "pooled": pooled.astype(np.float32),
            "batch": batch.astype(np.float32),
            "n_cells": int(cells.sum()),
            "n_samples": len(samples),
            "n_samples_with_controls": len(paired_terms),
        }
    return out


def unit_normalize(delta):
    """Scale a delta vector to unit L2 norm (zero vector passes through)."""
    norm = float(np.linalg.norm(delta))
    return delta / norm if norm > 0 else delta.astype(np.float64)


def consensus_delta(source_deltas, weights=None):
    """Weighted mean of unit-normalized source deltas over available sources.

    ``source_deltas``: dict name -> delta vector or None (None = source
    lacks this target). ``weights``: dict name -> nonnegative weight,
    default uniform. Returns (consensus, n_sources) where consensus is the
    weighted mean of unit-normalized deltas (not re-normalized), or None
    when no source covers the target.
    """
    present = {k: v for k, v in source_deltas.items() if v is not None}
    if not present:
        return None, 0
    weights = weights or {}
    num, den = np.zeros_like(next(iter(present.values())), dtype=np.float64), 0.0
    for name, delta in present.items():
        w = float(weights.get(name, 1.0))
        if w < 0:
            raise ValueError("Consensus weights must be nonnegative")
        num += w * unit_normalize(np.asarray(delta, dtype=np.float64))
        den += w
    return num / den if den > 0 else None, len(present)


def center_common_response(delta_matrix):
    """Subtract the per-gene median across targets (common-response component)."""
    matrix = np.asarray(delta_matrix, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 3:
        raise ValueError("Centering needs a (targets, genes) matrix with >=3 targets")
    return matrix - np.median(matrix, axis=0)


def rescale_to(delta, target_norm):
    """Rescale a consensus direction to a requested L2 norm."""
    norm = float(np.linalg.norm(delta))
    if norm <= 0 or target_norm <= 0:
        return np.zeros_like(delta)
    return delta * (target_norm / norm)
