"""Layer A — Gene-level perturbation effect transfer.

Maps target knocked gene k -> gene-wise response field Delta in R^G,
conditioned only on the basal context features of the target cell line.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np

from kytos.features.basal import BasalContext


class BaseLayerA(ABC):
    """Abstract base class for Layer A gene transfer models."""

    @abstractmethod
    def predict_delta(self, target_gene: str, context: BasalContext) -> np.ndarray:
        """Predict gene-wise delta vector (shape G,) for a given target knockdown."""
        pass


@dataclass
class MeanShiftTransfer(BaseLayerA):
    """Baseline transfer model: applies global mean perturbation response prior."""

    global_prior_delta: np.ndarray | None = None  # shape (G,)

    def predict_delta(self, target_gene: str, context: BasalContext) -> np.ndarray:
        n_genes = len(context.genes)
        if self.global_prior_delta is not None and len(self.global_prior_delta) == n_genes:
            delta = self.global_prior_delta.copy()
        else:
            delta = np.zeros(n_genes, dtype=float)

        # Directly down-regulate the target gene if present in gene list
        if target_gene in context.genes:
            idx = context.genes.index(target_gene)
            delta[idx] = -2.5  # standard strong CRISPRi knockdown log2FC
        return delta


@dataclass
class ContextConditionedTransfer(BaseLayerA):
    """Context-aware gene transfer model conditioned on target basal state.

    Uses target gene basal expression rank and cross-context learned priors
    to modulate the downstream propagation of the perturbation.
    """

    knockdown_efficiency: float = 2.5  # expected target knockdown in log2FC
    attenuation_factor: float = 0.5

    def predict_delta(self, target_gene: str, context: BasalContext) -> np.ndarray:
        n_genes = len(context.genes)
        delta = np.zeros(n_genes, dtype=float)

        if target_gene not in context.genes:
            return delta

        t_idx = context.genes.index(target_gene)
        target_rank = float(context.expression_rank[t_idx])
        target_mean = float(context.mean_expression[t_idx])

        # If target gene is barely expressed in basal state, effect is attenuated
        effective_kd = self.knockdown_efficiency * min(1.0, max(0.1, target_rank))
        delta[t_idx] = -effective_kd

        # Diffuse secondary effects scaled by basal expression magnitude
        # High-expressed genes experience proportional secondary shifts
        secondary_weights = (context.mean_expression / (target_mean + 1e-3)) * 0.05
        delta += np.clip(secondary_weights * (-effective_kd * self.attenuation_factor), -1.5, 1.5)
        delta[t_idx] = -effective_kd  # maintain exact target knockdown
        return delta
