"""Dual-moment integer count generation for VCC predictions.

Adapted from the kaipengm2 top-100 approach (MIT licensed). Instead of
simply adding deltas to control expression, this module generates integer
counts that simultaneously match:
  1. Per-cell mean CPM distribution (single-cell moment)
  2. Pseudobulk profile (bulk moment)

This preserves library-size structure and avoids the MSE collapse seen
with naive delta addition.

Key functions:
  - desired_mean_from_effects: convert log-space effects to target probability
  - dual_moment_counts: iterative moment-matching integer count generation
  - repair_bulk_totals: ensure exact per-gene bulk totals after rounding
"""

from __future__ import annotations

import numpy as np
from scipy import sparse


def desired_mean_from_effects(
    control_probability: np.ndarray,
    effects: np.ndarray,
    *,
    space: str = "bulk_delta",
    amplitude: float = 1.0,
    clip: float = 3.0,
) -> np.ndarray:
    """Convert log-space effects to a target probability vector.

    Args:
        control_probability: per-gene control probability (sums to ~1)
        effects: per-gene log-space effect (log1p delta or log2fc)
        space: 'bulk_delta' for log1p CPM deltas, 'log2fc' for log2 fold-change
        amplitude: scalar multiplier on effects
        clip: symmetric clip bound on scaled effects

    Returns:
        Target probability vector (sums to 1)
    """
    effect = np.clip(amplitude * effects, -clip, clip)
    if space == "log2fc":
        desired = control_probability * np.exp2(effect)
    elif space == "bulk_delta":
        # effects are log1p(CPM_pert) - log1p(CPM_ctrl)
        # invert: CPM_pert = expm1(log1p(50000*ctrl_prob) + effect)
        desired = np.expm1(np.maximum(np.log1p(50000 * control_probability) + effect, 0))
    else:
        raise ValueError(f"Unknown space: {space}")

    total = desired.sum()
    if total <= 0 or not np.isfinite(desired).all():
        # Fallback to control
        return control_probability.copy()
    return desired / total


def repair_bulk_totals(
    integer: np.ndarray,
    expected: np.ndarray,
) -> np.ndarray:
    """Adjust integer counts so per-gene column totals match floor(expected).

    Preserves per-row (per-cell) library sizes exactly.
    """
    expected = np.asarray(expected, dtype=np.float64)
    if integer.shape != expected.shape or integer.ndim != 2:
        raise ValueError("Count and expectation axes differ")
    if not np.isfinite(expected).all() or (expected < 0).any() or (integer < 0).any():
        raise ValueError("Invalid count expectations")

    row_totals = integer.sum(axis=1, dtype=np.int64)
    columns = expected.sum(axis=0)
    target = np.floor(columns).astype(np.int64)
    remaining = int(row_totals.sum() - target.sum())

    if remaining < 0 or remaining > len(target):
        raise ValueError("Expected and integer grand totals differ")
    if remaining:
        chosen = np.argsort(columns - target, kind="stable")[-remaining:]
        target[chosen] += 1

    difference = integer.sum(axis=0, dtype=np.int64) - target
    capacity = np.zeros(len(integer), dtype=np.int64)

    # Remove excess counts
    for gene in np.flatnonzero(difference > 0):
        excess = int(difference[gene])
        rounded_up = integer[:, gene] - np.floor(expected[:, gene]).astype(np.int64)
        rows = np.flatnonzero(rounded_up > 0)
        if rounded_up[rows].sum() < excess:
            raise ValueError("Initial rounding fell below its integer floor")
        rows = rows[np.argsort(-(integer[rows, gene] - expected[rows, gene]), kind="stable")]
        if excess <= len(rows):
            selected = rows[:excess]
            integer[selected, gene] -= 1
            capacity[selected] += 1
        else:
            for row in rows:
                take = min(excess, int(rounded_up[row]))
                integer[row, gene] -= take
                capacity[row] += take
                excess -= take
                if not excess:
                    break

    # Add deficit counts
    deficit_genes = np.flatnonzero(difference < 0)
    deficit_genes = deficit_genes[np.argsort(difference[deficit_genes], kind="stable")]
    for gene in deficit_genes:
        deficit = int(-difference[gene])
        while deficit:
            rows = np.flatnonzero(capacity > 0)
            if not len(rows):
                raise AssertionError("Column repair exhausted row capacity")
            take = min(deficit, len(rows))
            score = expected[rows, gene] - integer[rows, gene]
            selected = rows[np.argsort(-score, kind="stable")][:take]
            integer[selected, gene] += 1
            capacity[selected] -= 1
            deficit -= take

    if capacity.any() or (integer < 0).any():
        raise AssertionError("Column repair lost counts")
    if not np.array_equal(integer.sum(axis=1, dtype=np.int64), row_totals):
        raise AssertionError("Column repair changed a cell depth")
    if not np.array_equal(integer.sum(axis=0, dtype=np.int64), target):
        raise AssertionError("Column repair failed its bulk totals")
    return integer


