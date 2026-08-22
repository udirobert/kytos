"""HTML rendering for Observatory pages."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from frontend.observatory import data as data_mod
from frontend.observatory.charts import metrics_bar_chart
from frontend.observatory.meta import PageMeta, SITE_DESCRIPTION, render_head_tags
from frontend.observatory.runs import RunSummary
from frontend.observatory.templates import render_template

SITE_TITLE = "Kytos Observatory"

# The 78-day public build (Aug 20 → Nov 5). The demo's closer — "run #1 of 78"
# — is stamped on the surface so the long-game story survives a silent scroll.
VCC_DAYS = 78
VCC_START = "2026-08-20T00:00:00Z"
VCC_TEST_SET = "2026-10-22T00:00:00Z"
VCC_END = "2026-11-05T23:59:59Z"
HACKATHON_END = "2026-08-22T18:00:00Z"  # 19:00 London (BST) opt-in deadline

# Display names for cell-eval metric keys (full key kept in title/tooltip).
METRIC_LABELS: dict[str, str] = {
    "DESigGenesRecall": "DE gene recall",
    "pearson_delta": "Pearson Δ",
    "mse": "MSE",
    "mae": "MAE",
}


# First-visit vessel onboarding tooltip — shared by home + run detail.
_VESSEL_ONBOARD_HTML = """\
        <div class="vessel-onboard" id="vessel-onboard" hidden>
          <p>This is the κύτος vessel — <strong>liquid fill</strong> = how much room
          our prediction has to improve, <strong>amber cracks</strong> = where our
          audit caught us failing.</p>
          <p class="vessel-onboard-hint">Drag to rotate · click the cracks to see
          what went wrong</p>
          <button class="vessel-onboard-close" type="button"
                  aria-label="Dismiss">Got it</button>
        </div>
