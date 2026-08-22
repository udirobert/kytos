"""Enrichment-tool smoke tests (Developer B) — degrade paths only, stdlib only.

Must pass with NO partner clients installed and NO API keys set: enrichment is
auxiliary (famile lesson) — it must never block the experiment or the build.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FIXTURE = ROOT / "tests" / "fixtures" / "k001-mean-shift-baseline"

sys.path.insert(0, str(TOOLS))

import enrich_literature  # noqa: E402
import render_briefing  # noqa: E402
import render_narrative  # noqa: E402
import render_visuals  # noqa: E402
from _enrich_common import load_facts, set_visual_paths  # noqa: E402

API_ENV = ("OPENAI_API_KEY", "TAVILY_API_KEY", "FAL_KEY", "FAL_API_KEY")


@pytest.fixture()
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in API_ENV:
        monkeypatch.delenv(name, raising=False)
    dest = tmp_path / "k001-mean-shift-baseline"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_narrative_fallback(run_dir: Path) -> None:
    assert render_narrative.main(["--run", str(run_dir)]) == 0
    report = run_dir / "narrative" / "report.md"
    assert report.exists()
    text = report.read_text()
    assert "generated_by=fallback" in text
    assert "k001-mean-shift-baseline" in text
    assert "DESigGenesRecall" in text  # metrics table from facts.json
    assert "ACTB" in text  # audit flags from facts.json


def test_literature_degrades_empty(run_dir: Path) -> None:
    assert enrich_literature.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "literature").exists()


def test_visuals_degrades_empty(run_dir: Path) -> None:
    assert render_visuals.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "visual").exists()
    assert "visual" not in load_facts(run_dir)


def test_briefing_degrades_empty(run_dir: Path) -> None:
    # No hero.png in the fixture -> briefing must no-op cleanly.
    assert render_briefing.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "visual" / "briefing.mp4").exists()


def test_missing_facts_json_is_a_contract_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in API_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as exc:
        render_narrative.main(["--run", str(tmp_path)])
    assert exc.value.code == 1


def test_set_visual_paths_persists_only_generated(run_dir: Path) -> None:
    facts = load_facts(run_dir)
    changed = set_visual_paths(run_dir, facts, hero="visual/hero.png", briefing=None)
    assert changed
    again = load_facts(run_dir)
    assert again["visual"]["hero"] == "visual/hero.png"
    assert "briefing" not in again["visual"]


def test_run_id_resolution_from_repo_root() -> None:
    from _enrich_common import resolve_run_dir

    # `--run tests/fixtures/k001-mean-shift-baseline` (relative to repo root)
    # must resolve the same as the absolute path.
    absolute = resolve_run_dir(str(FIXTURE))
    relative = resolve_run_dir(str(FIXTURE.relative_to(ROOT)))
    assert absolute.resolve() == FIXTURE.resolve()
    assert relative.resolve() == FIXTURE.resolve()
