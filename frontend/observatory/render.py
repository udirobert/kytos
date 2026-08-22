"""HTML rendering for Observatory pages."""

from __future__ import annotations

import html
import json
from typing import Any

from frontend.observatory import data as data_mod
from frontend.observatory.charts import metrics_bar_chart
from frontend.observatory.meta import PageMeta, SITE_DESCRIPTION, render_head_tags
from frontend.observatory.runs import RunSummary

SITE_TITLE = "Kytos Observatory"

# The 78-day public build (Aug 20 → Nov 5). The demo's closer — "run #1 of 78"
# — is stamped on the surface so the long-game story survives a silent scroll.
VCC_DAYS = 78
VCC_START = "2026-08-20T00:00:00Z"
VCC_TEST_SET = "2026-10-22T00:00:00Z"
VCC_END = "2026-11-05T23:59:59Z"
HACKATHON_END = "2026-08-22T18:00:00Z"  # 19:00 London (BST) opt-in deadline


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def _run_index(run: RunSummary, runs: list[RunSummary]) -> int:
    """1-based position of a run in the published sequence (for the #N of 78 stamp)."""
    try:
        return runs.index(run) + 1
    except ValueError:
        return len(runs)


def _count_span(cls: str, value: Any, suffix: str = "", text: str = "0") -> str:
    """A data-strip value span that counts up to `value` on load."""
    return f'<span class="{cls}" data-count-to="{value}" data-suffix="{suffix}">{text}</span>'