"""


def _metric_label(key: str) -> str:
    if key in METRIC_LABELS:
        return METRIC_LABELS[key]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    return spaced.replace("_", " ")


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def _run_index(run: RunSummary, runs: list[RunSummary]) -> int:
    """1-based position of a run in the published sequence (for the #N of 78 stamp)."""
    try:
        return runs.index(run) + 1
    except ValueError:
        return len(runs)


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


def _prepare_narrative_markdown(text: str) -> str:
    """Drop audit/hypothesis sections already shown in other panels.

    Also strips LLM-generated debug annotations like ``(facts: key.path)``
    that leak JSON key paths into user-facing prose.
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        lower = stripped.lower()
        if re.match(r"^#{2,3}\s+audit", lower):
            i += 1
            while i < len(lines) and not re.match(r"^#{1,3}\s", lines[i].strip()):
                i += 1
            continue
        if re.match(r"^#{2,3}\s+hypothes", lower):
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if re.match(r"^#{1,3}\s", s):
                    break
                if not s:
                    i += 1
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    cleaned = "\n".join(out).strip()
    # Remove LLM debug annotations: (facts: ...) or (facts: key.path)
    cleaned = re.sub(r"\s*\(facts:\s*[^)]*\)", "", cleaned)
    return cleaned


def _narrative_display_html(narrative: str | None) -> str:
    if not narrative:
        return (
            '<p class="muted">Narrative pending — run <code>tools/render_narrative.py</code>.</p>'
        )
    cleaned = _prepare_narrative_markdown(narrative)
    full = data_mod.markdown_to_html(cleaned)
    match = re.search(r"(<p>.*?</p>)", full, re.DOTALL | re.IGNORECASE)
    if not match:
        return f'<div class="narrative-body narrative-compact">{full}</div>'
    lead = match.group(1)
    rest = full[match.end() :].strip()
    if not rest:
        return f'<div class="narrative-body narrative-lead">{lead}</div>'
    return (
        f'<div class="narrative-body narrative-lead">{lead}</div>'
        f'<details class="narrative-more">'
        f"<summary>Full digest</summary>"
        f'<div class="narrative-rest">{rest}</div>'
        f"</details>"
    )


def _gene_evidence_slug(gene: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", gene.strip()).strip("-").lower()
    return slug or "gene"


def _gene_links_html(genes: list[str]) -> str:
    if not genes:
        return ""
    links = []
    for gene in genes:
        slug = _gene_evidence_slug(gene)
        links.append(
            f'<a class="gene-evidence-link" href="#evidence-gene-{_h(slug)}" '
            f'data-gene="{_h(gene)}">#{_h(gene)}</a>'
        )
    return " ".join(links)


def _card_metrics_summary(metrics: dict[str, Any], limit: int = 2) -> str:
    if not metrics:
        return "—"
    items = list(metrics.items())
    head = ", ".join(f"{_metric_label(k)} {v}" for k, v in items[:limit])
    extra = len(items) - limit
    if extra > 0:
        head += f" +{extra} more"
    return head


def _run_card_delta(run: RunSummary, prev: RunSummary | None) -> str:
    """Delta vs prior run on the first shared headline metric (when n ≥ 2)."""
    if not prev:
        return ""
    curr_m = run.facts.get("headline_metrics") or {}
    prev_m = prev.facts.get("headline_metrics") or {}
    for key, val in curr_m.items():
        if key not in prev_m:
            continue
        delta = float(val) - float(prev_m[key])
        sign = "+" if delta >= 0 else ""
        return (
            f'<span class="run-card-delta">'
            f"{sign}{delta:.2f} {_h(_metric_label(key))} vs prior</span>"
        )
    return ""


def _evidence_block(title: str, hint: str, body: str) -> str:
    """Flat evidence section — no nested accordion inside the Evidence panel."""
    return f"""
    <section class="evidence-block">
      <header class="evidence-block-header">
        <h3 class="evidence-block-title">{_h(title)}</h3>
        <span class="disclosure-hint">{_h(hint)}</span>
      </header>
      <div class="evidence-block-body">{body}</div>
    </section>
    """


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


# Data-status labels for non-final metrics. meta.json declares data_status
# (e.g. "probe" for mock/placeholder values); without this the Observatory
# would present mock numbers as if they were real cell-eval output.
_DATA_STATUS_LABELS: dict[str, str] = {
    "probe": "probe · mock data",
    "mock": "mock data",
    "draft": "draft · unverified",
}


def _data_status_badge(facts: dict, meta: dict | None = None) -> str:
    """Small badge that distinguishes placeholder metrics from real cell-eval output.

    ``data_status`` is declared in ``meta.json`` (not ``facts.json``), so this
    reads ``meta`` first and falls back to ``facts`` for compatibility. Returns
    "" when data_status is absent or 'final' — honest by default: the badge only
    appears when the run's own meta/facts admit it is not real.
    """
    status = ""
    if meta:
        status = str(meta.get("data_status") or "").strip().lower()
    if not status:
        status = str(facts.get("data_status") or "").strip().lower()
    if not status or status == "final":
        return ""
    label = _DATA_STATUS_LABELS.get(status, f"{status} · unverified")
    title = "Metrics are placeholders, not real cell-eval output"
    return (
        f'<span class="data-status-badge" title="{_h(title)}" '
        f'data-status="{_h(status)}">{_h(label)}</span>'
    )


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
    strip_block = ""
    if len(runs) > 1:
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
        strip_block = f'<div class="run-strip">{strip}</div>'
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
    {strip_block}
    """


def _head(meta: PageMeta, *, root_prefix: str) -> str:
    html_class = "vessel-pending" if meta.needs_vessel else ""
    return f"""<!DOCTYPE html>
<html lang="en" class="{html_class}">
<head>
{render_head_tags(meta, root_prefix=root_prefix)}
</head>
"""


def _home_proof_pill(facts: dict, meta: dict | None = None) -> str:
    """One-line live stat from the latest run — optional social proof on the hero."""
    flags = facts.get("audit_flags") or []
    warns = sum(1 for f in flags if f.get("severity") in ("warn", "error"))
    metrics = facts.get("headline_metrics") or {}
    parts: list[str] = []
    badge = _data_status_badge(facts, meta)
    if badge:
        parts.append(badge)
    if warns:
        parts.append(f"{warns} audit warning{'s' if warns != 1 else ''}")
    if metrics:
        key, val = next(iter(metrics.items()))
        parts.append(f"{_metric_label(key)} {val}")
    if not parts:
        return ""
    # The badge is already-safe HTML; the text parts need escaping separately
    # so the join doesn't pass raw markup through _h() (which would escape the
    # badge's own tags into visible &lt;span&gt; text).
    escaped: list[str] = []
    for part in parts:
        if part.startswith("<"):
            escaped.append(part)
        else:
            escaped.append(_h(part))
    return f'<p class="home-proof">{" · ".join(escaped)}</p>'


def _bio_atmosphere(*, variant: str = "stage", density: str = "light") -> str:
    """Shared biological motif layer inspired by specimen plates and DNA studies.

    It stays behind content and uses static SVG geometry so the same visual language
    works on Home, Runs, and run detail without another runtime dependency.
    """
    density_class = f" bio-atmosphere-{density}"
    helix_left = (
        "M22 0 C118 70 118 140 22 210 C-8 232 -8 278 22 300 "
        "C118 370 118 440 22 510 C10 520 8 540 22 560"
    )
    helix_right = (
        "M118 0 C22 70 22 140 118 210 C148 232 148 278 118 300 "
        "C22 370 22 440 118 510 C130 520 132 540 118 560"
    )
    helix_bars = (
        "M42 42 L98 42 M30 112 L110 112 M26 182 L114 182 "
        "M42 252 L98 252 M26 322 L114 322 M30 392 L110 392 "
        "M42 462 L98 462 M26 532 L114 532"
    )
    vein_branches = (
        "M130 204 C120 150 90 112 36 74 M178 154 C188 110 212 76 266 36 "
        "M232 128 C278 124 314 142 352 184"
    )
    return f"""
      <div class="bio-atmosphere bio-atmosphere-{_h(variant)}{density_class}" aria-hidden="true">
        <svg class="bio-helix" viewBox="0 0 140 560" preserveAspectRatio="none">
          <path d="{helix_left}"/>
          <path d="{helix_right}"/>
          <path d="{helix_bars}"/>
        </svg>
        <svg class="bio-veins" viewBox="0 0 420 300" preserveAspectRatio="none">
          <path d="M0 266 C88 242 128 202 178 154 C222 112 268 82 420 38"/>
          <path d="{vein_branches}"/>
          <ellipse cx="70" cy="100" rx="38" ry="13" transform="rotate(30 70 100)"/>
          <ellipse cx="224" cy="72" rx="42" ry="14" transform="rotate(-32 224 72)"/>
          <ellipse cx="326" cy="151" rx="44" ry="14" transform="rotate(28 326 151)"/>
        </svg>
        <span class="bio-organelle bio-organelle-a"></span>
        <span class="bio-organelle bio-organelle-b"></span>
        <span class="bio-organelle bio-organelle-c"></span>
        <span class="bio-membrane bio-membrane-a"></span>
        <span class="bio-membrane bio-membrane-b"></span>
      </div>
    """


def _home_vessel_legend_html(vd: dict[str, Any], *, about_href: str) -> str:
    warn_word = "warning" if vd["warns"] == 1 else "warnings"
    info_word = "flag" if vd["infos"] == 1 else "flags"
    parts = [
        f'<span class="legend-item legend-fill">{vd["fill_pct"]}% headroom</span>',
        f'<span class="legend-item legend-warn">{vd["warns"]} audit {warn_word}</span>',
    ]
    if vd["infos"]:
        parts.append(f'<span class="legend-item legend-info">{vd["infos"]} info {info_word}</span>')
    return (
        f'<p class="home-vessel-legend vessel-legend-inline">{"".join(parts)}</p>'
        f'<p class="home-vessel-about-link">'
        f'<a href="{_h(about_href)}">What is the vessel?</a></p>'
    )


def render_home(runs: list[RunSummary], *, root_prefix: str = "") -> str:
    meta = PageMeta(
        title="Home",
        description=SITE_DESCRIPTION,
        canonical_path="/",
    )
    latest = runs[-1] if runs else None
    context: dict[str, Any] = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-home",
        "root_prefix": root_prefix,
        "nav": _nav("home", runs, root_prefix=root_prefix),
        "latest": latest is not None,
    }
    if latest:
        run_href = f"{root_prefix}runs/{_h(latest.run_id)}/index.html"
        vd = _vessel_data(latest.facts)
        vessel_json = json.dumps(vd)
        svg = _vessel_svg(latest.facts, clip_id="vessel-clip-home")

        run_index = _run_index(latest, runs)
        proof = _home_proof_pill(latest.facts, latest.meta)
        about_href = f"{root_prefix}about/index.html"
        vessel_legend = _home_vessel_legend_html(vd, about_href=about_href)
        visual = latest.facts.get("visual") or {}
        hero = visual.get("hero")
        presenter = visual.get("presenter")
        hero_img = ""
        if hero:
            hero_src = f"{root_prefix}runs/{_h(latest.run_id)}/{_h(hero)}"
            hero_img = (
                f'<img class="home-vessel-bg" src="{_h(hero_src)}" alt="" '
                f'decoding="async" loading="eager">'
            )

        # Dr. Kytos presenter background for home page
        presenter_bg = ""
        if presenter:
            presenter_src = f"{root_prefix}runs/{_h(latest.run_id)}/{_h(presenter)}"
            presenter_bg = f"""
            <div class="home-presenter-bg">
              <video class="home-presenter-video" src="{_h(presenter_src)}"
                     autoplay muted loop playsinline preload="auto"></video>
            </div>
            """

        context.update(
            {
                "bio_atmosphere": _bio_atmosphere(variant="home", density="light"),
                "presenter_bg": presenter_bg,
                "hero_img": hero_img,
                "svg": svg,
                "vessel_onboard_html": _VESSEL_ONBOARD_HTML,
                "vessel_json": vessel_json,
                "vessel_legend": vessel_legend,
                "run_index": run_index,
                "vcc_days": VCC_DAYS,
                "proof": proof,
                "run_href": run_href,
                "about_href": about_href,
            }
        )

    return render_template("home.html", **context)