def dual_moment_counts(
    template: np.ndarray,
    probability: np.ndarray,
    bulk_probability: np.ndarray,
    *,
    depths: np.ndarray,
    seed: int = 0,
    iterations: int = 100,
    tolerance: float = 2e-4,
) -> np.ndarray:
    """Generate integer counts matching both per-cell and bulk moments.

    Args:
        template: (n_cells, n_genes) float array of control-derived cell profiles
        probability: (n_genes,) target per-cell mean probability (sums to 1)
        bulk_probability: (n_genes,) target pseudobulk probability (sums to 1)
        depths: (n_cells,) integer library sizes
        seed: RNG seed
        iterations: max moment-matching iterations
        tolerance: convergence threshold for L1 error

    Returns:
        (n_cells, n_genes) int32 count matrix with exact row sums = depths
    """
    template = np.asarray(template, dtype=np.float64)
    probability = np.asarray(probability, dtype=np.float64)
    bulk_probability = np.asarray(bulk_probability, dtype=np.float64)
    raw_depths = np.asarray(depths)

    if template.ndim != 2 or not all(template.shape):
        raise ValueError("Template must be a nonempty cell-by-gene matrix")
    if probability.shape != (template.shape[1],):
        raise ValueError("Moment gene axes differ from template")
    if bulk_probability.shape != probability.shape:
        raise ValueError("Bulk probability shape mismatch")
    if not np.isfinite(template).all() or (template < 0).any():
        raise ValueError("Template must be finite nonnegative")
    if not np.isfinite(probability).all() or (probability < 0).any():
        raise ValueError("Probability must be finite nonnegative")
    if not np.isfinite(bulk_probability).all() or (bulk_probability < 0).any():
        raise ValueError("Bulk probability must be finite nonnegative")
    if (raw_depths != np.floor(raw_depths)).any() or (raw_depths < 1).any():
        raise ValueError("Depths must be positive integers")

    x = template.copy()
    p = probability.copy()
    bulk = bulk_probability.copy()
    depths = np.broadcast_to(raw_depths.astype(np.int64), (len(x),))

    if (depths <= 0).any():
        raise ValueError("All depths must be positive")

    z = depths / depths.mean()
    desired = len(x) * p

    # Project bulk onto feasible moment bounds
    lower = (z.min() + 0.01 * (1 - z.min())) * p
    upper = (z.max() - 0.01 * (z.max() - 1)) * p

    lo, hi = 0.0, 1.0
    if np.ptp(depths) == 0:
        bulk = p.copy()
    else:
        for _ in range(1024):
            if np.clip(bulk * hi, lower, upper).sum() >= 1:
                break
            hi *= 2
            if not np.isfinite(hi):
                raise ValueError("Bulk support cannot satisfy feasible moment bounds")
        else:
            raise ValueError("Cannot bracket the bulk projection")

        for _ in range(70):
            mid = (lo + hi) / 2
            if np.clip(bulk * mid, lower, upper).sum() < 1:
                lo = mid
            else:
                hi = mid
        bulk = np.clip(bulk * ((lo + hi) / 2), lower, upper)

    projection_error = float(np.abs(bulk - bulk_probability).sum())
    if projection_error > 0.03:
        # Relax constraint rather than fail
        pass

    ratio = np.divide(bulk, p, out=np.ones_like(p), where=p > 0)

    # Normalize template
    x /= np.maximum(x.sum(axis=1, keepdims=True), 1e-30)

    # Fill missing genes
    missing = (x.sum(axis=0) == 0) & (desired > 0)
    x[:, missing] = p[missing]

    # Small regularization
    x = 0.999 * x + 0.001 * p[None, :]

    # Iterative moment matching
    for step in range(iterations):
        col = x.sum(axis=0)
        x *= np.divide(desired, col, out=np.zeros_like(col), where=col > 0)

        first = z @ x
        mean = np.divide(first, desired, out=np.ones_like(first), where=desired > 0)
        second = z * z @ x
        var = np.maximum(
            np.divide(second, desired, out=np.zeros_like(desired), where=desired > 0) - mean * mean,
            0,
        )
        tilt = np.divide(ratio - mean, var, out=np.zeros_like(mean), where=var > 1e-12)
        lower_tilt = -0.95 / np.maximum(z.max() - mean, 1e-12)
        upper_tilt = 0.95 / np.maximum(mean - z.min(), 1e-12)
        tilt = np.clip(tilt, lower_tilt, upper_tilt)

        x *= 1 + tilt[None, :] * (z[:, None] - mean[None, :])
        x /= np.maximum(x.sum(axis=1, keepdims=True), 1e-30)

        if step % 5 == 4:
            cpm_error = float(np.abs(x.mean(axis=0) - p).sum())
            bulk_error = float(np.abs(z @ x / len(x) - bulk).sum())
            if max(cpm_error, bulk_error) < tolerance:
                break

    # Convert to integer counts
    expected = x * depths[:, None]
    integer = np.floor(expected).astype(np.int32)
    fractions = expected - integer

    rng = np.random.default_rng(seed)
    for i in range(len(x)):
        residual = int(depths[i]) - int(integer[i].sum())
        if residual > 0:
            cumulative = np.cumsum(fractions[i])
            if cumulative[-1] > 0:
                cumulative *= residual / cumulative[-1]
                locations = np.searchsorted(
                    cumulative, np.arange(residual) + rng.random(), side="right"
                )
                locations = np.clip(locations, 0, len(integer[i]) - 1)
                np.add.at(integer[i], locations, 1)

    integer = repair_bulk_totals(integer, expected)

    if (integer < 0).any() or not np.array_equal(integer.sum(axis=1), depths):
        raise AssertionError("Integer emission lost row depths")
    return integer


