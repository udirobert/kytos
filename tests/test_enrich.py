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
import pioneer_ner  # noqa: E402
import render_briefing  # noqa: E402
import render_narrative  # noqa: E402
import render_visuals  # noqa: E402
from _enrich_common import load_facts, set_visual_paths  # noqa: E402

API_ENV = (
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "SANDBASE_API_KEY",
    "SEARCH_ROUTE_ORDER",
    "FAL_KEY",
    "FAL_API_KEY",
    "PIONEER_API_KEY",
    "PIONEER_KEY",
    "VENICE_INFERENCE_KEY",
    "VENICE_API_KEY",
    "NARRATION_PROVIDER",
    "KYTOS_NARRATION_PROVIDER",
)


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
    # The fixture has a cached literature/ACTB.json; running with no key must
    # not add new files or error.
    existing = (
        sorted(p.name for p in (run_dir / "literature").glob("*.json"))
        if (run_dir / "literature").is_dir()
        else []
    )
    assert enrich_literature.main(["--run", str(run_dir)]) == 0
    after = (
        sorted(p.name for p in (run_dir / "literature").glob("*.json"))
        if (run_dir / "literature").is_dir()
        else []
    )
    assert after == existing  # no new files added


def test_visuals_degrades_empty(run_dir: Path) -> None:
    assert render_visuals.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "visual").exists()
    assert "visual" not in load_facts(run_dir)


def test_briefing_degrades_empty(run_dir: Path) -> None:
    # No hero.png in the fixture -> briefing must no-op cleanly.
    assert render_briefing.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "visual" / "briefing.mp4").exists()


def test_pioneer_ner_degrades_without_key(run_dir: Path) -> None:
    # No PIONEER_API_KEY in env (cleaned by fixture) → must no-op cleanly.
    assert pioneer_ner.main(["--run", str(run_dir)]) == 0
    assert not (run_dir / "pioneer").exists()


def test_pioneer_train_degrades_without_key(run_dir: Path) -> None:
    assert pioneer_ner.main(["--train"]) == 0


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


# ── SandBase / Tavily search routes (_enrich_common.tavily_search) ────────────


def test_tavily_search_no_routes_raises_lookup(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from _enrich_common import tavily_search

    for name in API_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LookupError):
        tavily_search("q", search_depth="basic", max_results=3)


def test_tavily_search_sandbase_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from _enrich_common import tavily_search

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("SANDBASE_API_KEY", "sb")
    monkeypatch.delenv("SEARCH_ROUTE_ORDER", raising=False)

    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json as j

            return j.dumps(
                {
                    "status": "completed",
                    "output": {"results": [{"title": "t", "url": "u", "content": "c"}]},
                }
            ).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = req.data
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    data, route = tavily_search("q", search_depth="basic", max_results=3)
    assert route == "sandbase"
    assert data["results"][0]["url"] == "u"
    assert captured["url"].endswith("/v1/api/tavily/search")
    assert captured["auth"] == "Bearer sb"


def test_tavily_search_falls_back_to_sandbase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _enrich_common as ec

    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.setenv("SANDBASE_API_KEY", "sb")
    monkeypatch.delenv("SEARCH_ROUTE_ORDER", raising=False)

    def boom(query, search_depth, max_results):
        raise RuntimeError("native down")

    monkeypatch.setattr(ec, "_native_tavily_search", boom)
    monkeypatch.setattr(
        ec,
        "_sandbase_tavily_search",
        lambda q, d, m: {"results": [{"title": "t", "url": "u"}]},
    )
    data, route = ec.tavily_search("q", search_depth="basic", max_results=3)
    assert route == "sandbase"
    assert data["results"][0]["url"] == "u"


def test_tavily_search_all_fail_raises_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _enrich_common as ec

    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.setenv("SANDBASE_API_KEY", "sb")
    monkeypatch.delenv("SEARCH_ROUTE_ORDER", raising=False)
    monkeypatch.setattr(
        ec, "_native_tavily_search", lambda *a: (_ for _ in ()).throw(RuntimeError("n1"))
    )
    monkeypatch.setattr(
        ec, "_sandbase_tavily_search", lambda *a: (_ for _ in ()).throw(RuntimeError("s1"))
    )
    with pytest.raises(RuntimeError) as exc:
        ec.tavily_search("q", search_depth="basic", max_results=3)
    assert "native" in str(exc.value) and "sandbase" in str(exc.value)