def _narrative_label(narrative: str | None) -> str:
    """Label the narrative panel from its own provenance comment — never guess."""
    first = (narrative or "").splitlines()[0] if narrative else ""
    if "generated_by=llm" in first:
        provider = (
            "venice"
            if "provider=venice" in first
            else "openai"
            if "provider=openai" in first
            else "llm"
        )
        return f"LLM digest ({provider}) · traces to facts.json"
    if "generated_by=fallback" in first:
        return "deterministic digest · no LLM · site builds offline"
    return "run digest · traces to facts.json"


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
    if latest:
        run_href = f"{root_prefix}runs/{_h(latest.run_id)}/index.html"
        metrics = latest.facts.get("headline_metrics") or {}
        metric_bits = ", ".join(f"{k} {v}" for k, v in metrics.items())
        headline = _h(latest.facts.get("headline", latest.run_id))
        vd = _vessel_data(latest.facts)
        vessel_json = json.dumps(vd)
        svg = _vessel_svg(latest.facts, clip_id="vessel-clip-home")

        # Full-bleed 3D vessel as background layer
        stage = f"""
        <section class="home-stage">
          <div class="vessel-fullscreen vessel-3d-container vessel-home" id="vessel-canvas">
            <div class="vessel-svg-fallback">{svg}</div>
            <script type="application/json" id="vessel-data">{vessel_json}</script>
          </div>
          <div class="home-overlay">
            <div class="home-overlay-content">
              <h1 class="home-headline">
                Predict how an unseen cell responds —<br>
                and <em>show when the model is biologically wrong.</em>
              </h1>
              <p class="home-lede">
                Run #{_run_index(latest, runs)} of {VCC_DAYS} — {_h(latest.run_id)}: {headline}.
                Headline metrics {_h(metric_bits)}.
              </p>
              <p class="vessel-legend-inline">
                <span class="legend-item legend-fill">fill = ceiling headroom</span>
                <span class="legend-item legend-warn">cracks = audit warnings</span>
                <span class="legend-item legend-info">droplets = info flags</span>
              </p>
              <div class="home-cta-row">
                <a class="button" href="{run_href}">Open run detail →</a>
                <a class="home-chip" href="{root_prefix}runs/index.html">
                  Browse all <strong>{len(runs)}</strong> runs
                </a>
              </div>
            </div>
          </div>
          <div class="home-data-strip">
            <span class="data-strip-item">
              <span class="data-strip-label">fill</span>
              {_count_span("data-strip-value", vd["fill_pct"], "%", "0%")}
            </span>
            <span class="data-strip-sep"></span>
            <span class="data-strip-item">
              <span class="data-strip-label">audit</span>
              {_count_span("data-strip-value data-strip-warn", vd["warns"], " warn", "0 warn")}
            </span>
            <span class="data-strip-sep"></span>
            <span class="data-strip-item">
              <span class="data-strip-label">build</span>
              <span class="data-strip-value" id="home-build-day" data-vcc-days="{VCC_DAYS}">…</span>
            </span>
            <span class="data-strip-sep"></span>
            <span class="data-strip-item">
              <span class="data-strip-label">nov 5</span>
              <span class="data-strip-value" id="home-vcc-left">…</span>
            </span>
          </div>
          <div class="home-scroll-hint">scroll ↓</div>
        </section>
        """
    else:
        stage = """
        <section class="home-stage">
          <h1 class="home-headline">Waiting for the first run</h1>
          <p class="home-lede">The Observatory lights up when the first experiment
          lands.</p>
        </section>
        """

    timeline = f"""
    <section class="panel timeline-panel">
      <div class="timeline-hackathon">
        <p class="timeline-eyebrow">🔥 Today · London</p>
        <h2>{{Tech: Europe}} × VEED Summer Lock-In</h2>
        <p class="timeline-tagline">
          Observatory Milestone 0 goes live today — same repo, same public build,
          all the way to VCC finals 🧬
        </p>
        <p class="hackathon-deadline">
          ⏰ Opt-in closes <strong id="hackathon-countdown">…</strong>
          <span class="muted">· 19:00 London</span>
        </p>
      </div>

      <div class="timeline-vcc">
        <p class="timeline-eyebrow">📡 78-day public build</p>
        <h3 class="timeline-subhead">Virtual Cell Challenge 2026</h3>
        <div class="vcc-track" role="img" aria-label="Virtual Cell Challenge timeline"
             data-vcc-start="{VCC_START}"
             data-vcc-end="{VCC_END}"
             data-vcc-test="{VCC_TEST_SET}"
             data-hackathon-end="{HACKATHON_END}"
             data-vcc-days="{VCC_DAYS}">
          <div class="vcc-inner">
            <div class="vcc-line"></div>
            <div class="vcc-fill" id="vcc-fill"></div>
            <div class="vcc-needle" id="vcc-needle"></div>
            <div class="vcc-marker" data-date="{VCC_START}">
              <span class="vcc-marker-emoji" aria-hidden="true">🚀</span>
              <time>Aug 20</time><span>we ship</span>
            </div>
            <div class="vcc-marker vcc-marker-hackathon" data-date="2026-08-22T12:00:00Z">
              <span class="vcc-marker-emoji" aria-hidden="true">🏆</span>
              <time>Aug 22</time><span>you are here</span>
            </div>
            <div class="vcc-marker" data-date="{VCC_TEST_SET}">
              <span class="vcc-marker-emoji" aria-hidden="true">🎯</span>
              <time>Oct 22</time><span>test set</span>
            </div>
            <div class="vcc-marker" data-date="{VCC_END}">
              <span class="vcc-marker-emoji" aria-hidden="true">🏁</span>
              <time>Nov 5</time><span>finale</span>
            </div>
          </div>
        </div>
        <div class="vcc-stats">
          <div class="vcc-stat">
            <span class="vcc-stat-label">🏁 Submit by Nov 5</span>
            <strong class="vcc-stat-value" id="vcc-countdown">…</strong>
            <span class="vcc-stat-note">Arc scores the hidden test set</span>
          </div>
          <div class="vcc-stat">
            <span class="vcc-stat-label">📡 Build day</span>
            <strong class="vcc-stat-value"><span id="vcc-day">…</span>"
            "<span class="vcc-stat-of">/{VCC_DAYS}</span></strong>
            <span class="vcc-stat-note">Publishing every run in the open</span>
          </div>
          <div class="vcc-stat">
            <span class="vcc-stat-label">🎯 Test set drops</span>
            <strong class="vcc-stat-value" id="vcc-testsets">…</strong>
            <span class="vcc-stat-note">New perturbations to predict</span>
          </div>
        </div>
      </div>
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

    body = _nav("home", runs, root_prefix=root_prefix) + stage + timeline + problem
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
        severity = _run_severity(run.facts)
        vd = _vessel_data(run.facts)
        cards += f"""
        <a class="run-card" href="{href}">
          <span class="run-card-top">
            <span class="run-card-id">
              <span class="run-pill-dot dot-{severity}"></span>{_h(run.run_id)}
            </span>
            <span class="run-card-fill">{vd["fill_pct"]}%</span>
          </span>
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
        needs_vessel=False,
    )
    return _head(meta, root_prefix=root_prefix) + f'<body class="page-runs">{body}</body></html>'


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
    vd = _vessel_data(facts)

    # When real visual assets exist (fal hero, Fabric briefing), use them as
    # the full-bleed hero instead of the 3D vessel. The 3D vessel is the
    # fallback when no committed visuals are available.
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
    entity_summary = data_mod.summarize_entity_extractions(entities)
    entity_html = _entity_rail(entities, entity_summary)

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
    <nav class="breadcrumb">
      <a href="{root_prefix}runs/index.html">← All runs</a>
      {"<span class='jk-hint'>j/k · switch runs</span>" if len(runs) > 1 else ""}
    </nav>
    <section class="run-hero">
      {hero_html}
      <div class="run-hero-overlay">
        <p class="eyebrow">
          Run #{_run_index(run, runs)} of {VCC_DAYS} · {_h(facts.get("created", ""))}
        </p>
        <h1 class="run-hero-title">{_h(facts.get("headline", run.run_id))}</h1>
        <p class="metric-summary">{metric_summary}</p>
        <div class="run-hero-strip">
          <span class="data-strip-item">
            <span class="data-strip-label">fill</span>
            {_count_span("data-strip-value", vd["fill_pct"], "%", "0%")}
          </span>
          <span class="data-strip-sep"></span>
          <span class="data-strip-item">
            <span class="data-strip-label">audit</span>
            {_count_span("data-strip-value data-strip-warn", vd["warns"], " warn", "0 warn")}
          </span>
          <span class="data-strip-sep"></span>
          <span class="data-strip-item">
            <span class="data-strip-label">info</span>
            {_count_span("data-strip-value", vd["infos"])}
          </span>
          {"<span class='data-strip-sep'></span>" if entity_summary["total_entities"] else ""}
          {
        f'''<span class="data-strip-item">
            <span class="data-strip-label">entities</span>
            {_count_span("data-strip-value", entity_summary["total_entities"])}
          </span>'''
        if entity_summary["total_entities"]
        else ""
    }
        </div>
      </div>
    </section>
    <main class="run-evidence">
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
      <section class="panel collapsible" id="newsroom">
        <h2>What the field is saying</h2>
        <p class="panel-note">Tavily field research · woven into the newsroom broadcast</p>
        {_newsroom_rail(run.path)}
      </section>
      <section class="panel collapsible" id="biomedical-ner">
        <h2>Biomedical NER</h2>
        <p class="panel-note">{_entity_panel_note(entity_summary)}</p>
        {entity_html}
      </section>
      <section class="panel">
        <h2>Narrative</h2>
        <p class="panel-note">{_narrative_label(narrative)}</p>
        {narrative_html}
      </section>
      <section class="panel">
        <h2>Pre-registered hypotheses</h2>
        <ul class="hyp-list">{hyp_html or "<li class='muted'>None</li>"}</ul>
      </section>
      {_verification_section(run.path, run.run_id)}
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
    </main>
    <script src="{root_prefix}static/site.js" defer></script>
    """

    headline = str(facts.get("headline", run.run_id))
    desc_bits = [headline]
    if headline_m:
        desc_bits.append(" · ".join(f"{k} {headline_m.get(k)}" for k in headline_m))
    run_desc = " ".join(desc_bits)[:300]
    og_image = visual.get("hero")  # run-relative; meta.py resolves it

    meta = PageMeta(
        title=run.run_id,
        description=run_desc or SITE_DESCRIPTION,
        canonical_path=f"/runs/{run.run_id}/",
        og_type="article",
        og_image=og_image,
        needs_plotly=True,
    )

    return _head(meta, root_prefix=root_prefix) + f"<body class='page-run'>{body}</body></html>"


def _stage_hero(visual: dict[str, Any], media_prefix: str, facts: dict) -> str:
    """Full-bleed hero for the run detail page.

    Priority: Fabric briefing video > fal hero image > 3D vessel.
    Each variant fills the viewport as a background layer.
    """
    briefing = visual.get("briefing")
    hero = visual.get("hero")
    # facts.json visual paths are run-relative and already include the
    # `visual/` dir (run-protocol schema) — build.py copies the run's visual/
    # next to the page, so the facts value IS the correct src. Prepending
    # media_prefix here double-prefixes to visual/visual/... (regression fixed).
    if briefing:
        src = f"{_h(briefing)}"
        poster = f"{_h(hero)}" if hero else ""
        return f"""
        <div class="hero-fullscreen hero-video">
          <video class="briefing-video" src="{src}" autoplay muted loop playsinline
                 controls poster="{poster}" preload="none"></video>
          <span class="briefing-stamp">kytos newsroom · run #1 of 78 · the oracle speaks</span>
          <button class="briefing-unmute" type="button" hidden
                  aria-label="Unmute the oracle briefing">♪ unmute — the oracle sings</button>
        </div>
        """
    if hero:
        return f"""
        <div class="hero-fullscreen hero-image-bg">
          <img src="{_h(hero)}" alt="Run visual" class="hero-image">
        </div>
        """
    return _vessel_stage(facts, fullscreen=True)


def _vessel_data(facts: dict) -> dict:
    """Extract the data that drives the 3D vessel from facts.json."""
    ceiling = facts.get("ceiling_headroom") or {}
    values = [float(v) for v in ceiling.values() if isinstance(v, (int, float))]
    fill = int(round(100 * sum(values) / len(values))) if values else 0
    fill = max(6, min(100, fill))
    flags = facts.get("audit_flags") or []
    return {
        "fill_pct": fill,
        "warns": sum(1 for f in flags if f.get("severity") in ("warn", "error")),
        "infos": sum(1 for f in flags if f.get("severity") == "info"),
    }


def _vessel_svg(facts: dict, *, svg_class: str = "vessel-svg", clip_id: str = "vessel-clip") -> str:
    """The κύτος vessel as an SVG — the fallback for the 3D scene.

    Liquid fill = mean ceiling headroom, amber cracks = warn/error audit flags,
    cyan droplets = info flags. The vessel's shape IS the run's state.
    """
    vd = _vessel_data(facts)
    fill, warns, infos = vd["fill_pct"], vd["warns"], vd["infos"]

    fill_y = 236 - int(fill / 100 * 190)  # liquid surface y (bottom = 236)
    cracks = "".join(
        f'<path class="vessel-crack" d="M {72 + i * 12} {150 + (i % 3) * 14} l {10 + i} {26 + i}"/>'
        for i in range(min(warns, 6))
    )
    droplets = "".join(
        f'<circle class="vessel-info" cx="{55 + i * 22}" cy="{46 + (i % 2) * 28}" r="3"/>'
        for i in range(min(infos, 5))
    )
    glass_path = (
        "M 80 12 L 120 12 L 120 58 Q 120 92 156 132 Q 188 168 172 208"
        " Q 158 240 100 240 Q 42 240 28 208 Q 12 168 44 132 Q 80 92 80 58 Z"
    )

    return f"""
      <svg class="{svg_class}" viewBox="0 0 200 250" role="img"
           aria-label="Kytos vessel instrument: fill {fill} percent, {warns} audit warnings">
        <defs>
          <clipPath id="{clip_id}">
            <path d="{glass_path}"/>
          </clipPath>
        </defs>
        <path class="vessel-glass" d="{glass_path}"/>
        <rect class="vessel-liquid" x="10" y="{fill_y}" width="180" height="250"
              clip-path="url(#{clip_id})"/>
        <line class="vessel-liquid-line" x1="30" y1="{fill_y}" x2="170" y2="{fill_y}"/>
        <g class="vessel-cracks">{cracks}</g>
        <g class="vessel-droplets">{droplets}</g>
      </svg>"""


def _vessel_stage(
    facts: dict,
    *,
    stage_class: str = "stage-hero vessel-instrument",
    fullscreen: bool = False,
) -> str:
    """Vessel instrument with 3D canvas + SVG fallback + legend.

    The 3D scene loads progressively via import map. If WebGL is unavailable
    the SVG fallback stays visible and the canvas never replaces it.

    When fullscreen=True, the vessel container itself becomes the full-bleed
    background layer (used by run detail page when no fal/fabric visuals exist).
    """
    vd = _vessel_data(facts)
    fill, warns, infos = vd["fill_pct"], vd["warns"], vd["infos"]
    warn_plural = "warning" if warns == 1 else "warnings"
    info_plural = "flag" if infos == 1 else "flags"
    vessel_json = json.dumps(vd)

    svg = _vessel_svg(facts)
    if fullscreen:
        container_class = "vessel-fullscreen vessel-3d-container"
        inner = f"""
        <div class="vessel-svg-fallback">{svg}</div>
        <script type="application/json" id="vessel-data">{vessel_json}</script>
        """
        return f"""
        <div class="{container_class}" id="vessel-canvas">
          {inner}
        </div>
        """
    return f"""
    <div class="{stage_class}">
      <div class="vessel-3d-container" id="vessel-canvas">
        <div class="vessel-svg-fallback">{svg}</div>
      </div>
      <script type="application/json" id="vessel-data">{vessel_json}</script>
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


