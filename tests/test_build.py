"""Observatory static site build smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


def test_build_produces_run_page(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, str(FRONTEND / "build.py"), "--out", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "KYTOS_SITE_URL": "https://kytos.example"},
    )
    assert "Built" in result.stdout

    home = dist / "index.html"
    about = dist / "about" / "index.html"
    run_page = dist / "runs" / "k001-mean-shift-baseline" / "index.html"
    assert home.is_file()
    assert about.is_file()
    assert run_page.is_file()

    home_html = home.read_text(encoding="utf-8")
    assert 'rel="icon"' in home_html
    assert 'property="og:image"' in home_html
    assert 'name="twitter:card"' in home_html
    assert "https://kytos.example/" in home_html
    assert "Open run detail" in home_html
    assert "About the build" in home_html

    about_html = about.read_text(encoding="utf-8")
    assert "VEED Summer Lock-In" in about_html
    assert "vcc-stats" in about_html
    assert "hackathon-countdown" in about_html
    assert "Why the Observatory" in about_html

    html = run_page.read_text(encoding="utf-8")
    assert "k001-mean-shift-baseline" in html
    assert "Audit flags" in html
    assert "Biomedical NER" in html
    assert "fine-tuned LoRA" in html
    assert "entity-summary" in html
    assert "metrics-chart-data" in html
    assert "hk-stability" in html or "housekeeping_shift" in html
    assert (dist / "static" / "style.css").is_file()
    assert (dist / "static" / "favicon.svg").is_file()
    assert (dist / "static" / "og-image.png").is_file()
    assert (dist / "robots.txt").is_file()
    assert (dist / "sitemap.xml").is_file()
    assert "Sitemap: https://kytos.example/sitemap.xml" in (dist / "robots.txt").read_text()
    assert "/about/" in (dist / "sitemap.xml").read_text()
    assert "/runs/k001-mean-shift-baseline/" in (dist / "sitemap.xml").read_text()