def _timeline_html() -> str:
    """VCC timeline + hackathon countdown — shared between pages."""
    return f"""
    <section class="panel timeline-panel timeline-centered">
      <div class="timeline-hackathon">
        <p class="timeline-eyebrow">🏆 VEED Summer Lock-In · Aug 2026</p>
        <h2>{{Tech: Europe}} × VEED Hackathon</h2>
        <p class="timeline-tagline">
          Observatory Milestone 0 — the public transparency layer for our Virtual Cell
          Challenge entry, shipping from this repo through Nov 5.
        </p>
        <p class="hackathon-deadline">
          Opt-in closed <strong id="hackathon-countdown" class="t-text-swap">…</strong>
          <span class="muted">· we keep building in public</span>
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
            <strong class="vcc-stat-value t-text-swap" id="vcc-countdown">…</strong>
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


def _vessel_about_panel(runs: list[RunSummary]) -> str:
    """Explain the κύτος vessel metaphor — moved off home when hero slimmed down."""
    latest = runs[-1] if runs else None
    if not latest:
        return ""
    vd = _vessel_data(latest.facts)
    svg = _vessel_svg(latest.facts, svg_class="vessel-mini about-vessel")
    warn_word = "warning" if vd["warns"] == 1 else "warnings"
    info_word = "flag" if vd["infos"] == 1 else "flags"
    return f"""
    <section class="panel vessel-about-panel">
      <h2>The vessel</h2>
      <div class="vessel-about-grid">
        <div class="vessel-about-art" aria-hidden="true">{svg}</div>
        <div class="vessel-about-copy">
          <p class="prose">The κύτος vessel is a live readout of each run&rsquo;s health —
          not decoration. Fill level tracks ceiling headroom; membrane stress and vesicles
          map to audit severity.</p>
          <p class="vessel-legend-inline">
            <span class="legend-item legend-fill">nucleus · {vd["fill_pct"]}% headroom</span>
            <span class="legend-item legend-warn">membrane · {vd["warns"]} audit {warn_word}</span>
            <span class="legend-item legend-info">vesicles · {vd["infos"]} info {info_word}</span>
          </p>
        </div>
      </div>
    </section>
    """


def _run_card_metrics_line(run: RunSummary) -> str:
    """Human-readable run card metrics: ceiling % and audit warns."""
    return _metrics_line_from_facts(run.facts)


def _metrics_line_from_facts(facts: dict) -> str:
    metrics = facts.get("headline_metrics") or {}
    ceilings = facts.get("ceiling_headroom") or {}
    parts: list[str] = []
    for key, val in list(metrics.items())[:2]:
        label = _metric_label(key)
        ceil = ceilings.get(key)
        if ceil is not None and float(ceil) > 0:
            pct = int(round(100 * float(val) / float(ceil)))
            parts.append(f"{label} {pct}% ceiling")
        else:
            parts.append(f"{label} {val}")
    warns = sum(1 for f in facts.get("audit_flags") or [] if f.get("severity") in ("warn", "error"))
    if warns:
        parts.append(f"{warns} audit warn{'s' if warns != 1 else ''}")
    extra = len(metrics) - 2
    if extra > 0:
        parts.append(f"+{extra} more")
    return " · ".join(parts) if parts else "—"


def _insight_card(
    eyebrow: str,
    title: str,
    body: str,
    *,
    foot: str = "",
    href: str | None = None,
) -> str:
    """Non-clickable context card on the runs index while the grid is sparse."""
    tag = "a" if href else "div"
    href_attr = f' href="{_h(href)}"' if href else ""
    foot_html = f'<span class="run-insight-foot">{_h(foot)}</span>' if foot else ""
    return f"""
    <{tag} class="run-card run-insight-card"{href_attr}>
      <span class="run-insight-eyebrow">{_h(eyebrow)}</span>
      <span class="run-insight-title">{_h(title)}</span>
      <span class="run-insight-body">{body}</span>
      {foot_html}
    </{tag}>
    """


def _runs_insight_cards(runs: list[RunSummary], *, root_prefix: str = "../") -> str:
    """Fill the runs grid with substantiation until enough real runs exist."""
    n = len(runs)
    if n >= 4:
        return ""
    about = f"{root_prefix}about/index.html#substantiation"
    cards = [
        _insight_card(
            "Virtual Cell Challenge",
            "Six metrics in 2026",
            "Arc expanded scoring because <strong>no single metric captures model quality</strong> "
            "and narrow leaderboards invite optimization against the score — not the biology.",
            foot="5,000+ registrants · 114 countries in 2025",
            href=about,
        ),
        _insight_card(
            "Arc Institute",
            "Biological vs numerical",
            "The 2026 challenge calls for people who know when a model is wrong for "
            "<strong>biological rather than numerical reasons</strong>. "
            "Rankings alone don't show that.",
            foot="Official scores stay in cell-eval — we add audit + provenance",
            href=about,
        ),
        _insight_card(
            "Kytos Observatory",
            "What we publish per run",
            "<strong>cell-eval metrics</strong> and ceiling headroom, "
            "<strong>audit flags</strong> (separate from score), "
            "literature, provenance, and briefings — for all "
            f"<strong>{VCC_DAYS} days</strong> of the public build.",
            foot="Run #1 of 78 is live",
            href=f"{root_prefix}index.html" if runs else None,
        ),
    ]
    if n == 1:
        run = runs[0]
        line = _run_card_metrics_line(run)
        cards.insert(
            0,
            _insight_card(
                "Run snapshot",
                "Why scores aren't enough",
                f"Our first baseline scores well on paper but fails its own audit rules — "
                f"<strong>{_h(line)}</strong>. "
                f"That tension is the point.",
                foot="Open the run → confession banner → gene evidence",
                href=f"{_h(run.run_id)}/index.html",
            ),
        )
    return "".join(cards[: max(0, 4 - n)])


def _substantiation_about_html(runs: list[RunSummary]) -> str:
    """Evidence-backed 'Why the Observatory' — stats without wall-of-citations."""
    k001_line = ""
    if runs:
        line = _run_card_metrics_line(runs[-1])
        k001_line = f"""
        <p class="substantiation-live prose">
          <strong>Live example (run #{_run_index(runs[-1], runs)}):</strong> {_h(line)} —
          plus audit flags the headline metrics never name.
        </p>"""
    return f"""
    <section class="panel substantiation-panel" id="substantiation">
      <h2>Why the Observatory</h2>
      <p class="prose">The Virtual Cell Challenge produces high-dimensional predictions
      and leaderboard scores. It does not publish <em>when a model is biologically wrong
      while still scoring acceptably</em>. We do — run by run, in the open, for the full
      competition window.</p>

      <div class="evidence-strip">
        <div class="evidence-stat">
          <span class="evidence-stat-value">6</span>
          <span class="evidence-stat-label">scored metrics in 2026</span>
          <span class="evidence-stat-note">Arc aggregate — 0 = mean baseline, 1 = replicate</span>
        </div>
        <div class="evidence-stat">
          <span class="evidence-stat-value">5k+</span>
          <span class="evidence-stat-label">VCC 2025 registrants</span>
          <span class="evidence-stat-note">114 countries · 300+ final teams</span>
        </div>
        <div class="evidence-stat">
          <span class="evidence-stat-value">{VCC_DAYS}</span>
          <span class="evidence-stat-label">days public build</span>
          <span class="evidence-stat-note">Aug 20 → Nov 5, 2026</span>
        </div>
      </div>

      {k001_line}

      <div class="substantiation-grid">
        <div class="substantiation-col">
          <h3 class="substantiation-subhead">Official infrastructure</h3>
          <ul class="substantiation-list">
            <li>Leaderboard + <code>cell-eval</code> six-metric scoring</li>
            <li>Zero-shot across six unseen cell contexts (2026)</li>
            <li>High-quality Perturb-seq ground truth (~1k cells / perturbation)</li>
          </ul>
        </div>
        <div class="substantiation-col">
          <h3 class="substantiation-subhead">Observatory adds</h3>
          <ul class="substantiation-list">
            <li>Ceiling headroom (% of best achievable per metric)</li>
            <li>Biological audit flags <em>separate from</em> score</li>
            <li>Literature + NER + provenance + reproduce commands</li>
          </ul>
        </div>
      </div>

      <details class="sources-details">
        <summary>Sources &amp; further reading</summary>
        <ul class="sources-list">
          <li><a href="https://arcinstitute.org/news/virtual-cell-challenge-2026" rel="noopener">
              Arc — Virtual Cell Challenge 2026</a> (six metrics, biological vs numerical)</li>
          <li><a href="https://arcinstitute.org/news/virtual-cell-challenge-2025-wrap-up"
              rel="noopener">
              Arc — 2025 wrap-up</a> (5,000+ registrants, Generalist Prize)</li>
          <li><a href="https://pypi.org/project/cell-eval2/" rel="noopener">
              cell-eval2</a> (2026 metric scale 0–1)</li>
          <li><a href="https://www.nature.com/articles/s41592-025-02772-6" rel="noopener">
              Nature Methods 2025</a> — perturbation models vs linear baselines</li>
          <li>Repo: <code>docs/substantiation.md</code> (maintainer crib sheet)</li>
        </ul>
      </details>
    </section>
    """


def render_about(runs: list[RunSummary], *, root_prefix: str = "") -> str:
    meta = PageMeta(
        title="About",
        description=(
            "The Kytos Observatory story — hackathon build, Virtual Cell Challenge "
            "timeline, and why we publish every run's failures in the open."
        ),
        canonical_path="/about/",
    )
    context = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-about",
        "root_prefix": root_prefix,
        "nav": _nav("about", runs, root_prefix=root_prefix),
        "timeline_html": _timeline_html(),
        "vessel_about_panel": _vessel_about_panel(runs),
        "substantiation_about_html": _substantiation_about_html(runs),
    }
    return render_template("about.html", **context)


def render_runs_index(runs: list[RunSummary], *, root_prefix: str = "../") -> str:
    cards = ""
    for run in reversed(runs):
        href = f"{_h(run.run_id)}/index.html"
        m = _run_card_metrics_line(run)
        severity = _run_severity(run.facts)
        vd = _vessel_data(run.facts)
        chron = list(runs)
        run_pos = chron.index(run)
        prev = chron[run_pos - 1] if run_pos > 0 else None
        delta = _run_card_delta(run, prev)
        mini_svg = _vessel_svg(run.facts, svg_class="vessel-mini")
        status_badge = _data_status_badge(run.facts, run.meta)
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
          {status_badge}
          {delta}
        </a>
        """

    latest = runs[-1] if runs else None
    if latest:
        header_vessel = _vessel_svg(latest.facts, svg_class="vessel-mini runs-header-vessel")
        run_count = f"{len(runs)} run{'s' if len(runs) != 1 else ''} published"
        header = f"""
        <section class="runs-header">
          {_bio_atmosphere(variant="archive", density="light")}
          <div class="runs-header-vessel-wrap">{header_vessel}</div>
          <h1>Experiment runs</h1>
          <p class="runs-header-sub">
            Metrics, ceiling headroom, and audit flags for every experiment.
            Insight cards fill the grid until more runs ship.
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

    insight_cards = _runs_insight_cards(runs, root_prefix=root_prefix)
    matrix = _runs_comparison_matrix(runs, root_prefix=root_prefix)
    meta = PageMeta(
        title="Runs",
        description=(
            "Index of Kytos experiment runs with cell-eval metrics, audit flags, and provenance."
        ),
        canonical_path="/runs/",
        needs_vessel=False,
    )
    context = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-runs",
        "root_prefix": root_prefix,
        "nav": _nav("runs", runs, root_prefix=root_prefix),
        "header": header,
        "matrix": matrix,
        "cards": cards,
        "insight_cards": insight_cards,
    }
    return render_template("runs_index.html", **context)


def _runs_comparison_matrix(runs: list[RunSummary], *, root_prefix: str = "../") -> str:
    """Render a cross-experiment scorecard table comparing all runs."""
    if not runs:
        return ""
    rows: list[dict[str, Any]] = []
    for run in runs:
        facts = run.facts
        meta = run.meta
        href = f"{_h(run.run_id)}/index.html"
        severity = _run_severity(facts)
        vd = _vessel_data(facts)
        status_badge = _data_status_badge(facts, meta)
        strategy = (
            meta.get("strategy") or facts.get("provenance", {}).get("strategy") or "mean-shift"
        )

        metrics = facts.get("headline_metrics") or {}
        recall = metrics.get("DESigGenesRecall")
        recall_str = f"{float(recall):.3f}" if recall is not None else "—"

        pearson = metrics.get("pearson_delta")
        pearson_str = f"{float(pearson):.3f}" if pearson is not None else "—"

        flags = facts.get("audit_flags") or []
        warns = sum(1 for f in flags if f.get("severity") in ("warn", "error"))
        info = sum(1 for f in flags if f.get("severity") == "info")

        if warns > 0:
            audit_badge = f'<span class="audit-badge audit-badge-warn">{warns} warn</span>'
        elif info > 0:
            audit_badge = f'<span class="audit-badge audit-badge-info">{info} info</span>'
        else:
            audit_badge = '<span class="audit-badge audit-badge-pass">clean</span>'

        rows.append(
            {
                "run_id": run.run_id,
                "href": href,
                "severity": severity,
                "strategy": strategy,
                "status_badge": status_badge,
                "fill_pct": vd["fill_pct"],
                "recall_str": recall_str,
                "pearson_str": pearson_str,
                "audit_badge": audit_badge,
            }
        )

    return render_template("components/matrix.html", rows=rows)


def _evidence_journey() -> str:
    """Run-detail navigation rail: one route through the evidence."""
    steps = [
        {
            "id": "audit",
            "number": "01",
            "title": "Audit",
            "hint": "stress detected",
            "accent": "amber",
        },
        {
            "id": "evidence",
            "number": "02",
            "title": "Evidence",
            "hint": "field context",
            "accent": "teal",
        },
        {
            "id": "narrative",
            "number": "03",
            "title": "Digest",
            "hint": "grounded account",
            "accent": "violet",
        },
        {
            "id": "trust",
            "number": "04",
            "title": "Trust",
            "hint": "reproduce + verify",
            "accent": "cyan",
        },
    ]
    return render_template("components/journey.html", steps=steps)


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
    narrative_html = _narrative_display_html(narrative)

    literature = data_mod.load_literature(run.path)
    lit_html = _literature_rail(literature, max_results=2, snippet_chars=120, default_open=False)

    entities = data_mod.load_entity_extractions(run.path)
    entity_summary = data_mod.summarize_entity_extractions(entities)
    entity_html = _entity_rail(
        entities, entity_summary, default_open=False, max_chips=8, compact_summary=True
    )

    prov = facts.get("provenance") or {}
    headline_m = facts.get("headline_metrics") or {}
    # Metrics CSVs ship next to the run page (build.py copies run/metrics/
    # to runs/<run-id>/metrics/) — link relative to the run page, not the
    # site root, or the score link 404s.
    csv_href = "metrics/agg_results.csv"
    score_line = _run_score_line(facts, csv_href)

    evidence_hint = _evidence_hint(literature, entity_summary)
    lit_count = len(literature)
    evidence_body = (
        _evidence_block(
            "Literature",
            f"{lit_count} gene{'s' if lit_count != 1 else ''}",
            f'<p class="panel-note">Tavily · auxiliary, not scored</p>{lit_html}',
        )
        + _evidence_block(
            "Field context",
            "VCC / perturbation research",
            _newsroom_rail(run.path, max_results=3, snippet_chars=120),
        )
        + _evidence_block(
            "Biomedical NER",
            f"{entity_summary.get('total_entities', 0)} entities",
            f'<p class="panel-note">{_entity_panel_note(entity_summary)}</p>{entity_html}',
        )
    )

    trust_body = _verification_section(run.path, run.run_id, embedded=True) + _provenance_block(
        prov, run.run_id
    )

    hyp_list = hyp_html or '<li class="muted">None</li>'
    audit_inner = (
        flags_html
        + '<details class="chart-details">'
        + "<summary>Metrics chart (all scores vs ceiling)</summary>"
        + '<div id="metrics-chart" class="chart chart-compact"></div>'
        + f'<script type="application/json" id="metrics-chart-data">{chart_json}</script>'
        + "</details>"
        + '<details class="hyp-details">'
        + f"<summary>Pre-registered hypotheses ({len(hypotheses)})</summary>"
        + '<ul class="hyp-list">'
        + hyp_list
        + "</ul>"
        + "</details>"
    )

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
        needs_vessel=True,
    )

    context = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-run",
        "root_prefix": root_prefix,
        "bio_atmosphere": _bio_atmosphere(variant="detail", density="light"),
        "vessel_svg": _vessel_svg(facts, clip_id="vessel-clip-run"),
        "vessel_json": json.dumps(vd),
        "presenter_overlay": (
            _presenter_overlay(run, root_prefix, visual) if visual.get("presenter") else ""
        ),
        "nav": _nav(run.run_id, runs, root_prefix=root_prefix),
        "confession_banner": _confession_banner(facts, run.run_id),
        "run_header": _run_header_compact(
            run,
            runs,
            facts,
            visual,
            score_line,
            root_prefix=root_prefix,
        ),
        "evidence_journey": _evidence_journey(),
        "panel_audit": _disclosure_section(
            "Audit & metrics",
            _audit_summary(facts),
            audit_inner,
            open_default=True,
            section_id="audit",
            accent="amber",
        ),
        "panel_evidence": _disclosure_section(
            "Evidence",
            evidence_hint,
            evidence_body,
            open_default=False,
            section_id="evidence",
            accent="teal",
        ),
        "panel_narrative": _disclosure_section(
            "Narrative digest",
            _narrative_label(narrative),
            narrative_html,
            open_default=False,
            section_id="narrative",
            accent="violet",
        ),
        "panel_trust": _disclosure_section(
            "Trust & provenance",
            "Self-tests + reproduce command",
            trust_body,
            open_default=False,
            section_id="trust",
            accent="cyan",
        ),
    }

    return render_template("run_detail.html", **context)


def _presenter_overlay(run: RunSummary, root_prefix: str, visual: dict) -> str:
    """Dr. Kytos presenter video overlay for the run detail hero."""
    presenter_path = visual.get("presenter", "")
    src = f"{_h(root_prefix)}runs/{_h(run.run_id)}/{_h(presenter_path)}"
    return f"""
    <div class="run-hero-presenter">
      <video class="run-hero-presenter-video" src="{src}"
             autoplay muted loop playsinline preload="auto"></video>
      <div class="run-hero-presenter-badge">KYTOS OBSERVATORY · BIOLOGICAL FIELD REPORT</div>
    </div>
    """


def _stage_hero(visual: dict[str, Any], media_prefix: str, facts: dict) -> str:
    """Full-bleed hero for the run detail page.

    Priority: Dr. Kytos presenter video > briefing video > hero image > 3D
    vessel.  The presenter frames the run as a broadcast from the biological
    accountability desk — a named correspondent who contextualises findings.
    Each variant fills the viewport as a background layer.
    """
    presenter = visual.get("presenter")
    briefing = visual.get("briefing")
    hero = visual.get("hero")
    # facts.json visual paths are run-relative and already include the
    # `visual/` dir (run-protocol schema) — build.py copies the run's visual/
    # next to the page, so the facts value IS the correct src.
    if presenter:
        src = _h(presenter)
        poster = f"{_h(hero)}" if hero else ""
        return f"""
        <div class="hero-fullscreen hero-presenter">
          <video class="presenter-video" src="{src}" autoplay muted loop playsinline
                 controls poster="{poster}" preload="none"></video>
          <div class="presenter-overlay">
            <span class="presenter-badge">KYTOS OBSERVATORY · BIOLOGICAL FIELD REPORT</span>
            <span class="presenter-stamp">correspondent · Dr. Kytos</span>
          </div>
        </div>
        """
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
    """Extract the data that drives the 3D vessel from facts.json.

    The vessel is an interactive instrument — organelles link to metrics,
    cracks link to audit flags. We pass the structured data so the 3D scene
    can wire up click handlers and hover callouts.
    """
    ceiling = facts.get("ceiling_headroom") or {}
    metrics = facts.get("headline_metrics") or {}
    values = [float(v) for v in ceiling.values() if isinstance(v, (int, float))]
    fill = int(round(100 * sum(values) / len(values))) if values else 0
    fill = max(6, min(100, fill))
    flags = facts.get("audit_flags") or []
    warn_flags = [f for f in flags if f.get("severity") in ("warn", "error")]
    info_flags = [f for f in flags if f.get("severity") == "info"]

    # Organelles map to headline metrics — each gets a label + target element
    organelle_metrics = []
    metric_items = list(metrics.items())[:6]  # max 6 organelles
    for name, value in metric_items:
        ceiling_val = ceiling.get(name)
        organelle_metrics.append(
            {
                "label": f"{name}: {value:.2f}",
                "ceiling": f"/ {ceiling_val:.2f}" if isinstance(ceiling_val, (int, float)) else "",
                "target": "audit",  # scroll to the audit panel
            }
        )

    # Cracks map to audit flags — each links to its flag in the audit panel
    crack_flags = []
    for fl in warn_flags[:6]:
        crack_flags.append(
            {
                "rule": fl.get("rule", "audit"),
                "message": fl.get("message", ""),
                "target": "audit",
            }
        )

    return {
        "fill_pct": fill,
        "warns": len(warn_flags),
        "infos": len(info_flags),
        "metrics": organelle_metrics,
        "cracks": crack_flags,
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
    accent: str = "",
) -> str:
    """Progressive disclosure panel — one section, collapsed by default unless asked.

    The accent class ties each panel to a part of the 3D vessel:
    audit=amber (cracks), evidence=teal (organelles), trust=cyan (nucleus).
    """
    open_attr = " open" if open_default else ""
    id_attr = f' id="{_h(section_id)}"' if section_id else ""
    accent_attr = f' data-accent="{_h(accent)}"' if accent else ""
    return f"""
    <details class="disclosure-panel"{id_attr}{open_attr}{accent_attr}>
      <summary class="disclosure-summary">
        <span class="disclosure-title">{_h(title)}</span>
        <span class="disclosure-hint">{hint}</span>
        <span class="disclosure-icon t-icon-swap">
          <span class="t-icon" data-icon="closed">+</span>
          <span class="t-icon" data-icon="open">−</span>
        </span>
      </summary>
      <div class="disclosure-body">{body}</div>
    </details>
    """


def _run_score_line(facts: dict, csv_href: str) -> str:
    """Single hero score surface: % ceiling + audit warns (links to metrics CSV)."""
    line = _metrics_line_from_facts(facts)
    if not line or line == "—":
        return ""
    return (
        f'<p class="run-score-line">'
        f'<a class="run-score-link" href="{_h(csv_href)}" title="Open metrics CSV">'
        f"{_h(line)}</a></p>"
    )


def _audit_summary(facts: dict) -> str:
    return _metrics_line_from_facts(facts) or "Scores from committed CSVs"


def _evidence_hint(literature: list[dict], entity_summary: dict) -> str:
    gene_n = len(literature)
    ent_n = entity_summary.get("total_entities") or 0
    if gene_n and ent_n:
        return f"{gene_n} genes · {ent_n} entities · Tavily + Pioneer"
    if gene_n:
        return f"{gene_n} genes · Tavily literature"
    return "Literature & entity enrichment"


def _run_header_compact(
    run: RunSummary,
    runs: list[RunSummary],
    facts: dict,
    visual: dict,
    score_line: str,
    *,
    root_prefix: str,
) -> str:
    media = _run_header_media(visual, facts)
    jk = '<span class="jk-hint">j/k · switch runs</span>' if len(runs) > 1 else ""
    status_badge = _data_status_badge(facts, run.meta)
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
          {status_badge}
          {score_line}
        </div>
        {media}
      </div>
    </header>
    """


def _run_header_media(visual: dict, facts: dict) -> str:
    bulletin = visual.get("bulletin")
    briefing = visual.get("briefing")
    hero = visual.get("hero")
    media = bulletin or briefing
    if media:
        poster = f' poster="{_h(hero)}"' if hero else ""
        is_bulletin = bool(bulletin)
        media_class = "run-header-media-bulletin" if is_bulletin else "run-header-media-briefing"
        label = "8s run bulletin" if is_bulletin else "full broadcast"
        kicker = "RUN BULLETIN" if is_bulletin else "FULL BROADCAST"
        metrics = facts.get("headline_metrics") or {}
        ceilings = facts.get("ceiling_headroom") or {}
        score = "score pending"
        for key, value in list(metrics.items())[:1]:
            ceiling = ceilings.get(key)
            score = (
                f"{round(100 * float(value) / float(ceiling))}%"
                if ceiling not in (None, 0)
                else str(value)
            )
        audit_gene = next(
            (gene for flag in facts.get("audit_flags") or [] for gene in flag.get("genes") or []),
            "audit",
        )
        return f"""
        <div class="run-header-media run-header-media-video {media_class}">
          <div class="bulletin-bio-lines" aria-hidden="true"></div>
          <div class="bulletin-orbit bulletin-orbit-a" aria-hidden="true"></div>
          <div class="bulletin-orbit bulletin-orbit-b" aria-hidden="true"></div>
          <video class="briefing-video briefing-video-compact" src="{_h(media)}"
                 muted playsinline preload="metadata"{poster}></video>
          <div class="bulletin-overlay" aria-hidden="true">
            <span class="bulletin-kicker">{kicker}</span>
            <span class="bulletin-run">KYTOS · {_h(str(facts.get("run_id", "run")).upper())}</span>
            <span class="bulletin-state">AUDIT ACTIVE</span>
          </div>
          <div class="bulletin-data-rail" aria-label="Run bulletin facts">
            <span><strong>{_h(score)} ceiling</strong></span>
            <span><strong>{_h(str(audit_gene))}</strong> flagged</span>
          </div>
          <button class="briefing-play" type="button" aria-label="Play {label}">
            <span aria-hidden="true">▶</span> {label}
          </button>
          <button class="bulletin-next" type="button" data-bulletin-target="audit">
            <span aria-hidden="true">↓</span> inspect audit
          </button>
          <span class="briefing-stamp briefing-stamp-compact">{label}</span>
          <button class="briefing-unmute" type="button" hidden
                  aria-label="Unmute bulletin">♪ unmute</button>
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
      <button class="copy-btn" type="button" data-copy="#reproduce-cmd"
              data-copy-label="copy" aria-label="Copy reproduce command">copy</button></p>
    </footer>
    """


def _audit_flags_compact(flags: list[dict[str, Any]]) -> str:
    if not flags:
        return '<p class="muted">No audit flags.</p>'
    badge = {"warn": "!", "error": "✕", "info": "i"}
    rows = []
    for flag in flags:
        genes_html = _gene_links_html(flag.get("genes") or [])
        severity = flag.get("severity", "info")
        msg = flag.get("message", "")
        if len(msg) > 120:
            msg = msg[:117] + "…"
        rows.append(
            f'<li class="flag-row severity-{_h(severity)}">'
            f'<span class="flag-badge">{badge.get(severity, "i")}</span>'
            f'<span class="flag-row-rule">{_h(flag.get("rule", ""))}</span>'
            f'<span class="flag-row-msg">{_h(msg)}</span>'
            f'<span class="flag-row-genes">{genes_html}</span>'
            f"</li>"
        )
    return f'<ul class="flag-list-compact">{"".join(rows)}</ul>'


def _confession_banner(facts: dict, run_id: str) -> str:
    """Self-own moment: our own run violating our own rules is the demo opener."""
    del run_id  # reproduce lives in Trust panel; keep banner copy short
    flags = facts.get("audit_flags") or []
    warns = [f for f in flags if f.get("severity") in ("warn", "error")]
    if not warns:
        return ""
    rules = ", ".join(f"<code>{_h(f.get('rule', '?'))}</code>" for f in warns[:3])
    return f"""
    <div class="confession-banner">
      <p class="eyebrow">Audit confession — this run fails its own rules</p>
      <p>{len(warns)} warning(s) on our published baseline: {rules}.</p>
    </div>
    """


def _clean_snippet(text: str) -> str:
    """Strip markdown/scrape residue from Tavily snippets for display.

    Raw search results arrive with markdown headers (``####``), stray table
    pipes, image/link syntax, and emphasis markers — none of which render in
    our plain-text cards, so they read as noise in an evidence panel whose
    entire job is trust.
    """
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # images
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)  # links → link text
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # markdown headers
    text = re.sub(r"[*_~`]+", "", text)  # emphasis / code markers
    text = re.sub(r"\|", " ", text)  # stray table pipes
    return re.sub(r"\s+", " ", text).strip(" -#")


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
        # Dedupe repeated sources (search APIs regularly return the same page
        # with different snippets) before slicing to max_results.
        seen_titles: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for hit in results:
            key = re.sub(r"\s+", " ", (hit.get("title") or "").strip().lower()) or hit.get("url")
            if key in seen_titles:
                continue
            seen_titles.add(key)
            deduped.append(hit)
        results = deduped
        lis = []
        total = len(results)
        for hit in results[:max_results]:
            # Titles keep pipes ("… | eLife") — they are real separators;
            # snippets get the full residue scrub.
            clean_title = re.sub(r"[*_~`]+", "", hit.get("title") or "")
            clean_title = re.sub(r"\s+", " ", clean_title).strip(" -#")
            clean_snip = _clean_snippet(hit.get("snippet") or "")
            title = _h(clean_title or "Untitled")
            url = _h(hit.get("url", "#"))
            snippet = _h(clean_snip[:snippet_chars])
            if len(clean_snip) > snippet_chars:
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
            f'<details{open_attr} data-evidence-gene="{_h(str(flag_id))}" '
            f'class="evidence-gene-block evidence-gene-lit">'
            f"<summary>{_h(str(flag_id))}"
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
    """The trust layer: planted-signal, Holo agent audit, narrative grounding cards."""
    planted = data_mod.load_planted_signal(run_dir)
    holo = data_mod.load_holo_audit(run_dir)
    narrative_check = data_mod.load_narrative_check(run_dir)
    holo_shot = "holo_screenshot.png"

    cards = []

    if planted:
        ok = planted.get("status") == "pass"
        summary = planted.get("summary") or "—"
        cases = planted.get("cases") or []
        passed = sum(1 for c in cases if c.get("ok"))
        badge = "PASS" if ok else "FAIL"
        card_class = "verify-pass" if ok else "verify-fail"
        body = (
            f"<p>We plant known-answer failures through our own audit rules. If it "
            f"can't catch what we planted, it can't be trusted to catch what we "
            f"didn't. <strong>{_h(summary)}</strong> ({passed}/{len(cases)} cases).</p>"
            f'<p class="verify-cmd"><code>python tools/planted_signal.py</code></p>'
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact {card_class}">'
                f"<summary>"
                f'<span class="verify-badge">{badge}</span>'
                f'<span class="verify-title">Planted-signal self-test</span>'
                f'<span class="verify-compact-hint">{_h(summary)} · {passed}/{len(cases)}</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{body}</div>'
                f"</details>"
            )
        else:
            cards.append(
                f"""
            <article class="verify-card {card_class}">
              <header>
                <span class="verify-badge">{badge}</span>
                <span class="verify-title">Planted-signal self-test</span>
              </header>
              {body}
            </article>
            """
            )
    else:
        pending = (
            "<p>Run <code>python tools/planted_signal.py --json "
            "…/verification/planted_signal.json</code>.</p>"
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact verify-pending">'
                f"<summary>"
                f'<span class="verify-badge">PENDING</span>'
                f'<span class="verify-title">Planted-signal self-test</span>'
                f'<span class="verify-compact-hint">not run yet</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{pending}</div>'
                f"</details>"
            )
        else:
            cards.append(
                """
            <article class="verify-card verify-pending">
              <header>
                <span class="verify-badge">PENDING</span>
                <span class="verify-title">Planted-signal self-test</span>
              </header>
              """
                + pending
                + """
            </article>
            """
            )

    if holo:
        ok = holo.get("status") == "pass"
        model = holo.get("model") or "h/web-surfer-flash"
        summary = holo.get("summary") or "—"
        results = holo.get("results") or []
        passed = sum(1 for r in results if r.get("ok"))
        badge = "PASS" if ok else "FAIL"
        card_class = "verify-pass" if ok else "verify-fail"
        shot = (
            f'<img class="verify-shot" src="{_h(holo_shot)}" '
            f'alt="Holo agent screenshot of the live run page">'
            if (run_dir / holo_shot).is_file()
            else ""
        )
        body = (
            f"<p>An autonomous agent (<code>{_h(model)}</code>) browsed the live page "
            f"and verified <strong>{_h(summary)}</strong> ({passed}/{len(results)} fields) "
            f"against facts.json — the surface is honest, not just claimed.</p>"
            f"{shot}"
            f'<p class="verify-cmd"><code>python tools/holo_audit.py '
            f"--run experiments/{_h(run_id)}</code></p>"
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact {card_class}">'
                f"<summary>"
                f'<span class="verify-badge">{badge}</span>'
                f'<span class="verify-title">Independent agent audit</span>'
                f'<span class="verify-compact-hint">{_h(summary)} · {passed}/{len(results)}</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{body}</div>'
                f"</details>"
            )
        else:
            cards.append(
                f"""
            <article class="verify-card {card_class}">
              <header>
                <span class="verify-badge">{badge}</span>
                <span class="verify-title">Independent agent audit</span>
              </header>
              {body}
            </article>
            """
            )
    else:
        pending = (
            "<p>Run <code>python tools/holo_audit.py --run experiments/&lt;run-id&gt;</code>.</p>"
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact verify-pending">'
                f"<summary>"
                f'<span class="verify-badge">PENDING</span>'
                f'<span class="verify-title">Independent agent audit</span>'
                f'<span class="verify-compact-hint">not run yet</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{pending}</div>'
                f"</details>"
            )
        else:
            cards.append(
                """
            <article class="verify-card verify-pending">
              <header>
                <span class="verify-badge">PENDING</span>
                <span class="verify-title">Independent agent audit</span>
              </header>
              """
                + pending
                + """
            </article>
            """
            )

    if narrative_check and narrative_check.get("status") != "skip":
        ok = narrative_check.get("status") == "pass"
        summary = narrative_check.get("summary") or "—"
        cases = narrative_check.get("cases") or []
        passed = sum(1 for c in cases if c.get("ok"))
        badge = "PASS" if ok else "FAIL"
        card_class = "verify-pass" if ok else "verify-fail"
        body = (
            f"<p>The LLM digest is grounded by construction: every number in it must "
            f"trace back to facts.json, verified deterministically. "
            f"<strong>{_h(summary)}</strong> ({passed}/{len(cases)} checks).</p>"
            f'<p class="verify-cmd"><code>python tools/check_narrative.py '
            f"--run experiments/{_h(run_id)}</code></p>"
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact {card_class}">'
                f"<summary>"
                f'<span class="verify-badge">{badge}</span>'
                f'<span class="verify-title">Narrative grounding check</span>'
                f'<span class="verify-compact-hint">{_h(summary)} · {passed}/{len(cases)}</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{body}</div>'
                f"</details>"
            )
        else:
            cards.append(
                f"""
            <article class="verify-card {card_class}">
              <header>
                <span class="verify-badge">{badge}</span>
                <span class="verify-title">Narrative grounding check</span>
              </header>
              {body}
            </article>
            """
            )
    else:
        pending = (
            "<p>Run <code>python tools/check_narrative.py --run experiments/&lt;run-id&gt;</code> "
            "after the digest is generated.</p>"
        )
        if embedded:
            cards.append(
                f'<details class="verify-compact verify-pending">'
                f"<summary>"
                f'<span class="verify-badge">PENDING</span>'
                f'<span class="verify-title">Narrative grounding check</span>'
                f'<span class="verify-compact-hint">not run yet</span>'
                f"</summary>"
                f'<div class="verify-compact-body">{pending}</div>'
                f"</details>"
            )
        else:
            cards.append(
                """
            <article class="verify-card verify-pending">
              <header>
                <span class="verify-badge">PENDING</span>
                <span class="verify-title">Narrative grounding check</span>
              </header>
              """
                + pending
                + """
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
            f'<details{open_attr} data-evidence-gene="{_h(gene)}" '
            f'class="evidence-gene-block evidence-gene-ner">'
            f"<summary>{_h(gene)} <span class='entity-meta'>"
            f"{count} entities · {_entity_method_badge(item)}</span></summary>"
            f'<div class="entity-grid">'
            f"{' '.join(shown) if shown else empty}{extra_html}</div></details>"
        )
    return (
        "".join(blocks)
        if blocks
        else ('<p class="muted">NER pending — run <code>tools/pioneer_ner.py --run …</code>.</p>')
    )
