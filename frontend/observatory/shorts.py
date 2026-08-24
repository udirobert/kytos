"""Chronicle shorts — the /shorts/ surface.

A short is a 10–20s clip that is never shipped alone: every clip carries a
plain-words card (rung 2) and a source trail (rung 3) — see
docs/chronicle/context-layer.md. This module loads the chronicle manifest
(docs/chronicle/shorts.json + glossary.json) and renders both the per-short
page and the /shorts/ index.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from frontend.observatory import render as render_mod
from frontend.observatory.meta import PageMeta, SITE_DESCRIPTION, render_head_tags
from frontend.observatory.templates import render_template

CHRONICLE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "chronicle"


@dataclass(frozen=True)
class ChronicleShort:
    slug: str
    title: str
    hook: str
    published: str
    series: str
    plain_words: str
    terms: list[str]
    sources: list[dict[str, str]]
    deep: str
    media: dict[str, str]


@dataclass(frozen=True)
class Chronicle:
    root: Path
    series: str
    shorts: list[ChronicleShort]
    glossary: dict[str, str]  # term -> plain definition


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def _plain_md(text: str) -> str:
    """Minimal markdown for the 'deep science' block (bold + paragraphs)."""
    text = _h(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    paragraphs = [f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip()]
    return "\n".join(paragraphs) or text


def _annotate_terms(text: str, glossary: dict[str, str]) -> str:
    """Wrap glossary terms in <span class=\"term\" data-tip=…> for tooltips."""
    text = _h(text)
    for term in sorted(glossary, key=lambda t: -len(t)):
        definition = _h(glossary[term])
        pattern = rf"(?<!\w)({re.escape(term)})(?!\w)"
        text = re.sub(
            pattern,
            rf'<span class="term" tabindex="0" data-tip="{definition}">\1</span>',
            text,
        )
    return text


def load_chronicle(root: Path | None = None) -> Chronicle:
    """Load shorts.json + glossary.json from a chronicle dir (no file → empty)."""
    root = (root or CHRONICLE_ROOT).resolve()
    glossary: dict[str, str] = {}
    gfile = root / "glossary.json"
    if gfile.is_file():
        raw = json.loads(gfile.read_text(encoding="utf-8"))
        for key, entry in raw.items():
            if isinstance(entry, dict):
                glossary[key] = entry.get("definition", key)
            else:
                glossary[key] = str(entry)

    shorts: list[ChronicleShort] = []
    mfile = root / "shorts.json"
    if mfile.is_file():
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
        series = manifest.get("series", "Chronicle")
        for item in manifest.get("shorts", []):
            shorts.append(
                ChronicleShort(
                    slug=item["slug"],
                    title=item.get("title", ""),
                    hook=item.get("hook", ""),
                    published=item.get("published", ""),
                    series=item.get("series", series),
                    plain_words=item.get("plain_words", ""),
                    terms=item.get("terms", []),
                    sources=item.get("sources", []),
                    deep=item.get("deep", ""),
                    media=item.get("media", {}),
                )
            )
    return Chronicle(root=root, series=series, shorts=shorts, glossary=glossary)


def render_short(
    short: ChronicleShort, chronicle: Chronicle, *, root_prefix: str, js_version: str = ""
) -> str:
    """Render the per-short page (clip + plain words + source)."""
    meta = PageMeta(
        title=short.title,
        description=(short.hook or SITE_DESCRIPTION),
        canonical_path=f"/shorts/{short.slug}/",
        needs_vessel=False,
        needs_plotly=False,
    )
    med = short.media
    plain_html = _annotate_terms(short.plain_words or "", chronicle.glossary)
    glossary_items = [
        {"term": term, "definition": chronicle.glossary.get(term, "")}
        for term in short.terms
        if term in chronicle.glossary
    ]
    context = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-short",
        "root_prefix": root_prefix,
        "js_version": js_version,
        "nav": render_mod._nav("shorts", [], root_prefix=root_prefix),
        "series": short.series,
        "published": short.published,
        "title": short.title,
        "hook": short.hook,
        "video_src": med.get("video", ""),
        "poster_src": med.get("poster", ""),
        "captions_src": med.get("captions", ""),
        "plain_html": plain_html,
        "glossary_items": glossary_items,
        "sources": short.sources,
        "deep_html": _plain_md(short.deep or ""),
        "index_href": f"{root_prefix}index.html",
        "home_href": f"{root_prefix}index.html",
    }
    return render_template("short.html", **context)


def render_shorts_index(chronicle: Chronicle, *, root_prefix: str, js_version: str = "") -> str:
    """Render the /shorts/ index — poster grid of all shorts."""
    meta = PageMeta(
        title="The Chronicle",
        description=(
            "Short field reports from the Virtual Cell Challenge — one idea each, "
            "with plain-words context underneath."
        ),
        canonical_path="/shorts/",
        needs_vessel=False,
        needs_plotly=False,
    )
    cards = []
    for short in chronicle.shorts:
        cards.append(
            {
                "href": f"{short.slug}/index.html",
                "title": short.title,
                "hook": short.hook,
                "series": short.series,
                "published": short.published,
                "poster": f"{short.slug}/{short.media.get('poster', '')}",
            }
        )
    context = {
        "meta": meta,
        "head_tags": render_head_tags(meta, root_prefix=root_prefix),
        "body_class": "page-shorts",
        "root_prefix": root_prefix,
        "js_version": js_version,
        "nav": render_mod._nav("shorts", [], root_prefix=root_prefix),
        "series": chronicle.series,
        "cards": cards,
        "home_href": f"{root_prefix}index.html",
    }
    return render_template("shorts_index.html", **context)
