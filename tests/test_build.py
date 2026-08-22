"""Observatory static site build smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"


def test_build_produces_run_page() -> None:
    result = subprocess.run(
        [sys.executable, str(FRONTEND / "build.py"), "--out", str(DIST)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Built" in result.stdout

    home = DIST / "index.html"
    run_page = DIST / "runs" / "k001-mean-shift-baseline" / "index.html"
    assert home.is_file()
    assert run_page.is_file()

    html = run_page.read_text(encoding="utf-8")
    assert "k001-mean-shift-baseline" in html
    assert "Audit flags" in html
    assert "metrics-chart-data" in html
    assert "hk-stability" in html or "housekeeping_shift" in html
    assert (DIST / "static" / "style.css").is_file()
