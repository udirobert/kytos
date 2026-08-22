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
    about_html = about.read_text(encoding="utf-8")
    html = run_page.read_text(encoding="utf-8")
    runs_html = (dist / "runs" / "index.html").read_text(encoding="utf-8")

    assert 'rel="icon"' in home_html
    assert 'property="og:image"' in home_html
    assert 'name="twitter:card"' in home_html
    assert "https://kytos.example/" in home_html
    assert "View run" in home_html
    assert "About the 78-day build" in home_html
    assert "home-scroll-hint" not in home_html
    assert "home-data-strip" not in home_html
    assert "home-hero-grid" in home_html
    assert "home-vessel-legend" in home_html
    assert "run-strip" not in home_html
    assert "DE gene recall" in home_html

    assert "VEED Summer Lock-In" in about_html
    assert "vessel-about-panel" in about_html
    assert "Today · London" not in about_html
    assert "vcc-stats" in about_html
    assert "hackathon-countdown" in about_html
    assert "Why the Observatory" in about_html
    assert "substantiation-panel" in about_html
    assert "evidence-strip" in about_html

    assert "k001-mean-shift-baseline" in html
    assert "confession-banner" in html
    assert "DE gene recall" in html
    assert "disclosure-panel" in html
    assert "Audit &amp; metrics" in html
    assert "gene-evidence-link" in html
    assert "evidence-sub-panel" in html
    assert "narrative-more" in html
    assert "briefing-play" in html
    assert "run-header-media-bulletin" in html
    assert "bulletin-data-rail" in html
    assert "visual/bulletin.mp4" in html
    assert (dist / "runs" / "k001-mean-shift-baseline" / "visual" / "bulletin.mp4").is_file()
    assert "chart-details" in html
    assert "run-header" in html
    assert "vessel3d.js" in html  # run detail now has full-bleed vessel
    assert "run-hero" in html
    assert "metrics-chart-data" in html
    assert "vessel3d.js" not in runs_html
    assert "runs-header" in runs_html
    assert "run-insight-card" in runs_html
    assert "% ceiling" in runs_html
    assert "hk-stability" in html or "housekeeping_shift" in html
    assert (dist / "static" / "style.css").is_file()
    assert (dist / "static" / "favicon.svg").is_file()
    assert (dist / "static" / "og-image.png").is_file()
    assert (dist / "robots.txt").is_file()
    assert (dist / "sitemap.xml").is_file()
    assert "Sitemap: https://kytos.example/sitemap.xml" in (dist / "robots.txt").read_text()
    assert "/about/" in (dist / "sitemap.xml").read_text()
    assert "/runs/k001-mean-shift-baseline/" in (dist / "sitemap.xml").read_text()
