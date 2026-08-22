"""HTML rendering for Observatory pages."""

from __future__ import annotations

import html
from typing import Any

from frontend.observatory import data as data_mod
from frontend.observatory.charts import metrics_bar_chart
from frontend.observatory.meta import PageMeta, SITE_DESCRIPTION, render_head_tags
from frontend.observatory.runs import RunSummary

SITE_TITLE = "Kytos Observatory"


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def _run_severity(facts: dict) -> str:
    """Worst audit severity across a run's flags (for status dots)."""
    severities = {f.get("severity") for f in facts.get("audit_flags") or []}
    if "error" in severities:
        return "error"
    if "warn" in severities:
        return "warn"
    if "info" in severities:
        return "info"
    return "none"


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
        f'<span class="run-pill-id">'
        f'<span class="run-pill-dot dot-{_run_severity(run.facts)}"></span>'
        f"{_h(run.run_id)}</span>"
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


def _head(meta: PageMeta, *, root_prefix: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{render_head_tags(meta, root_prefix=root_prefix)}
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
      <div class="vcc-track" role="img" aria-label="Competition timeline progress">
        <div class="vcc-inner">
          <div class="vcc-line"></div>
          <div class="vcc-fill" id="vcc-fill"></div>
          <div class="vcc-needle" id="vcc-needle"></div>
          <div class="vcc-marker" data-date="2026-08-20T00:00:00Z">
            <time>Aug 20</time><span>validation live</span>
          </div>
          <div class="vcc-marker" data-date="2026-10-22T00:00:00Z">
            <time>Oct 22</time><span>test set</span>
          </div>
          <div class="vcc-marker" data-date="2026-11-05T23:59:59Z">
            <time>Nov 5</time><span>submissions due</span>
          </div>
        </div>
      </div>
      <p class="vcc-countdown">Final submissions in <strong id="vcc-countdown">…</strong></p>
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
    meta = PageMeta(
        title="Home",
        description=SITE_DESCRIPTION,
        canonical_path="/",
    )
    return (
        _head(meta, root_prefix=root_prefix)
        + f'<body class="page-home">{body}'
        + f'<script src="{root_prefix}static/site.js" defer></script>'
        + "</body></html>"
    )


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
    meta = PageMeta(
        title="Runs",
        description=(
            "Index of Kytos experiment runs with cell-eval metrics, audit flags, and provenance."
        ),
        canonical_path="/runs/",
    )
    return _head(meta, root_prefix=root_prefix) + f"<body>{body}</body></html>"


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

    entities = data_mod.load_entity_extractions(run.path)
    entity_html = _entity_rail(entities)

    prov = facts.get("provenance") or {}
    headline_m = facts.get("headline_metrics") or {}
    headline_c = facts.get("ceiling_headroom") or {}
    csv_href = f"{root_prefix}metrics/agg_results.csv"
    # Build the summary with markup, escaping only the dynamic parts — running
    # the whole string through _h() would escape the drill-down links.
    summary_bits = []
    for k in headline_m:
        summary_bits.append(
            f'{_h(k)} <a class="metric-src" href="{csv_href}"'
            f' title="opens metrics/agg_results.csv">{_h(str(headline_m.get(k, "—")))}</a>'
            f" / ceiling {_h(str(headline_c.get(k, '—')))}"
        )
    metric_summary = " · ".join(summary_bits)

    body = f"""
    {_nav(run.run_id, runs, root_prefix=root_prefix)}
    {_confession_banner(facts, run.run_id)}
    <nav class="breadcrumb"><a href="{root_prefix}runs/index.html">← All runs</a></nav>
    <main class="run-layout">
      <section class="stage-column">
        {hero_html}
        <div class="stage-caption">
          <p class="eyebrow">{_h(facts.get("created", ""))}</p>
          <h1>{_h(facts.get("headline", run.run_id))}</h1>
          <p class="metric-summary">{metric_summary}</p>
        </div>
      </section>
      <aside class="evidence-rail">
        <section class="panel">
          <h2>Audit flags</h2>
          {flags_html}
        </section>
        <section class="panel">
          <h2>Metrics vs ceiling</h2>
          <p class="panel-note">From committed CSVs only — never LLM-generated.
          Click a headline value to open its source.</p>
          <div id="metrics-chart" class="chart"></div>
          <script type="application/json" id="metrics-chart-data">{chart_json}</script>
        </section>
        <section class="panel collapsible">
          <h2>Literature</h2>
          <p class="panel-note">Tavily enrichment · auxiliary evidence</p>
          {lit_html}
        </section>
        <section class="panel collapsible">
          <h2>Biomedical NER</h2>
          <p class="panel-note">Pioneer GLiNER2 · deterministic entity extraction</p>
          {entity_html}
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
          <code id="reproduce-cmd">python -m kytos.audit --run experiments/{_h(run.run_id)}
          &amp;&amp; python -m kytos.eval.facts --run experiments/{_h(run.run_id)}</code>
          <button class="copy-btn" type="button" data-copy="#reproduce-cmd">copy</button></p>
        </footer>
      </aside>
    </main>
    <script src="{root_prefix}static/site.js" defer></script>
    """

    headline = str(facts.get("headline", run.run_id))
    desc_bits = [headline]
    if headline_m:
        desc_bits.append(" · ".join(f"{k} {headline_m.get(k)}" for k in headline_m))
    run_desc = " ".join(desc_bits)[:300]
    og_image = None
    hero_path = visual.get("hero")
    if hero_path and media_prefix:
        og_image = f"{media_prefix}{hero_path}"

    meta = PageMeta(
        title=run.run_id,
        description=run_desc or SITE_DESCRIPTION,
        canonical_path=f"/runs/{run.run_id}/",
        og_type="article",
        og_image=og_image,
    )

    return _head(meta, root_prefix=root_prefix) + f"<body class='page-run'>{body}</body></html>"


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
    return _vessel_instrument(facts)


def _vessel_instrument(facts: dict) -> str:
    """The hollow vessel fills with evidence — a data-bound instrument.

    Rendered deterministically from facts.json at build time (zero JS, zero
    API): liquid fill = mean ceiling headroom, amber cracks = warn/error audit
    flags, cyan droplets = info flags. The vessel's shape IS the run's state.
    """
    ceiling = facts.get("ceiling_headroom") or {}
    values = [float(v) for v in ceiling.values() if isinstance(v, (int, float))]
    fill = int(round(100 * sum(values) / len(values))) if values else 0
    fill = max(6, min(100, fill))  # keep a visible droplet even at 0 headroom

    flags = facts.get("audit_flags") or []
    warns = sum(1 for f in flags if f.get("severity") in ("warn", "error"))
    infos = sum(1 for f in flags if f.get("severity") == "info")
    warn_plural = "warning" if warns == 1 else "warnings"
    info_plural = "flag" if infos == 1 else "flags"

    fill_y = 236 - int(fill / 100 * 190)  # liquid surface y (bottom = 236)
    cracks = "".join(
        f'<path class="vessel-crack" d="M {72 + i * 12} {150 + (i % 3) * 14} l {10 + i} {26 + i}"/>'
        for i in range(min(warns, 6))
    )
    droplets = "".join(
        f'<circle class="vessel-info" cx="{55 + i * 22}" cy="{46 + (i % 2) * 28}" r="3"/>'
        for i in range(min(infos, 5))
    )

    return f"""
    <div class="stage-hero vessel-instrument">
      <svg class="vessel-svg" viewBox="0 0 200 250" role="img"
           aria-label="Kytos vessel instrument: fill {fill} percent, {warns} audit warnings">
        <defs>
          <clipPath id="vessel-clip">
            <path d="M 80 12 L 120 12 L 120 58 Q 120 92 156 132 Q 188 168 172 208
                    Q 158 240 100 240 Q 42 240 28 208 Q 12 168 44 132 Q 80 92 80 58 Z"/>
          </clipPath>
        </defs>
        <path class="vessel-glass" d="M 80 12 L 120 12 L 120 58 Q 120 92 156 132
              Q 188 168 172 208 Q 158 240 100 240 Q 42 240 28 208 Q 12 168 44 132 Q 80 92 80 58 Z"/>
        <rect class="vessel-liquid" x="10" y="{fill_y}" width="180" height="250"
              clip-path="url(#vessel-clip)"/>
        <line class="vessel-liquid-line" x1="30" y1="{fill_y}" x2="170" y2="{fill_y}"/>
        <g class="vessel-cracks">{cracks}</g>
        <g class="vessel-droplets">{droplets}</g>
      </svg>
      <p class="vessel-label">κύτος · the hollow vessel fills with evidence</p>
      <p class="vessel-legend">
        <span class="legend-item legend-fill">fill = {fill}% ceiling headroom</span>
        <span class="legend-item legend-warn">{warns} {warn_plural}</span>
        <span class="legend-item legend-info">{infos} info {info_plural}</span>
      </p>
    </div>
    """


def _confession_banner(facts: dict, run_id: str) -> str:
    """Self-own moment: our own run violating our own rules is the demo opener."""
    flags = facts.get("audit_flags") or []
    warns = [f for f in flags if f.get("severity") in ("warn", "error")]
    if not warns:
        return ""
    rules = ", ".join(f"<code>{_h(f.get('rule', '?'))}</code>" for f in warns[:3])
    return f"""
    <section class="confession-banner">
      <p class="eyebrow">Audit confession — k001 fails its own rules</p>
      <p>{len(warns)} warning(s) raised against our own baseline: {rules}.
      Reproduce: <code>python -m kytos.audit --run experiments/{_h(run_id)}</code></p>
    </section>
    """


def _audit_flags(flags: list[dict[str, Any]]) -> str:
    if not flags:
        return '<p class="muted">No audit flags.</p>'
    badge = {"warn": "!", "error": "✕", "info": "i"}
    cards = []
    for flag in flags:
        genes = ", ".join(flag.get("genes") or [])
        severity = flag.get("severity", "info")
        cards.append(
            f"""
            <article class="flag-card severity-{_h(severity)}">
              <header>
                <span class="flag-rule"><span class="flag-badge">{badge.get(severity, "i")}</span>
                {_h(flag.get("rule", ""))}</span>
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


def _entity_rail(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            '<p class="muted">NER pending — run '
            "<code>tools/pioneer_ner.py --run experiments/&lt;run-id&gt;</code>.</p>"
        )
    blocks = []
    for item in items:
        gene = item.get("source_gene", "gene")
        method = item.get("method", "?")
        count = item.get("entity_count", 0)
        by_label = item.get("by_label") or {}
        chips = []
        for label, texts in by_label.items():
            for text in texts:
                chips.append(
                    f'<span class="entity-chip entity-{_h(label)}">{_h(text)}'
                    f'<span class="entity-label">{_h(label)}</span></span>'
                )
        blocks.append(
            f'<details open><summary>{_h(gene)} <span class="entity-meta">'
            f"{count} entities · {_h(method)}</span></summary>"
            f'<div class="entity-grid">{" ".join(chips)}</div></details>'
        )
    return "".join(blocks)
