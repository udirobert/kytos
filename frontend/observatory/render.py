"""HTML rendering for Observatory pages."""

from __future__ import annotations

import html
from typing import Any

from frontend.observatory import data as data_mod
from frontend.observatory.charts import metrics_bar_chart
from frontend.observatory.runs import RunSummary

SITE_TITLE = "Kytos Observatory"


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def _nav(active: str, runs: list[RunSummary], *, root_prefix: str) -> str:
    links = [
        ("Home", f"{root_prefix}index.html", active == "home"),
        ("Runs", f"{root_prefix}runs/index.html", active == "runs"),
    ]
    lis = "".join(
        f'<li><a class="nav-link{" is-active" if is_active else ""}" href="{href}">{label}</a></li>'
        for label, href, is_active in links
    )
    strip = "".join(
        f'<a class="run-pill{" is-active" if run.run_id == active else ""}" '
        f'href="{root_prefix}runs/{_h(run.run_id)}/index.html">'
        f'<span class="run-pill-id">{_h(run.run_id)}</span>'
        f'<span class="run-pill-headline">{_h(run.facts.get("headline", ""))}</span>'
        f"</a>"
        for run in runs
    )
    return f"""
    <header class="site-header">
      <div class="brand">
        <a href="{root_prefix}index.html" class="brand-mark">κύτος</a>
        <div class="brand-text">
          <span class="brand-name">Kytos Observatory</span>
          <span class="brand-tag">Virtual Cell Challenge · build in public</span>
        </div>
      </div>
      <nav class="nav-main"><ul>{lis}</ul></nav>
    </header>
    <div class="run-strip">
      {strip or '<span class="muted">No runs with facts.json yet.</span>'}
    </div>
    """