def _entity_panel_note(summary: dict[str, Any]) -> str:
    if not summary.get("gene_count"):
        return (
            "Pioneer GLiNER2 · fine-tuned on Tavily literature when available · "
            "regex fallback offline"
        )
    label_bits = ", ".join(
        f"{count} {_h(label.replace('_', ' '))}"
        for label, count in sorted(
            (summary.get("label_totals") or {}).items(),
            key=lambda item: (-item[1], item[0]),
        )[:4]
    )
    model_label = summary.get("model_label") or "unknown"
    badge_cls = "pioneer-badge-finetuned" if summary.get("is_fine_tuned") else "pioneer-badge-base"
    model_id = summary.get("model_id") or ""
    job_hint = ""
    if summary.get("is_fine_tuned") and model_id:
        job_hint = f" · job <code>{_h(model_id[:8])}…</code>"
    return (
        f'<a href="https://docs.pioneer.ai" rel="noopener">Pioneer</a> '
        f'<span class="pioneer-badge {badge_cls}">{_h(model_label)}</span>'
        f" · {summary['total_entities']} entities across {summary['gene_count']} genes"
        f"{job_hint}"
        f"{f' · {label_bits}' if label_bits else ''}"
    )


def _entity_method_badge(item: dict[str, Any]) -> str:
    label = data_mod.entity_model_label(item)
    if label == "fine-tuned LoRA":
        cls = "pioneer-badge pioneer-badge-finetuned"
    elif label == "regex fallback":
        cls = "pioneer-badge pioneer-badge-fallback"
    else:
        cls = "pioneer-badge pioneer-badge-base"
    return f'<span class="{cls}">{_h(label)}</span>'


