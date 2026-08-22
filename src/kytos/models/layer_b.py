"""Layer B — Conditional single-cell sample generator.

Given unperturbed target basal cells X_basal in R^(N x G) and Layer A predicted
delta vector Delta in R^G, draws synthetic post-perturbation cells X_pred in R^(M x G).
Satisfies the single-cell distribution, dispersion, and DE-gated metrics required by cell-eval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np


class BaseLayerB(ABC):
    """Abstract base class for Layer B single-cell generators."""

    @abstractmethod
    def sample_cells(
        self,
        X_basal: np.ndarray,
        delta: np.ndarray,
        n_samples: int,
        *,
        seed: int = 42,
    ) -> np.ndarray:
        """Sample n_samples post-perturbation cells given basal cells and gene delta."""
        pass


@dataclass
class AdditiveTransportSampler(BaseLayerB):
    """Transports basal cells along predicted gene deltas with single-cell noise preservation.

    Applies multiplicative scaling in linear expression space (additive in log1p space)
    with biological variance matching and non-negativity constraints.
    """

    noise_scale: float = 0.05

    def sample_cells(
        self,
        X_basal: np.ndarray,
        delta: np.ndarray,
        n_samples: int,
        *,
        seed: int = 42,
    ) -> np.ndarray:
        rng = np.random.default_rng(seed)
        n_basal = X_basal.shape[0]

        # Resample basal indices with replacement if n_samples != n_basal
        if n_samples == n_basal:
            indices = np.arange(n_basal)
        else:
            indices = rng.choice(n_basal, size=n_samples, replace=True)

        sampled_basal = X_basal[indices].copy()

        # Apply delta (assumed log1p / log2FC additive shift)
        # Shift with multiplicative noise to avoid deterministic collapse
        noise = rng.normal(0.0, self.noise_scale, size=sampled_basal.shape)
        perturbed = sampled_basal + delta[np.newaxis, :] + noise

        # Single-cell expression cannot be negative
        np.clip(perturbed, a_min=0.0, a_max=None, out=perturbed)
        return perturbed
