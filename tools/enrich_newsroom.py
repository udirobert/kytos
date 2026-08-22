"""Newsroom research + broadcast script for a run (Tavily).

Turns a run's committed facts into a newsroom broadcast:

  1. research — Tavily searches on the run's field context, cached as
     `newsroom/research.json` (titles, urls, snippets — never metrics).
  2. script   — a deterministic spoken broadcast script
     (`newsroom/script.md`) that frames the run digest as a news bulletin:
     opening, headline, audit segment, "what the field is saying", sign-off.

`render_briefing.py` prefers `newsroom/script.md` over `narrative/report.md`,
so the oracle anchor speaks the broadcast instead of a plain digest.

Hard rules (docs/observatory.md §5): reads facts.json only; research never
enters the prediction path; degrade to a no-op (exit 0) on missing key /
client / API failure — the site builds without the newsroom.

Spend cap: at most 3 Tavily searches per run (poker lesson).

Usage:
    python tools/enrich_newsroom.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json

from _enrich_common import env_key, load_facts, notice, resolve_run_dir, utcnow, warn

MAX_SEARCHES = 3  # spend cap: max Tavily searches per run
MAX_RESULTS = 3  # per query
MAX_SNIPPET = 400  # chars stored per result

FIELD_QUERIES = [
    "virtual cell competition single-cell perturbation prediction",
    "single-cell perturbation prediction foundation model 2026",
    "flow matching virtual cell gene expression prediction",
]

BROADCAST_OPEN = (
    "This is the Kytos Newsroom. Run one of seventy-eight. "
    "Every run is published, and so is every failure."
)


def field_research(api_key: str) -> list[dict]:
    """Tavily searches on the field context; returns deduped top results."""
    from tavily import TavilyClient  # lazy: partner client is optional

    client = TavilyClient(api_key=api_key)
    seen: set[str] = set()
    results: list[dict] = []
    for query in FIELD_QUERIES[:MAX_SEARCHES]:
        try:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=MAX_RESULTS,
            )
        except Exception as exc:  # one query failing must not kill the rest
            warn(f"Tavily search failed for {query!r} ({exc}); continuing")
            continue
        for item in response.get("results", []):
            url = item.get("url") or ""
            if url in seen:
                continue
            seen.add(url)
            results.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "snippet": (item.get("content") or "")[:MAX_SNIPPET],
                    "score": item.get("score"),
                }
            )
    return results[:6]


def broadcast_script(facts: dict, research: list[dict]) -> str:
    """Deterministic spoken broadcast script grounded in facts + research."""
    headline = facts.get("headline") or "no headline in facts.json"
    metrics = facts.get("headline_metrics") or {}
    ceiling = facts.get("ceiling_headroom") or {}
    flags = facts.get("audit_flags") or []
    run_id = facts.get("run_id") or "k001"

    metric_line = ", ".join(f"{k} {v}" for k, v in metrics.items()) or "no metrics yet"
    ceiling_line = ", ".join(f"{k} {v}" for k, v in ceiling.items()) or "no ceiling yet"

    lines = [
        f"# {run_id} — KYTOS NEWSROOM broadcast script",
        "",
        f"> Deterministic broadcast wrapper over facts.json + newsroom/research.json "
        f"(no LLM). Generated {utcnow()} UTC.",
        "",
        BROADCAST_OPEN,
        "",
        "Headline: " + headline,
        "",
        "Metrics: " + metric_line + "; ceiling " + ceiling_line + ".",
        "",
    ]

    if flags:
        lines.append(f"Our audit flags {len(flags)} issue" + ("s" if len(flags) != 1 else "") + ":")
        for flag in flags:
            genes = ", ".join(flag.get("genes") or [])
            lines.append(
                f"- a {flag.get('severity', 'info')} flag on {flag.get('rule', '?')} "
                f"affecting {genes}."
            )
    else:
        lines.append("No audit flags on this run.")
    lines.append("")

    if research:
        lines.append("What the field is saying:")
        for item in research[:2]:
            lines.append(f"- {item.get('title', 'untitled paper')}.")
    else:
        lines.append("No field research cached for this broadcast.")
    lines.append("")

    lines.append(
        "We publish every run, and we publish our own failures. This has been the Kytos Newsroom."
    )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)

    api_key = env_key("TAVILY_API_KEY")
    if not api_key:
        notice("newsroom: skipped (no TAVILY_API_KEY); run degrades without newsroom")
        return 0

    research: list[dict] = []
    try:
        research = field_research(api_key)
    except ImportError:
        warn("tavily client not installed (`uv sync --extra obs`); run degrades without newsroom")
        return 0
    except Exception as exc:
        warn(f"newsroom research failed ({exc}); run degrades without newsroom")
        return 0

    newsroom_dir = run_dir / "newsroom"
    newsroom_dir.mkdir(parents=True, exist_ok=True)

    if research:
        (newsroom_dir / "research.json").write_text(
            json.dumps({"generated_at": utcnow(), "results": research}, indent=2) + "\n"
        )
        notice(f"newsroom: cached {len(research)} research results")

    script = broadcast_script(facts, research)
    (newsroom_dir / "script.md").write_text(script)
    notice(f"newsroom: wrote {newsroom_dir.joinpath('script.md').relative_to(run_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
