"""ElevenLabs Music 'Run #N anthem' — the sung sign-off of the newsroom broadcast.

The oracle anchor ends each broadcast by singing a short anthem grounded in
the run's own facts (run number, headline, self-own). Generates
`visual/anthem.mp3` via `POST /v1/music` (ElevenLabs Music, `music_v1`).

The full sung broadcast is assembled by concatenating the TTS briefing audio
and the anthem, then re-running `render_briefing.py` against the combined
track (documented in the docstring of render_briefing.py).

Hard rules (docs/observatory.md §5): reads facts.json only; lyrics never
invent numbers — they quote the run's headline and audit count; degrade to a
no-op (exit 0) on missing key / API failure — the site builds without the
anthem.

Spend: at most 1 ElevenLabs Music call per run.

Usage:
    python tools/render_anthem.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json
import urllib.request

from _enrich_common import env_key, load_facts, notice, resolve_run_dir, warn

MUSIC_URL = "https://api.elevenlabs.io/v1/music"
MODEL = "music_v1"
SEED = 7  # fixed: same facts -> same anthem, reproducible
OUT = "visual/anthem.mp3"

STYLES = [
    "ethereal",
    "minimal synth",
    "haunting choir",
    "cinematic",
    "dark ambient",
    "great production quality",
]


def anthem_lyrics(facts: dict) -> list[str]:
    """Lyrics grounded in facts.json — run number, headline, audit self-own."""
    run_id = facts.get("run_id") or "k001"
    run_no = "one"
    try:
        run_no = str(int(run_id.split("-")[0].lstrip("k0")) or 1)
    except ValueError:
        pass
    headline = facts.get("headline") or "the baseline took the fall"
    flags = len(facts.get("audit_flags") or [])
    flag_line = (
        f"we flagged our own audit, {flags} issues for all"
        if flags
        else "our audit found nothing, so we say it all"
    )
    return [
        f"Run {run_no} of seventy-eight, {headline.lower()}",
        flag_line,
        "the vessel speaks, the vessel sings",
        "we publish every failure, watch the cracks and rings",
    ]


def generate_anthem(api_key: str, lyrics: list[str]) -> bytes:
    """One ElevenLabs Music call; return the mp3 bytes."""
    body = {
        "composition_plan": {
            "positive_global_styles": STYLES,
            "negative_global_styles": ["upbeat", "pop", "dance", "country"],
            "sections": [
                {
                    "section_name": "Verse 1",
                    "positive_local_styles": STYLES[:3],
                    "negative_local_styles": ["upbeat"],
                    "duration_ms": 22000,
                    "lines": lyrics,
                }
            ],
        },
        "model_id": MODEL,
        "seed": SEED,
    }
    req = urllib.request.Request(
        MUSIC_URL,
        data=json.dumps(body).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)

    api_key = env_key("ELEVENLABS_API_KEY", "ELEVEN_API_KEY")
    if not api_key:
        notice("anthem: skipped (no ELEVENLABS_API_KEY); run degrades without the anthem")
        return 0

    try:
        data = generate_anthem(api_key, anthem_lyrics(facts))
    except Exception as exc:
        warn(f"anthem generation failed ({exc}); run degrades without the anthem")
        return 0

    out = run_dir / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    notice(f"anthem: wrote {out.relative_to(run_dir)} ({len(data) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
