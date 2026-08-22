"""Context feature extraction from unperturbed target basal cells.

Extracts per-gene statistics and covariance priors required by Layer A (gene-level
transfer) and Layer B (single-cell sampling) without using any post-perturbation data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np


@dataclass(frozen=True)
class BasalContext:
    """Statistical summary of unperturbed basal state across genes."""

    genes: list[str]
    mean_expression: np.ndarray  # shape (G,)
    var_expression: np.ndarray  # shape (G,)
    expression_rank: np.ndarray  # shape (G,), percentile rank 0.0 -> 1.0
    sparsity: np.ndarray  # shape (G,), fraction of non-zero cells
    n_cells: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_cells": self.n_cells,
            "n_genes": len(self.genes),
            "genes": self.genes,
            "mean_expression": self.mean_expression.tolist(),
            "var_expression": self.var_expression.tolist(),
            "expression_rank": self.expression_rank.tolist(),
            "sparsity": self.sparsity.tolist(),
        }


def extract_basal_context(
    X: np.ndarray,
    genes: list[str],
) -> BasalContext:
    """Extract context statistics from basal cell-by-gene expression matrix.

    Args:
        X: 2D numpy array of shape (N_cells, G_genes), log1p normalized or counts.
        genes: list of gene symbols matching columns of X.

    Returns:
        BasalContext dataclass.
    """
    if X.ndim != 2:
        raise ValueError(f"Expected 2D matrix, got shape {X.shape}")
    if X.shape[1] != len(genes):
        raise ValueError(f"Matrix columns ({X.shape[1]}) do not match gene list ({len(genes)})")

    n_cells = X.shape[0]
    if n_cells == 0:
        raise ValueError("Cannot extract context from empty cell matrix")

    mean_expr = np.asarray(X.mean(axis=0)).ravel()
    var_expr = np.asarray(X.var(axis=0)).ravel()
    nonzero_frac = np.asarray((X > 0).mean(axis=0)).ravel()

    # Percentile rank (0.0 to 1.0)
    order = np.argsort(mean_expr)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.linspace(0.0, 1.0, len(mean_expr))

    return BasalContext(
        genes=genes,
        mean_expression=mean_expr,
        var_expression=var_expr,
        expression_rank=ranks,
        sparsity=nonzero_frac,
        n_cells=n_cells,
    )
