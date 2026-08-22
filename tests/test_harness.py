"""End-to-end tests for the submission harness (submission/script.py).

The harness is the load-bearing contract (NOTES §4 ratiocine): official inputs
→ cell-eval-ready AnnData. These tests lock the input→output shape so the
first real `cell-eval run` cannot silently trip over the schema.

The unit-level group/shape assertions run with ZERO third-party deps — they
catch the groups-vs-X-rows mismatch even before `anndata` is installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "submission" / "fixtures"

sys.path.insert(0, str(ROOT / "submission"))
import script as harness  # noqa: E402

GENE_ORDER = [f"gene{i}" for i in range(20)]
TARGETS = ["gene2", "gene7", "gene13"]
CONTROL = "control"
N_CELLS = 100


def _inputs() -> harness.ChallengeInputs:
    return harness.ChallengeInputs(
        basal_path=FIXTURES / "basal.txt",
        targets_path=FIXTURES / "targets.txt",
        gene_order_path=FIXTURES / "gene_order.txt",
    )


def test_mean_shift_groups_match_values_shape() -> None:
    """The regression: groups had n_cells entries while X had n_cells*(1+n) rows."""
    result = harness.MeanShiftBaseline().predict(_inputs(), GENE_ORDER, TARGETS)
    assert len(result.groups) == result.values.shape[0] == N_CELLS * (1 + len(TARGETS))
    assert result.values.shape[1] == len(GENE_ORDER)

    # Group composition: control block first, then one block per target gene.
    assert result.groups[:N_CELLS] == [CONTROL] * N_CELLS
    offset = N_CELLS
    for target in TARGETS:
        assert result.groups[offset : offset + N_CELLS] == [target] * N_CELLS
        offset += N_CELLS


def test_harness_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "pred.h5ad"
    meta_path = tmp_path / "meta.json"
    rc = harness.main(
        [
            "--basal",
            str(FIXTURES / "basal.txt"),
            "--targets",
            str(FIXTURES / "targets.txt"),
            "--gene-order",
            str(FIXTURES / "gene_order.txt"),
            "--out",
            str(out),
            "--meta",
            str(meta_path),
        ]
    )
    assert rc == 0

    meta = json.loads(meta_path.read_text())
    assert meta["strategy"] == "mean-shift"
    assert meta["n_per_group"] == N_CELLS
    assert meta["n_targets"] == len(TARGETS)
    assert meta["gene_order_sha"]  # provenance: content hash of the gene axis

    try:
        import anndata as ad
    except ImportError:
        ad = None

    if ad is not None:
        # Real H5AD path: cell × gene matrix, per-cell perturbation labels,
        # gene axis == expected_genelist.
        adata = ad.read_h5ad(out)
        expected_rows = N_CELLS * (1 + len(TARGETS))
        assert adata.shape == (expected_rows, len(GENE_ORDER))
        assert list(adata.var.index) == GENE_ORDER
        pert = adata.obs["perturbation"]
        assert len(pert) == expected_rows
        assert (pert == CONTROL).sum() == N_CELLS
        for target in TARGETS:
            assert (pert == target).sum() == N_CELLS
    else:
        # No anndata: harness degrades to a JSON placeholder — never crashes.
        placeholder = json.loads(out.read_text())
        assert placeholder["genes"] == GENE_ORDER


def test_missing_input_is_a_contract_error(tmp_path: Path) -> None:
    inputs = _inputs()
    inputs.basal_path = tmp_path / "does-not-exist.h5ad"
    with pytest.raises(FileNotFoundError):
        inputs.validate()