def _verification_section(run_dir: Any, run_id: str) -> str:
    """The trust layer: we test our own pipeline, and an agent verifies the surface.

    Renders whatever committed verification artifacts exist; each card degrades
    to a muted 'pending' note when the artifact is absent (site builds offline).
    """
    planted = data_mod.load_planted_signal(run_dir)
    holo = data_mod.load_holo_audit(run_dir)
    holo_shot = "holo_screenshot.png"

    cards = []

    if planted:
        ok = planted.get("status") == "pass"
        summary = planted.get("summary") or "—"
        cases = planted.get("cases") or []
        passed = sum(1 for c in cases if c.get("ok"))
        cards.append(
            f"""
            <article class="verify-card {"verify-pass" if ok else "verify-fail"}">
              <header>
                <span class="verify-badge">{"PASS" if ok else "FAIL"}</span>
                <span class="verify-title">Planted-signal self-test</span>
              </header>
              <p>We plant known-answer failures through our own audit rules. If it
              can't catch what we planted, it can't be trusted to catch what we
              didn't. <strong>{summary}</strong> ({passed}/{len(cases)} cases).</p>
              <p class="verify-cmd"><code>python tools/planted_signal.py</code></p>
            </article>
            """
        )
    else:
        cards.append(
            """
            <article class="verify-card verify-pending">
              <header>
                <span class="verify-badge">PENDING</span>
                <span class="verify-title">Planted-signal self-test</span>
              </header>
              <p>Run <code>python tools/planted_signal.py --json "
            "…/verification/planted_signal.json</code>.</p>
            </article>
            """
        )

    if holo:
        ok = holo.get("status") == "pass"
        model = holo.get("model") or "h/web-surfer-flash"
        summary = holo.get("summary") or "—"
        results = holo.get("results") or []
        passed = sum(1 for r in results if r.get("ok"))
        shot = (
            f'<img class="verify-shot" src="{_h(holo_shot)}" '
            f'alt="Holo agent screenshot of the live run page">'
            if (run_dir / holo_shot).is_file()
            else ""
        )
        cards.append(
            f"""
            <article class="verify-card {"verify-pass" if ok else "verify-fail"}">
              <header>
                <span class="verify-badge">{"PASS" if ok else "FAIL"}</span>
                <span class="verify-title">Independent agent audit</span>
              </header>
              <p>An autonomous agent (<code>{_h(model)}</code>) browsed the live page
              and verified <strong>{summary}</strong> ({passed}/{len(results)} fields)
              against facts.json — the surface is honest, not just claimed.</p>
              {shot}
              <p class="verify-cmd"><code>python tools/holo_audit.py "
            f"--run experiments/{_h(run_id)}</code></p>
            </article>
            """
        )
    else:
        cards.append(
            """
            <article class="verify-card verify-pending">
              <header>
                <span class="verify-badge">PENDING</span>
                <span class="verify-title">Independent agent audit</span>
              </header>
              <p>Run <code>python tools/holo_audit.py --run experiments/&lt;run-id&gt;</code>.</p>
            </article>
            """
        )

    return f"""
    <section class="panel verification-panel">
      <h2>Verification</h2>
      <p class="panel-note">We test our own pipeline — and an independent agent "
      "verifies the surface is honest.</p>
      <div class="verify-grid">{"".join(cards)}</div>
    </section>
    """


