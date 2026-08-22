"""Tests for tools/prep_vcc2025_validation.py flags and manifest behavior.

Runs against a tiny synthetic counts matrix — no VCC data needed. Skips if
anndata/scanpy are unavailable (science env optional in some installs).
"""

from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("anndata")
pytest.importorskip("scanpy")
pytest.importorskip("numpy")
pytest.importorskip("pandas")

TOOL = Path(__file__).resolve().parent.parent / "tools" / "prep_vcc2025_validation.py"
spec = importlib.util.spec_from_file_location("prep_vcc2025_validation", TOOL)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def _synthetic_counts(path: Path, n_per_label: int = 4) -> tuple[int, list[str]]:
    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    rng = np.random.default_rng(0)
    genes = ["ACTB", "IFIT1", "MX1"]
    labels = ["non-targeting", "IFIT1-KD", "MX1-KD"]
    n = n_per_label * len(labels)
    X = sparse.csr_matrix(rng.integers(0, 50, size=(n, len(genes))).astype(float))
    obs = pd.DataFrame(
        {"target_gene": np.repeat(labels, n_per_label)},
        index=[f"cell{i}" for i in range(n)],
    )
    ad.AnnData(X=X, obs=obs, var=pd.DataFrame(index=genes)).write_h5ad(str(path))
    return n, [label for label in labels if label != "non-targeting"]


def test_prep_writes_outputs_and_manifest(tmp_path: Path):
    src = tmp_path / "adata_Validation.h5ad"
    n_cells, targets = _synthetic_counts(src)

    rc = mod.main(["--src", str(src)])
    assert rc == 0

    out = src.parent
    assert (out / "real_lognorm.h5ad").is_file()
    assert (out / "basal_lognorm.h5ad").is_file()
    assert (out / "targets.txt").read_text().splitlines() == sorted(targets)
    assert len((out / "gene_order.txt").read_text().splitlines()) == 3

    manifest = json.loads((out / "prep_manifest.json").read_text())
    assert manifest["source"]["sha256"] == mod.sha256_of(src)
    assert "real_lognorm.h5ad" in manifest["outputs"]
    assert manifest["outputs"]["real_lognorm.h5ad"]["bytes"] > 0
    assert src.is_file(), "source must survive a plain prep"
    _ = n_cells


def test_purge_requires_expected_hash(tmp_path: Path, capsys):
    src = tmp_path / "adata_Validation.h5ad"
    _synthetic_counts(src)
    rc = mod.main(["--src", str(src), "--purge-source"])
    assert rc == 2
    assert "refusing" in capsys.readouterr().err
    assert src.is_file()


def test_purge_rejects_hash_mismatch(tmp_path: Path, capsys):
    src = tmp_path / "adata_Validation.h5ad"
    _synthetic_counts(src)
    rc = mod.main(["--src", str(src), "--purge-source", "--expect-source-sha256", "deadbeef"])
    assert rc == 3
    assert "refusing to purge" in capsys.readouterr().err
    assert src.is_file(), "source must NOT be deleted on hash mismatch"


def test_purge_deletes_on_hash_match(tmp_path: Path):
    src = tmp_path / "adata_Validation.h5ad"
    _synthetic_counts(src)
    full_hash = mod.sha256_of(src)
    rc = mod.main(["--src", str(src), "--purge-source", "--expect-source-sha256", full_hash[:12]])
    assert rc == 0
    assert not src.exists(), "matched source should be purged"
    assert (src.parent / "real_lognorm.h5ad").is_file()
    assert (src.parent / "prep_manifest.json").is_file()


def test_missing_src_returns_1(tmp_path: Path):
    rc = mod.main(["--src", str(tmp_path / "nope.h5ad")])
    assert rc == 1
