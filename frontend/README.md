# Kytos Observatory — frontend

Static site generator for the build-in-public experiment tracker. Renders from
committed `experiments/*/facts.json` plus `visual/`, `narrative/`, and
`literature/` artifacts — no runtime API calls at view time.

**Plan and UX spec:** [`docs/observatory.md`](../docs/observatory.md)  
**Problem / wedge:** [`docs/competitive-landscape.md`](../docs/competitive-landscape.md)

## Layout (Milestone 0)

Stage layout inspired by [cell-architecture-studio](https://github.com/cclank/cell-architecture-studio)
and [plant-dna](https://github.com/thebuggeddev/plant-dna): run strip, center
stage (κύτος vessel + VEED Fabric briefing), evidence rail (metrics, audit,
literature, narrative, provenance). See observatory doc §3.

## Build & deploy

```bash
python3 frontend/build.py --experiments experiments/ --out frontend/dist/
python3 -m http.server 8080 --directory frontend/dist
```

**Site metadata:** each build emits per-page `<title>`, description, Open Graph /
Twitter cards, canonical URLs, `robots.txt`, and `sitemap.xml`. Static assets live
in `frontend/static/` (`favicon.svg`, `og-image.png`, `apple-touch-icon.png`,
`site.webmanifest`). Set `KYTOS_SITE_URL` (or rely on Netlify's `URL` env var) so
canonical and sitemap links use your production domain.

**Live site:** [kytosapp.netlify.app](https://kytosapp.netlify.app)

1. [Netlify](https://app.netlify.com) → **Add new site** → **Import from Git** → select `udirobert/kytos`
2. Netlify reads `netlify.toml` (build command + `frontend/dist` publish dir) — no dashboard overrides needed
3. Push to `main` → production deploy; other branches get preview URLs if enabled in site settings

Local preview does not trigger Netlify — only pushes to the linked remote do.

Enrichment (run before build):

```bash
python tools/render_narrative.py   --run experiments/<run-id>
python tools/enrich_literature.py  --run experiments/<run-id>
python tools/render_visuals.py     --run experiments/<run-id>
python tools/render_briefing.py    --run experiments/<run-id>
```

**Milestone 0 target (2026-08-22):** Run detail page (P0) with Plotly, Fabric
briefing, OpenAI narrative, Tavily literature rail, Pioneer NER entity chips. Thin Home; defer Runs polish.