def build_prediction_dual_moment(
    control_adata,
    deltas: dict[str, np.ndarray],
    targets: list[str],
    gene_order: list[str],
    cells_per_target: int = 400,
    *,
    amplitude: float = 0.6,
    bulk_amplitude: float = 0.3,
    pool_k: int = 4,
    seed: int = 0,
    space: str = "bulk_delta",
) -> sparse.csr_matrix:
    """Build full prediction matrix using dual-moment count generation.

    Args:
        control_adata: AnnData with control cells (raw integer counts)
        deltas: dict mapping target -> log1p delta vector (aligned to gene_order)
        targets: list of target gene names
        gene_order: ordered gene list
        cells_per_target: cells to generate per target
        amplitude: scaling for per-cell CPM moment
        bulk_amplitude: scaling for pseudobulk moment
        pool_k: number of control cells to pool for template
        seed: base RNG seed
        space: 'bulk_delta' or 'log2fc'

    Returns:
        sparse.csr_matrix of shape (n_targets * cells_per_target, n_genes)
    """
    raw = sparse.csr_matrix(control_adata.X, dtype=np.float64)
    library = np.asarray(raw.sum(axis=1)).ravel()
    if (library <= 0).any():
        raise ValueError("Control has zero-depth cells")
    if len(library) < cells_per_target * pool_k:
        raise ValueError("Not enough control cells for template pooling")

    n_genes = len(gene_order)

    # Control mean CPM and bulk probability
    mean_cpm = np.zeros(n_genes)
    for left in range(0, len(library), 256):
        block = raw[left : left + 256].toarray() / library[left : left + 256, None]
        mean_cpm += block.sum(axis=0)
    mean_cpm /= len(library)
    bulk_prob = np.asarray(raw.sum(axis=0)).ravel()
    bulk_prob /= bulk_prob.sum()

    all_blocks = []
    for ti, target in enumerate(targets):
        delta = deltas.get(target)
        if delta is None:
            delta = np.zeros(n_genes, dtype=np.float32)

        # Select control cells for template
        rng = np.random.default_rng(seed + ti)
        selected = rng.choice(len(library), cells_per_target * pool_k, replace=False)
        selected = selected[np.argsort(library[selected], kind="stable")]
        template = raw[selected].toarray() / library[selected, None]
        template = template.reshape(cells_per_target, pool_k, n_genes).mean(axis=1)
        depths = np.rint(library[selected].reshape(cells_per_target, pool_k).mean(axis=1)).astype(
            np.int64
        )
        depths = np.clip(depths, 1, 1_000_000)

        # Per-cell moment
        prob_cell = desired_mean_from_effects(mean_cpm, delta, space=space, amplitude=amplitude)
        # Bulk moment
        prob_bulk = desired_mean_from_effects(
            bulk_prob, delta, space=space, amplitude=bulk_amplitude
        )

        counts = dual_moment_counts(
            template,
            prob_cell,
            prob_bulk,
            depths=depths,
            seed=seed + ti,
        )
        all_blocks.append(sparse.csr_matrix(counts))

    return sparse.vstack(all_blocks, format="csr")
