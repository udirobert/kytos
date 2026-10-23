"""Tavily literature enrichment for audit-flagged genes.

Reads `facts.json` -> `audit_flags`, searches the literature for each flagged
gene, and caches results as `literature/<gene>.json`. Evidence grounds the
flags (famile lesson) — it never enters the prediction path.

Degradation (famile / docs/observatory.md §5): missing key, missing client, or
API failure → write NOTHING and exit 0. The site builds without the rail.

Spend cap: at most 5 Tavily searches per run (poker lesson).

Usage:
    python tools/enrich_literature.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json

from _enrich_common import (
    _search_route_order,
    load_facts,
    tavily_search,
    notice,
    record_pipeline_status,
    resolve_run_dir,
    utcnow,
    warn,
)

MAX_GENES = 10  # spend cap: max Tavily searches per run (covers all flagged genes)
MAX_RESULTS = 3  # per gene
MAX_SNIPPET = 500  # chars stored per result


def flagged_genes(facts: dict) -> list[str]:
    """Unique, ordered gene list from audit flags, capped at MAX_GENES."""
    genes: list[str] = []
    for flag in facts.get("audit_flags") or []:
        for gene in flag.get("genes") or []:
            if gene and gene not in genes:
                genes.append(gene)
    return genes[:MAX_GENES]


def search_gene(gene: str) -> dict:
    query = f"{gene} gene CRISPRi knockdown perturbation function"
    response, route = tavily_search(
        query,
        search_depth="basic",
        max_results=MAX_RESULTS,
    )
    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": (item.get("content") or "")[:MAX_SNIPPET],
                "snippet": (item.get("content") or "")[:MAX_SNIPPET],
                "score": item.get("score"),
            }
        )
    return {
        "gene": gene,
        "query": query,
        "generated_at": utcnow(),
        "provider": route,
        "results": results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)
    genes = flagged_genes(facts)

    if not genes:
        notice("literature: no audit-flagged genes; nothing to search")
        record_pipeline_status(
            run_dir,
            "literature",
            "skipped",
            "No audit-flagged genes to search.",
        )
        return 0
    if not _search_route_order():
        notice("literature: skipped (no TAVILY_API_KEY / SANDBASE_API_KEY); run degrades empty")
        record_pipeline_status(
            run_dir,
            "literature",
            "skipped",
            "Neither TAVILY_API_KEY nor SANDBASE_API_KEY set — enrichment not attempted.",
        )
        return 0

    succeeded = 0
    failed = 0
    routes_used: set[str] = set()
    try:
        for gene in genes:
            try:
                payload = search_gene(gene)
            except Exception as exc:  # one gene failing must not kill the rest
                warn(f"Tavily search failed for {gene} ({exc}); continuing")
                failed += 1
                continue
            routes_used.add(payload["provider"])
            out = run_dir / "literature" / f"{gene}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2) + "\n")
            notice(f"literature: cached {out.relative_to(run_dir)}")
            succeeded += 1
    except ImportError:
        warn("tavily client not installed (`uv sync --extra obs`); run degrades empty")
        record_pipeline_status(
            run_dir,
            "literature",
            "failed",
            "tavily-python not installed — no literature retrieved.",
        )
        return 0

    if failed and not succeeded:
        record_pipeline_status(
            run_dir,
            "literature",
            "failed",
            f"All {failed} gene searches failed (API unavailable or erroring).",
        )
    elif failed:
        record_pipeline_status(
            run_dir,
            "literature",
            "fallback",
            "Partial: "
            f"{succeeded}/{len(genes)} genes retrieved via "
            f"{sorted(routes_used)[0] if routes_used else 'none'}; "
            f"{failed} failed.",
        )
    else:
        record_pipeline_status(
            run_dir,
            "literature",
            "done",
            f"Retrieved evidence for {succeeded} flagged gene{'s' if succeeded != 1 else ''}.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
