"""Site-wide SEO and social metadata for Observatory pages."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass

SITE_TITLE = "Kytos Observatory"
SITE_TAGLINE = "Virtual Cell Challenge · build in public"
SITE_DESCRIPTION = (
    "Public experiment tracker for Kytos: cell-eval metrics, biological audit flags, "
    "literature evidence, provenance, and VEED Fabric briefings — failure modes visible "
    "during the 2026 Virtual Cell Challenge."
)
SITE_AUTHOR = "Kytos"
THEME_COLOR = "#100e0a"
TWITTER_HANDLE = ""  # optional @handle without @
DEFAULT_OG_IMAGE = "static/og-image.jpg"
FAVICON_PATH = "static/favicon.svg"
APPLE_TOUCH_ICON = "static/apple-touch-icon.png"
MANIFEST_PATH = "static/site.webmanifest"


DEFAULT_SITE_URL = "https://kytosapp.netlify.app"


def site_url() -> str:
    """Canonical site origin, no trailing slash."""
    for key in ("KYTOS_SITE_URL", "SITE_URL", "URL", "DEPLOY_PRIME_URL"):
        value = os.environ.get(key, "").strip().rstrip("/")
        if value:
            return value
    return DEFAULT_SITE_URL


def _abs_url(path: str, *, origin: str) -> str:
    path = path.lstrip("/")
    if not origin:
        return f"/{path}"
    return f"{origin}/{path}"


@dataclass(frozen=True)
class PageMeta:
    title: str
    description: str
    canonical_path: str
    og_type: str = "website"
    og_image: str | None = None
    robots: str = "index, follow"
    # Only run detail pages have the Plotly metrics chart.
    # When False, the Plotly script tag is omitted entirely (saves 1.3 MB).
    needs_plotly: bool = False
    # Home + run detail pages have the 3D vessel; runs index uses SVG only.
    # When False, the Three.js import map and vessel3d.js module are omitted
    # (saves ~270 KB of JS that would never execute).
    needs_vessel: bool = True


def _h(text: str) -> str:
    return html.escape(text, quote=True)


def render_head_tags(meta: PageMeta, *, root_prefix: str) -> str:
    """HTML fragment for <head> — title, icons, description, OG, Twitter, canonical.

    Heavy scripts (Plotly 1.3 MB, Three.js 270 KB) are conditionally included
    only on pages that need them. This is the single biggest performance lever:
    the home page and runs index don't load Plotly at all.
    """
    origin = site_url()
    canonical = _abs_url(meta.canonical_path, origin=origin)
    og_image_rel = meta.og_image or DEFAULT_OG_IMAGE
    if og_image_rel.startswith(("http://", "https://")):
        og_image = og_image_rel
    elif meta.canonical_path not in ("/", "/runs/") and not og_image_rel.startswith("static/"):
        base = meta.canonical_path.rstrip("/")
        og_image = _abs_url(f"{base}/{og_image_rel.lstrip('/')}", origin=origin)
    else:
        og_image = _abs_url(og_image_rel, origin=origin)

    full_title = f"{meta.title} · {SITE_TITLE}"
    icon_href = f"{root_prefix}static/favicon.svg"
    apple_href = f"{root_prefix}static/apple-touch-icon.png"
    manifest_href = f"{root_prefix}static/site.webmanifest"

    twitter_site = ""
    if TWITTER_HANDLE:
        handle = TWITTER_HANDLE.lstrip("@")
        twitter_site = f'\n  <meta name="twitter:site" content="@{_h(handle)}">'

    head = f"""  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(full_title)}</title>
  <meta name="description" content="{_h(meta.description)}">
  <meta name="author" content="{_h(SITE_AUTHOR)}">
  <meta name="robots" content="{_h(meta.robots)}">
  <meta name="theme-color" content="{THEME_COLOR}">
  <link rel="canonical" href="{_h(canonical)}">
  <link rel="icon" href="{_h(icon_href)}" type="image/svg+xml" sizes="any">
  <link rel="apple-touch-icon" href="{_h(apple_href)}" sizes="180x180">
  <link rel="manifest" href="{_h(manifest_href)}">
  <meta property="og:site_name" content="{_h(SITE_TITLE)}">
  <meta property="og:title" content="{_h(full_title)}">
  <meta property="og:description" content="{_h(meta.description)}">
  <meta property="og:type" content="{_h(meta.og_type)}">
  <meta property="og:url" content="{_h(canonical)}">
  <meta property="og:image" content="{_h(og_image)}">
  <meta property="og:image:alt" content="{_h(SITE_TITLE)} — κύτος vessel instrument">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_h(full_title)}">
  <meta name="twitter:description" content="{_h(meta.description)}">
  <meta name="twitter:image" content="{_h(og_image)}">{twitter_site}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&display=swap"
        rel="stylesheet">
  <link rel="stylesheet" href="{root_prefix}static/style.css">"""

    # ── Conditional heavy scripts ──────────────────────────────────────────
    # Plotly is now lazy-loaded by site.js when the chart scrolls into view
    # (saves 1.3 MB of render-blocking JS). No <script> tag needed in <head>.
    #
    # Three.js + vessel3d.js: ~270 KB — home + run detail only (not runs index).
    if meta.needs_vessel:
        head += f"""
  <script type="importmap">
  {{
    "imports": {{
      "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"
    }}
  }}
  </script>
  <script type="module" src="{root_prefix}static/vessel3d.js"></script>"""

    return head


def render_robots_txt() -> str:
    origin = site_url()
    sitemap_line = f"Sitemap: {origin}/sitemap.xml\n" if origin else ""
    return f"""User-agent: *
Allow: /

{sitemap_line}"""


def render_sitemap_xml(paths: list[str]) -> str:
    origin = site_url()
    if not origin:
        origin = "https://example.com"

    urls = "\n".join(
        f"  <url>\n    <loc>{html.escape(origin + path)}</loc>\n  </url>" for path in paths
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
