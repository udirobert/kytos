"""Package import smoke tests — must pass with NO heavy deps installed.

Mirrors the harness's "degrade, don't crash" property (submission/script.py).
The src layout is enough for an import: no anndata/torch/cell-eval needed here.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_kytos_importable() -> None:
    import kytos  # noqa: F401

    assert kytos.__version__ == "0.0.1"


def test_subpackages_importable() -> None:
    import kytos.audit
    import kytos.data
    import kytos.eval
    import kytos.features
    import kytos.models
    import kytos.serve  # noqa: F401


def test_fixtures_present() -> None:
    root = Path(__file__).resolve().parent.parent
    for rel in (
        "submission/fixtures/gene_order.txt",
        "submission/fixtures/targets.txt",
        "submission/fixtures/basal.txt",
    ):
        assert (root / rel).exists(), f"missing fixture {rel}"