def _head(title: str, *, root_prefix: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(title)} · {_h(SITE_TITLE)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap"
        rel="stylesheet">
  <link rel="stylesheet" href="{root_prefix}static/style.css">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" defer></script>
</head>
"""


def render_home(runs: list[RunSummary], *, root_prefix: str = "") -> str:
    latest = runs[-1] if runs else None
    hero = ""
    if latest:
        run_href = f"{root_prefix}runs/{_h(latest.run_id)}/index.html"
        metrics = latest.facts.get("headline_metrics") or {}
        metric_bits = ", ".join(f"{k} {v}" for k, v in metrics.items())
        hero = f"""
        <section class="hero-card">
          <p class="eyebrow">Latest run</p>
          <h1>{_h(latest.facts.get("headline", latest.run_id))}</h1>
          <p class="lede">Headline metrics: {_h(metric_bits)}. Biological audit flags and ceiling
          headroom published for public scrutiny — not just leaderboard scores.</p>
          <a class="button" href="{run_href}">Open run detail →</a>
        </section>
        """
    else:
        hero = '<section class="hero-card"><h1>Waiting for first run</h1></section>'

    timeline = """
    <section class="panel timeline-panel">
      <h2>2026 Virtual Cell Challenge</h2>
      <ul class="timeline">
        <li><time>Aug 20</time> Validation live · leaderboard open</li>
        <li><time>Oct 22</time> Final test set released</li>
        <li><time>Nov 5</time> Final submissions due</li>
      </ul>
    </section>
    """

    problem = """
    <section class="panel">
      <h2>Why the Observatory</h2>
      <p class="prose">Arc expanded to six metrics because narrow scoring invites optimization
      against the metric, not the biology. We publish every run's scores <em>and</em> biological
      audit flags, literature, and provenance so failure modes are visible while the competition
      runs.</p>
    </section>
    """

    body = _nav("home", runs, root_prefix=root_prefix) + hero + timeline + problem
    return _head("Home", root_prefix=root_prefix) + f'<body class="page-home">{body}</body></html>'


def render_runs_index(runs: list[RunSummary], *, root_prefix: str = "../") -> str:
    cards = ""
    for run in reversed(runs):
        href = f"{_h(run.run_id)}/index.html"
        metrics = run.facts.get("headline_metrics") or {}
        m = ", ".join(f"{k}={v}" for k, v in metrics.items())
        cards += f"""
        <a class="run-card" href="{href}">
          <span class="run-card-id">{_h(run.run_id)}</span>
          <span class="run-card-headline">{_h(run.facts.get("headline", ""))}</span>
          <span class="run-card-metrics">{_h(m)}</span>
        </a>
        """
    body = (
        _nav("runs", runs, root_prefix=root_prefix)
        + f'<main class="content"><h1>Experiment runs</h1>'
        f'<div class="run-grid">{cards}</div></main>'
    )
    return _head("Runs", root_prefix=root_prefix) + f"<body>{body}</body></html>"


def render_run_detail(
    run: RunSummary,
    runs: list[RunSummary],
    *,
    root_prefix: str = "../../",
    media_prefix: str = "",
) -> str:
    facts = run.facts
    metrics_names, scores, ceilings = data_mod.load_metrics(run.path / "metrics")
    chart_json = metrics_bar_chart(metrics_names, scores, ceilings) if metrics_names else "{}"

    visual = facts.get("visual") or {}
    hero_html = _stage_hero(visual, media_prefix, facts)

    flags_html = _audit_flags(facts.get("audit_flags") or [])
    hypotheses = facts.get("hypotheses_preregistered") or []
    hyp_html = "".join(f"<li>{_h(item)}</li>" for item in hypotheses)

    narrative = data_mod.load_narrative(run.path)
    narrative_html = (
        f'<div class="narrative-body">{data_mod.markdown_to_html(narrative)}</div>'
        if narrative
        else '<p class="muted">Narrative pending — run <code>tools/render_narrative.py</code>.</p>'
    )

    literature = data_mod.load_literature(run.path)
    lit_html = _literature_rail(literature)

    prov = facts.get("provenance") or {}
    headline_m = facts.get("headline_metrics") or {}
    headline_c = facts.get("ceiling_headroom") or {}
    metric_summary = " · ".join(
        f"{k} {headline_m.get(k, '—')} / ceiling {headline_c.get(k, '—')}" for k in headline_m
    )

    body = f"""
    {_nav(run.run_id, runs, root_prefix=root_prefix)}
    <main class="run-layout">
      <section class="stage-column">
        {hero_html}
        <div class="stage-caption">
          <p class="eyebrow">{_h(facts.get("created", ""))}</p>
          <h1>{_h(facts.get("headline", run.run_id))}</h1>
          <p class="metric-summary">{_h(metric_summary)}</p>
        </div>
      </section>
      <aside class="evidence-rail">
        <section class="panel">
          <h2>Metrics vs ceiling</h2>
          <p class="panel-note">From committed CSVs only — never LLM-generated.</p>
          <div id="metrics-chart" class="chart"></div>
          <script type="application/json" id="metrics-chart-data">{chart_json}</script>
        </section>
        <section class="panel">
          <h2>Audit flags</h2>
          {flags_html}
        </section>
        <section class="panel collapsible">
          <h2>Literature</h2>
          <p class="panel-note">Tavily enrichment · auxiliary evidence</p>
          {lit_html}
        </section>
        <section class="panel">
          <h2>Narrative</h2>
          <p class="panel-note">OpenAI digest · traces to facts.json</p>
          {narrative_html}
        </section>
        <section class="panel">
          <h2>Pre-registered hypotheses</h2>
          <ul class="hyp-list">{hyp_html or "<li class='muted'>None</li>"}</ul>
        </section>
        <footer class="provenance">
          <h2>Provenance</h2>
          <dl>
            <dt>commit</dt><dd><code>{_h(str(prov.get("commit", "")))}</code></dd>
            <dt>seed</dt><dd>{_h(str(prov.get("seed", "")))}</dd>
            <dt>code_hash</dt><dd><code>{_h(str(prov.get("code_hash", "")))}</code></dd>
          </dl>
          <p class="reproduce">Reproduce:
          <code>python -m kytos.audit --run experiments/{_h(run.run_id)}</code> then
          <code>python -m kytos.eval.facts --run experiments/{_h(run.run_id)}</code></p>
        </footer>
      </aside>
    </main>
    <script src="{root_prefix}static/site.js" defer></script>
    """

    return (
        _head(run.run_id, root_prefix=root_prefix) + f"<body class='page-run'>{body}</body></html>"
    )


def _stage_hero(visual: dict[str, Any], media_prefix: str, facts: dict) -> str:
    briefing = visual.get("briefing")
    hero = visual.get("hero")
    if briefing:
        src = f"{media_prefix}{briefing}"
        return f"""
        <div class="stage-hero video-hero">
          <video class="briefing-video" src="{_h(src)}" autoplay muted loop playsinline
                 controls poster="{_h(media_prefix + hero) if hero else ""}"></video>
        </div>
        """
    if hero:
        return f"""
        <div class="stage-hero">
          <img src="{_h(media_prefix + hero)}" alt="Run visual" class="hero-image">
        </div>
        """
    return """
    <div class="stage-hero vessel-placeholder" aria-hidden="true">
      <div class="vessel-ring ring-a"></div>
      <div class="vessel-ring ring-b"></div>
      <div class="vessel-core"></div>
      <p class="vessel-label">κύτος · awaiting Fabric briefing</p>
    </div>
    """


def _audit_flags(flags: list[dict[str, Any]]) -> str:
    if not flags:
        return '<p class="muted">No audit flags.</p>'
    cards = []
    for flag in flags:
        genes = ", ".join(flag.get("genes") or [])
        severity = flag.get("severity", "info")
        cards.append(
            f"""
            <article class="flag-card severity-{_h(severity)}">
              <header>
                <span class="flag-rule">{_h(flag.get("rule", ""))}</span>
                <span class="flag-severity">{_h(severity)}</span>
              </header>
              <p>{_h(flag.get("message", ""))}</p>
              <p class="flag-genes"><strong>Genes:</strong> {_h(genes)}</p>
            </article>
            """
        )
    return "".join(cards)


def _literature_rail(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            '<p class="muted">Literature pending — run <code>tools/enrich_literature.py</code>.</p>'
        )
    blocks = []
    for item in items:
        flag_id = item.get("flag_id", "flag")
        results = item.get("results") or []
        if not results:
            blocks.append(f"<p class='muted'>No results for {_h(str(flag_id))}.</p>")
            continue
        lis = []
        for hit in results[:5]:
            title = _h(hit.get("title", "Untitled"))
            url = _h(hit.get("url", "#"))
            snippet = _h(hit.get("snippet", ""))
            lis.append(
                f'<li><a href="{url}" rel="noopener">{title}</a>'
                f'<span class="lit-snippet">{snippet}</span></li>'
            )
        blocks.append(
            f"<details open><summary>{_h(str(flag_id))}</summary>"
            f"<ul class='lit-list'>{''.join(lis)}</ul></details>"
        )
    return "".join(blocks)
