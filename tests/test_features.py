import numpy as np
import pytest
from kytos.features.basal import BasalContext, extract_basal_context


def test_extract_basal_context_basic():
    genes = ["ACTB", "GAPDH", "MYC", "TP53"]
    # 10 cells x 4 genes
    rng = np.random.default_rng(42)
    X = rng.exponential(scale=1.5, size=(10, 4))

    ctx = extract_basal_context(X, genes)
    assert isinstance(ctx, BasalContext)
    assert ctx.n_cells == 10
    assert len(ctx.genes) == 4
    assert ctx.mean_expression.shape == (4,)
    assert ctx.var_expression.shape == (4,)
    assert ctx.expression_rank.shape == (4,)
    assert (ctx.sparsity >= 0.0).all() and (ctx.sparsity <= 1.0).all()

    d = ctx.to_dict()
    assert d["n_cells"] == 10
    assert d["genes"] == genes


def test_extract_basal_context_validation():
    with pytest.raises(ValueError, match="Expected 2D matrix"):
        extract_basal_context(np.zeros((5, 5, 2)), ["A", "B"])

    with pytest.raises(ValueError, match="do not match gene list"):
        extract_basal_context(np.zeros((5, 3)), ["A", "B"])

    with pytest.raises(ValueError, match="empty cell matrix"):
        extract_basal_context(np.zeros((0, 2)), ["A", "B"])