def _newsroom_rail(run_dir: Any) -> str:
    """'What the field is saying' — Tavily field research woven into the broadcast."""
    results = data_mod.load_newsroom_research(run_dir)
    if not results:
        return (
            '<p class="muted">Field research pending — run '
            "<code>tools/enrich_newsroom.py</code>.</p>"
        )
    lis = []
    for hit in results[:4]:
        title = _h(hit.get("title", "Untitled"))
        url = _h(hit.get("url", "#"))
        snippet = _h(hit.get("snippet", ""))
        lis.append(
            f'<li><a href="{url}" rel="noopener">{title}</a>'
            f'<span class="lit-snippet">{snippet}</span></li>'
        )
    return '<ul class="lit-list newsroom-list">' + "".join(lis) + "</ul>"


def _entity_rail(items: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    if not items:
        return (
            '<p class="muted">NER pending — run '
            "<code>tools/pioneer_ner.py --train</code> once, then "
            "<code>tools/pioneer_ner.py --run experiments/&lt;run-id&gt;</code>.</p>"
        )

    label_pills = "".join(
        f'<span class="entity-label-pill entity-{_h(label)}">'
        f"{_h(label.replace('_', ' '))} · {count}</span>"
        for label, count in sorted(
            (summary.get("label_totals") or {}).items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    header = (
        f'<div class="entity-summary">'
        f'<span class="entity-stat">{summary["total_entities"]} entities</span>'
        f'<span class="entity-stat">{summary["gene_count"]} genes</span>'
        f"{label_pills}"
        f"</div>"
    )

    blocks = [header]
    for item in items:
        gene = item.get("source_gene", "gene")
        count = item.get("entity_count", 0)
        by_label = item.get("by_label") or {}
        chips = []
        for label, texts in by_label.items():
            for text in texts:
                chips.append(
                    f'<span class="entity-chip entity-{_h(label)}">{_h(text)}'
                    f'<span class="entity-label">{_h(label.replace("_", " "))}</span></span>'
                )
        empty = '<span class="muted">none</span>'
        blocks.append(
            f'<details open><summary>{_h(gene)} <span class="entity-meta">'
            f"{count} entities · {_entity_method_badge(item)}</span></summary>"
            f'<div class="entity-grid">{" ".join(chips) if chips else empty}</div></details>'
        )
    return "".join(blocks)
