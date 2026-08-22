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

## Build (once implemented)

```bash
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

Enrichment (run before build):

```bash
python tools/render_narrative.py   --run experiments/<run-id>
python tools/enrich_literature.py  --run experiments/<run-id>
python tools/render_visuals.py     --run experiments/<run-id>
python tools/render_briefing.py    --run experiments/<run-id>
```

**Milestone 0 target (2026-08-22):** Run detail page (P0) with Plotly, Fabric
briefing, OpenAI narrative, Tavily literature rail. Thin Home; defer Runs polish.
