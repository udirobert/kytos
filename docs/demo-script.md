# Kytos — 2-minute demo script (Loom, hackathon opt-in)

Status: **ACTIVE** · Owner: Dev C (record by 17:30) · Last updated: 2026-08-22

Structure per [`observatory.md §7`](observatory.md#7-demo-script-2-minutes), but
**re-ordered for the self-own**: the demo opens with our own baseline failing
our own audit — credibility before claims. Record against the **live Netlify
URL**; fall back to `python -m http.server 8080 --directory frontend/dist`.

---

## 0:00–0:10 — Hook: the leaderboard lies

> "Virtual cell models score well but fail biologically — and the leaderboard
> only shows numbers. Arc itself says the field needs people who know when a
> model is wrong for *biological* reasons. So we built the thing that catches
> us."

**On screen:** Home page → hero card. Cursor hovers the "Why the Observatory"
panel.

## 0:10–0:35 — The self-own: our vessel confesses

> "This is κύτος — the hollow vessel that fills with evidence. This is our own
> baseline, k001. **It fails our own audit**: housekeeping genes shifted +2.10
> log2FC — past our own threshold. Interferon response is mixed-directional.
> We flagged ourselves. That's the product: every run publishes its failure
> modes, not just its score."

**On screen:** Run detail page. The **vessel instrument** (fill = ceiling
headroom, amber cracks = the two warnings). Click the confession banner →
audit flag cards.

**Demo beat (if Fabric video exists):** let the briefing autoplay for 5–8s
here — "the vessel explains its own run, generated from the same committed
facts, not a script about them."

## 0:35–1:10 — Metrics vs ceiling → drill-down

> "The numbers come from `cell-eval` — nothing here is LLM-generated. Scores
> vs the noise-adjusted ceiling per metric; every headline value links to the
> committed CSV it came from. Click a value — that's the source. The chart, the
> flags, the reproduce command — all trace to committed artifacts."

**On screen:** Metrics vs ceiling Plotly chart (click a metric value → CSV
opens). Scroll: audit flag cards → provenance footer (commit hash, seed,
reproduce commands).

## 1:10–1:35 — Literature + narrative rails (evidence, not decoration)

> "Each flag is grounded: Tavily pulls the literature for the flagged genes —
> auxiliary evidence that degrades empty if the API is down. The narrative
> digest is rendered *from* the facts JSON only — every sentence cites its
> source field. Numbers by code; prose by LLM; never the other way around."

**On screen:** Literature rail (if artifacts landed) → narrative block with
inline citations → pre-registered hypotheses ("we wrote these down before
looking at the leaderboard").

## 1:35–1:50 — The planted-signal proof

> "And the audit audits itself: we plant known-answer perturbations — the
> exact shifts we flagged — and require the rules to catch them. If the audit
> can't catch what we planted, we can't trust it to catch what we didn't."

**On screen:** `python tools/planted_signal.py` in the terminal → PASS/PASS/…
table (fast, scripted).

## 1:50–2:00 — The 78-day closer

> "This is run #1 of 78. The competition runs until November 5 — we're going
> to publish every run, in public, and let you watch us get caught. Critique
> our audit rules and our pre-registered hypotheses on GitHub Discussions.
> This is what 'knowing when a model is wrong' looks like while it's
> happening, not after."

**On screen:** GitHub repo page → Discussions link. Fade to κύτος vessel.

---

## Recording checklist

- [ ] Live URL confirmed (Netlify) — or local server fallback
- [ ] Real artifacts in k001 if available (hero, literature, briefing.mp4) — script holds either way
- [ ] `planted_signal.py` run pre-recorded or scripted live (it's fast)
- [ ] Cursor movements slow and deliberate; no dead air > 2s
- [ ] Mobile check of the URL first (judges may click on phones)
- [ ] Public repo link + Discussions link ready in the description
- [ ] Done by 17:30; upload + submission form by 18:30
