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
        ("About", f"{root_prefix}about/index.html", active == "about"),
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
                The Observatory publishes every run of a {VCC_DAYS}-day public
                experiment: scores, biological audit flags, literature, and
                provenance. Run #{_run_index(latest, runs)} of {VCC_DAYS} is live.
              </p>
              <p class="vessel-legend-inline">
                <span class="legend-item legend-fill">nucleus = ceiling headroom</span>
                <span class="legend-item legend-warn">membrane stress = audit warnings</span>
                <span class="legend-item legend-info">vesicles = info flags</span>
              </p>
              <div class="home-cta-row">
                <a class="button" href="{run_href}">View run #{_run_index(latest, runs)} →</a>
                <a class="home-chip" href="{root_prefix}about/index.html">
                  About the build
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

    body = _nav("home", runs, root_prefix=root_prefix) + stage
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


def _timeline_html() -> str:
    """VCC timeline + hackathon countdown — shared between pages."""
    return f"""
    <section class="panel timeline-panel timeline-centered">
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
            <strong class="vcc-stat-value">
              <span id="vcc-day">…</span><span class="vcc-stat-of">/{VCC_DAYS}</span>
            </strong>
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


def _why_html() -> str:
    """The 'Why the Observatory' essay — shared between pages."""
    return """
    <section class="panel">
      <h2>Why the Observatory</h2>
      <p class="prose">Arc expanded to six metrics because narrow scoring invites optimization
      against the metric, not the biology. We publish every run's scores <em>and</em> biological
      audit flags, literature, and provenance so failure modes are visible while the competition
      runs.</p>
    </section>
    """


def render_about(runs: list[RunSummary], *, root_prefix: str = "") -> str:
    body = (
        _nav("about", runs, root_prefix=root_prefix)
        + '<main class="content about-content">'
        + _timeline_html()
        + _why_html()
        + "</main>"
    )
    meta = PageMeta(
        title="About",
        description=(
            "The Kytos Observatory story — hackathon build, Virtual Cell Challenge "
            "timeline, and why we publish every run's failures in the open."
        ),
        canonical_path="/about/",
    )
    return (
        _head(meta, root_prefix=root_prefix)
        + f'<body class="page-about">{body}</body>'
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
        # Mini SVG vessel on each card — visual identity without WebGL on this page
        mini_svg = _vessel_svg(run.facts, svg_class="vessel-mini")
        cards += f"""
        <a class="run-card" href="{href}">
          <div class="run-card-vessel">{mini_svg}</div>
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

    latest = runs[-1] if runs else None
    if latest:
        header_vessel = _vessel_svg(latest.facts, svg_class="vessel-mini runs-header-vessel")
        run_count = f"{len(runs)} run{'s' if len(runs) != 1 else ''} published"
        header = f"""
        <section class="runs-header">
          <div class="runs-header-vessel-wrap">{header_vessel}</div>
          <h1>Experiment runs</h1>
          <p class="runs-header-sub">
            Metrics, audit flags, and provenance for every experiment — click a card to open.
          </p>
          <p class="runs-header-count">{run_count}</p>
        </section>
        """
    else:
        header = """
        <section class="runs-header">
          <h1>Experiment runs</h1>
          <p class="runs-header-sub muted">Waiting for the first run with facts.json.</p>
        </section>
        """

    body = (
        _nav("runs", runs, root_prefix=root_prefix)
        + header
        + f'<main class="content"><div class="run-grid">{cards}</div></main>'
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

    flags_html = _audit_flags_compact(facts.get("audit_flags") or [])
    hypotheses = facts.get("hypotheses_preregistered") or []
    hyp_html = "".join(f"<li>{_h(item)}</li>" for item in hypotheses)

    narrative = data_mod.load_narrative(run.path)
    narrative_html = (
        (
            f'<div class="narrative-body narrative-compact">'
            f"{data_mod.markdown_to_html(narrative)}</div>"
        )
        if narrative
        else '<p class="muted">Narrative pending — run <code>tools/render_narrative.py</code>.</p>'
    )

    literature = data_mod.load_literature(run.path)
    lit_html = _literature_rail(literature, max_results=2, snippet_chars=120, default_open=False)

    entities = data_mod.load_entity_extractions(run.path)
    entity_summary = data_mod.summarize_entity_extractions(entities)
    entity_html = _entity_rail(
        entities, entity_summary, default_open=False, max_chips=8, compact_summary=True
    )

    prov = facts.get("provenance") or {}
    headline_m = facts.get("headline_metrics") or {}
    headline_c = facts.get("ceiling_headroom") or {}
    csv_href = f"{root_prefix}metrics/agg_results.csv"
    metric_pills = _metric_pills(headline_m, headline_c, csv_href)

    evidence_hint = _evidence_hint(literature, entity_summary)
    evidence_body = f"""
      <div class="evidence-sub">
        <h3 class="evidence-subhead">Per-flag literature</h3>
        <p class="panel-note">Tavily · auxiliary, not scored</p>
        {lit_html}
      </div>
      <div class="evidence-sub">
        <h3 class="evidence-subhead">Field context</h3>
        {_newsroom_rail(run.path, max_results=3, snippet_chars=120)}
      </div>
      <div class="evidence-sub">
        <h3 class="evidence-subhead">Biomedical NER</h3>
        <p class="panel-note">{_entity_panel_note(entity_summary)}</p>
        {entity_html}
      </div>
    """

    trust_body = _verification_section(run.path, run.run_id, embedded=True) + _provenance_block(
        prov, run.run_id
    )

    hyp_list = hyp_html or '<li class="muted">None</li>'
    audit_inner = (
        _run_verdict(facts, run.run_id)
        + flags_html
        + '<div id="metrics-chart" class="chart chart-compact"></div>'
        + f'<script type="application/json" id="metrics-chart-data">{chart_json}</script>'
        + '<details class="hyp-details">'
        + f"<summary>Pre-registered hypotheses ({len(hypotheses)})</summary>"
        + '<ul class="hyp-list">'
        + hyp_list
        + "</ul>"
        + "</details>"
    )

    body = f"""
    {_nav(run.run_id, runs, root_prefix=root_prefix)}
    {
        _run_header_compact(
            run,
            runs,
            facts,
            visual,
            vd,
            entity_summary,
            metric_pills,
            root_prefix=root_prefix,
        )
    }
    <main class="run-evidence">
      {
        _disclosure_section(
            "Audit & metrics",
            _audit_summary(facts),
            audit_inner,
            open_default=True,
            section_id="audit",
        )
    }
      {
        _disclosure_section(
            "Evidence",
            evidence_hint,
            evidence_body,
            open_default=False,
            section_id="evidence",
        )
    }
      {
        _disclosure_section(
            "Narrative digest",
            _narrative_label(narrative),
            narrative_html,
            open_default=False,
            section_id="narrative",
        )
    }
      {
        _disclosure_section(
            "Trust & provenance",
            "Self-tests + reproduce command",
            trust_body,
            open_default=False,
            section_id="trust",
        )
    }
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
        needs_vessel=False,
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
          <span class="briefing-stamp">kytos newsroom · run #1 of 78 · the cell speaks</span>
          <button class="briefing-unmute" type="button" hidden
                  aria-label="Unmute the cell briefing">♪ unmute — the cell sings</button>
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
    # Membrane stress marks (audit warnings) on the cell's edge
    cracks = "".join(
        f'<path class="vessel-crack" d="M {72 + i * 12} {150 + (i % 3) * 14} l {10 + i} {26 + i}"/>'
        for i in range(min(warns, 6))
    )
    # Vesicles (info flags) floating in the cytoplasm
    droplets = "".join(
        f'<circle class="vessel-info" cx="{55 + i * 22}" cy="{46 + (i % 2) * 28}" r="3"/>'
        for i in range(min(infos, 5))
    )
    # The instrument: the vessel silhouette that holds the cell
    glass_path = (
        "M 80 12 L 120 12 L 120 58 Q 120 92 156 132 Q 188 168 172 208"
        " Q 158 240 100 240 Q 42 240 28 208 Q 12 168 44 132 Q 80 92 80 58 Z"
    )
    # The subject: the cell inside the vessel — nucleus = headroom, cytoplasm
    # = the rising liquid, membrane = the vessel's inner wall.
    cell_cy = 132
    cell_r = 62
    nucleus_r = max(10, int(cell_r * fill / 100))  # nucleus grows with headroom
    nucleus_cx, nucleus_cy = 100, 150
    nucleus = f'<circle class="cell-nucleus" cx="{nucleus_cx}" cy="{nucleus_cy}" r="{nucleus_r}"/>'
    cell = (
        f'<circle class="cell-membrane" cx="{cell_cy}" cy="{cell_cy}" r="{cell_r}"/>'
        f'<circle class="cell-membrane" cx="{cell_cy}" cy="{cell_cy}" r="{cell_r - 4}"/>'
        f"{nucleus}"
    )

    return f"""
      <svg class="{svg_class}" viewBox="0 0 200 250" role="img"
           aria-label="Kytos cell instrument: nucleus fill {fill} percent, {warns} audit warnings">
        <defs>
          <clipPath id="{clip_id}">
            <path d="{glass_path}"/>
          </clipPath>
        </defs>
        <path class="vessel-glass" d="{glass_path}"/>
        <rect class="vessel-liquid" x="10" y="{fill_y}" width="180" height="250"
              clip-path="url(#{clip_id})"/>
        <line class="vessel-liquid-line" x1="30" y1="{fill_y}" x2="170" y2="{fill_y}"/>
        <g class="cell-subject">{cell}</g>
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
      <p class="vessel-label">κύτος · the instrument that shows when the model is wrong</p>
      <p class="vessel-legend">
        <span class="legend-item legend-fill">nucleus = {fill}% ceiling headroom</span>
        <span class="legend-item legend-warn">{warns} {warn_plural}</span>
        <span class="legend-item legend-info">{infos} info {info_plural}</span>
      </p>
    </div>
    """


def _disclosure_section(
    title: str,
    hint: str,
    body: str,
    *,
    open_default: bool = False,
    section_id: str | None = None,
) -> str:
    """Progressive disclosure panel — one section, collapsed by default unless asked."""
    open_attr = " open" if open_default else ""
    id_attr = f' id="{_h(section_id)}"' if section_id else ""
    return f"""
    <details class="disclosure-panel"{id_attr}{open_attr}>
      <summary class="disclosure-summary">
        <span class="disclosure-title">{_h(title)}</span>
        <span class="disclosure-hint">{hint}</span>
      </summary>
      <div class="disclosure-body">{body}</div>
    </details>
    """


def _metric_pills(headline_m: dict[str, Any], headline_c: dict[str, Any], csv_href: str) -> str:
    if not headline_m:
        return ""
    pills = []
    for key in headline_m:
        pills.append(
            f'<span class="metric-pill">'
            f"{_h(key)} "
            f'<a class="metric-src" href="{csv_href}" title="opens metrics CSV">'
            f"<strong>{_h(str(headline_m.get(key, '—')))}</strong></a> "
            f'<span class="metric-ceiling">/ {_h(str(headline_c.get(key, "—")))}</span>'
            f"</span>"
        )
    return "".join(pills)


def _audit_summary(facts: dict) -> str:
    flags = facts.get("audit_flags") or []
    warns = sum(1 for f in flags if f.get("severity") in ("warn", "error"))
    metrics = facts.get("headline_metrics") or {}
    metric_bits = ", ".join(f"{k} {v}" for k, v in list(metrics.items())[:2])
    parts = []
    if warns:
        parts.append(f"{warns} audit warn{'s' if warns != 1 else ''}")
    if metric_bits:
        parts.append(metric_bits)
    return " · ".join(parts) if parts else "Scores from committed CSVs"


def _evidence_hint(literature: list[dict], entity_summary: dict) -> str:
    gene_n = len(literature)
    ent_n = entity_summary.get("total_entities") or 0
    if gene_n and ent_n:
        return f"{gene_n} genes · {ent_n} entities · Tavily + Pioneer"
    if gene_n:
        return f"{gene_n} genes · Tavily literature"
    return "Literature & entity enrichment"


def _run_verdict(facts: dict, run_id: str) -> str:
    flags = facts.get("audit_flags") or []
    warns = [f for f in flags if f.get("severity") in ("warn", "error")]
    if not warns:
        return ""
    rules = ", ".join(_h(f.get("rule", "?")) for f in warns[:3])
    return (
        f'<p class="run-verdict">'
        f"<strong>{len(warns)} warning(s)</strong> on this run ({rules}) — "
        f"we publish our own failures. "
        f"<code>python -m kytos.audit --run experiments/{_h(run_id)}</code>"
        f"</p>"
    )


def _run_header_compact(
    run: RunSummary,
    runs: list[RunSummary],
    facts: dict,
    visual: dict,
    vd: dict,
    entity_summary: dict,
    metric_pills: str,
    *,
    root_prefix: str,
) -> str:
    media = _run_header_media(visual, facts)
    jk = '<span class="jk-hint">j/k · switch runs</span>' if len(runs) > 1 else ""
    entity_strip = ""
    if entity_summary.get("total_entities"):
        entity_strip = f"""
          <span class="data-strip-sep"></span>
          <span class="data-strip-item">
            <span class="data-strip-label">entities</span>
            {_count_span("data-strip-value", entity_summary["total_entities"])}
          </span>"""
    return f"""
    <header class="run-header">
      <nav class="breadcrumb">
        <a href="{root_prefix}runs/index.html">← All runs</a>
        {jk}
      </nav>
      <div class="run-header-grid">
        <div class="run-header-copy">
          <p class="eyebrow">
            Run #{_run_index(run, runs)} of {VCC_DAYS} · {_h(facts.get("created", ""))}
          </p>
          <h1 class="run-header-title">{_h(facts.get("headline", run.run_id))}</h1>
          <div class="metric-pills">{metric_pills}</div>
          <div class="run-hero-strip run-header-strip">
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
            {entity_strip}
          </div>
        </div>
        {media}
      </div>
    </header>
    """


def _run_header_media(visual: dict, facts: dict) -> str:
    briefing = visual.get("briefing")
    hero = visual.get("hero")
    if briefing:
        poster = f' poster="{_h(hero)}"' if hero else ""
        return f"""
        <div class="run-header-media">
          <video class="briefing-video briefing-video-compact" src="{_h(briefing)}"
                 autoplay muted loop playsinline controls preload="none"{poster}></video>
          <span class="briefing-stamp briefing-stamp-compact">newsroom briefing</span>
          <button class="briefing-unmute" type="button" hidden
                  aria-label="Unmute briefing">♪ unmute</button>
        </div>"""
    if hero:
        return f"""
        <div class="run-header-media">
          <img class="run-header-thumb" src="{_h(hero)}" alt="Run visual">
        </div>"""
    return f"""
        <div class="run-header-media run-header-vessel-wrap">
          {_vessel_svg(facts, svg_class="vessel-mini run-header-vessel")}
        </div>"""


def _provenance_block(prov: dict, run_id: str) -> str:
    return f"""
    <footer class="provenance provenance-compact">
      <dl>
        <dt>commit</dt><dd><code>{_h(str(prov.get("commit", "")))}</code></dd>
        <dt>seed</dt><dd>{_h(str(prov.get("seed", "")))}</dd>
        <dt>code_hash</dt><dd><code>{_h(str(prov.get("code_hash", "")))}</code></dd>
      </dl>
      <p class="reproduce">Reproduce:
      <code id="reproduce-cmd">python -m kytos.audit --run experiments/{_h(run_id)}
      &amp;&amp; python -m kytos.eval.facts --run experiments/{_h(run_id)}</code>
      <button class="copy-btn" type="button" data-copy="#reproduce-cmd">copy</button></p>
    </footer>
    """


def _audit_flags_compact(flags: list[dict[str, Any]]) -> str:
    if not flags:
        return '<p class="muted">No audit flags.</p>'
    badge = {"warn": "!", "error": "✕", "info": "i"}
    rows = []
    for flag in flags:
        genes = ", ".join(flag.get("genes") or [])
        severity = flag.get("severity", "info")
        msg = flag.get("message", "")
        if len(msg) > 120:
            msg = msg[:117] + "…"
        rows.append(
            f'<li class="flag-row severity-{_h(severity)}">'
            f'<span class="flag-badge">{badge.get(severity, "i")}</span>'
            f'<span class="flag-row-rule">{_h(flag.get("rule", ""))}</span>'
            f'<span class="flag-row-msg">{_h(msg)}</span>'
            f'<span class="flag-row-genes">{_h(genes)}</span>'
            f"</li>"
        )
    return f'<ul class="flag-list-compact">{"".join(rows)}</ul>'


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


def _literature_rail(
    items: list[dict[str, Any]],
    *,
    max_results: int = 5,
    snippet_chars: int = 200,
    default_open: bool = True,
) -> str:
    if not items:
        return (
            '<p class="muted">Literature pending — run <code>tools/enrich_literature.py</code>.</p>'
        )
    open_attr = " open" if default_open else ""
    blocks = []
    for item in items:
        flag_id = item.get("flag_id", "flag")
        results = item.get("results") or []
        if not results:
            blocks.append(f"<p class='muted'>No results for {_h(str(flag_id))}.</p>")
            continue
        lis = []
        total = len(results)
        for hit in results[:max_results]:
            title = _h(hit.get("title", "Untitled"))
            url = _h(hit.get("url", "#"))
            snippet = _h((hit.get("snippet") or "")[:snippet_chars])
            if len(hit.get("snippet") or "") > snippet_chars:
                snippet += "…"
            lis.append(
                f'<li><a href="{url}" rel="noopener">{title}</a>'
                f'<span class="lit-snippet">{snippet}</span></li>'
            )
        more = (
            f'<li class="muted lit-more">+ {total - max_results} more source(s)</li>'
            if total > max_results
            else ""
        )
        blocks.append(
            f"<details{open_attr}><summary>{_h(str(flag_id))}"
            f'<span class="lit-count">{min(max_results, total)}/{total}</span></summary>'
            f"<ul class='lit-list'>{''.join(lis)}{more}</ul></details>"
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


def _verification_section(run_dir: Any, run_id: str, *, embedded: bool = False) -> str:
    """The trust layer: planted-signal + Holo agent audit cards."""
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

    grid = f'<div class="verify-grid">{"".join(cards)}</div>'
    if embedded:
        return f'<div class="verification-embedded">{grid}</div>'
    return f"""
    <section class="panel verification-panel">
      <h2>Verification</h2>
      <p class="panel-note">We test our own pipeline — and an independent agent "
      "verifies the surface is honest.</p>
      {grid}
    </section>
    """


def _newsroom_rail(
    run_dir: Any,
    *,
    max_results: int = 4,
    snippet_chars: int = 200,
) -> str:
    """Tavily field research woven into the newsroom broadcast."""
    results = data_mod.load_newsroom_research(run_dir)
    if not results:
        return (
            '<p class="muted">Field research pending — run '
            "<code>tools/enrich_newsroom.py</code>.</p>"
        )
    lis = []
    for hit in results[:max_results]:
        title = _h(hit.get("title", "Untitled"))
        url = _h(hit.get("url", "#"))
        snippet = _h((hit.get("snippet") or "")[:snippet_chars])
        if len(hit.get("snippet") or "") > snippet_chars:
            snippet += "…"
        lis.append(
            f'<li><a href="{url}" rel="noopener">{title}</a>'
            f'<span class="lit-snippet">{snippet}</span></li>'
        )
    more = (
        f'<li class="muted lit-more">+ {len(results) - max_results} more</li>'
        if len(results) > max_results
        else ""
    )
    return '<ul class="lit-list newsroom-list">' + "".join(lis) + more + "</ul>"


def _entity_rail(
    items: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    default_open: bool = True,
    max_chips: int = 24,
    compact_summary: bool = False,
) -> str:
    if not items:
        return (
            '<p class="muted">NER pending — run '
            "<code>tools/pioneer_ner.py --train</code> once, then "
            "<code>tools/pioneer_ner.py --run experiments/&lt;run-id&gt;</code>.</p>"
        )

    open_attr = " open" if default_open else ""
    label_pills = ""
    if not compact_summary:
        label_pills = "".join(
            f'<span class="entity-label-pill entity-{_h(label)}">'
            f"{_h(label.replace('_', ' '))} · {count}</span>"
            for label, count in sorted(
                (summary.get("label_totals") or {}).items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
    header = (
        f'<div class="entity-summary{" entity-summary-compact" if compact_summary else ""}">'
        f'<span class="entity-stat">{summary["total_entities"]} entities</span>'
        f'<span class="entity-stat">{summary["gene_count"]} genes</span>'
        f"{label_pills}"
        f"</div>"
    )

    blocks = [header] if summary.get("gene_count") else []
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
        shown = chips[:max_chips]
        extra = len(chips) - len(shown)
        extra_html = f'<span class="entity-more muted">+ {extra} more</span>' if extra > 0 else ""
        empty = '<span class="muted">none</span>'
        blocks.append(
            f'<details{open_attr}><summary>{_h(gene)} <span class="entity-meta">'
            f"{count} entities · {_entity_method_badge(item)}</span></summary>"
            f'<div class="entity-grid">'
            f"{' '.join(shown) if shown else empty}{extra_html}</div></details>"
        )
    return (
        "".join(blocks)
        if blocks
        else ('<p class="muted">NER pending — run <code>tools/pioneer_ner.py --run …</code>.</p>')
    )
