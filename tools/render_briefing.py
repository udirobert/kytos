"""VEED Fabric run briefing — hero image + TTS audio -> talking video (fal).

The demo centerpiece (docs/observatory.md §2): `fal veed/fabric-1.0` turns a
committed hero still + a narrated audio track into `visual/briefing.mp4`.

Pipeline:
  1. script  — derived from committed `narrative/report.md` (fallback digest
               works too), so the spoken words trace to facts.json fields
  2. audio   — OpenAI TTS (tts-1) -> `visual/briefing-audio.mp3`
  3. video   — fal `veed/fabric-1.0` (image_url + audio_url) -> `visual/briefing.mp4`
  4. paths   — `facts.json` -> `visual.briefing` updated on success

Degrades to a no-op (exit 0) at any step — the site builds without the video.
Requires `visual/hero.png` (run `render_visuals.py` first) as the source frame.

Spend: 1 TTS call + 1 Fabric call per run (~$0.08/s at 480p; a ~45 s briefing
≈ $3.60). Resolution via --resolution (480p default, 720p costs ~2x).

Usage:
    python tools/render_briefing.py --run experiments/k001-mean-shift-baseline [--resolution 720p]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _enrich_common import (
    download,
    env_key,
    load_facts,
    media_committable,
    notice,
    openai_tts_client,
    record_pipeline_status,
    resolve_run_dir,
    set_visual_paths,
    warn,
)

FABRIC_MODEL = "veed/fabric-1.0"
TTS_MODEL = "tts-1"
TTS_VOICE = "onyx"
MAX_SCRIPT_CHARS = 950  # ≈ 70 s of speech — bounds video length and spend


def strip_markdown(text: str) -> str:
    """Crude markdown -> plain speech text (drops comments, fences, markup)."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("<!--") or s.startswith("```"):
            continue
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # links -> label text
        s = re.sub(r"[#>*_`]", "", s)
        s = re.sub(r"\|", " ", s)  # table pipes -> spaces
        if s:
            lines.append(s)
    return " ".join(lines).strip()


def briefing_script(run_dir: Path, facts: dict) -> str:
    """Spoken script traced to committed artifacts; fallback to facts fields.

    Prefers the newsroom broadcast script (newsroom/script.md) when present,
    else the LLM narrative digest (narrative/report.md).
    """
    for candidate in ("newsroom/script.md", "narrative/report.md"):
        report = run_dir / candidate
        if report.exists():
            text = strip_markdown(report.read_text())
            break
    else:
        metrics = facts.get("headline_metrics") or {}
        summary = ", ".join(f"{k} {v}" for k, v in metrics.items()) or "no metrics yet"
        text = (
            f"{facts.get('headline', 'Kytos run briefing.')} "
            f"Headline metrics: {summary}. "
            f"Audit flags: {len(facts.get('audit_flags') or [])}. "
            f"Run {facts.get('run_id', '')}."
        )
    text = text[:MAX_SCRIPT_CHARS]
    return text or "Kytos run briefing."


def tts_audio(script: str) -> bytes:
    client = openai_tts_client()
    response = client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=script)
    content = response.content
    if not content:
        raise RuntimeError("OpenAI TTS returned empty audio")
    return content


def fabric_video(image_path: Path, audio_path: Path, resolution: str) -> str:
    import fal_client  # lazy: partner client is optional

    fal_client.api_key = env_key("FAL_KEY", "FAL_API_KEY")
    image_url = fal_client.upload_file(str(image_path))
    audio_url = fal_client.upload_file(str(audio_path))
    # Input keys per fal docs for veed/fabric-1.0 (image_url, audio_url, resolution).
    result = fal_client.subscribe(
        FABRIC_MODEL,
        arguments={"image_url": image_url, "audio_url": audio_url, "resolution": resolution},
    )
    try:
        url = result["video"]["url"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"unexpected fal response shape: {result}") from exc
    if not url:
        raise RuntimeError("Fabric returned no video url")
    return url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    parser.add_argument("--resolution", default="480p", choices=["480p", "720p"])
    parser.add_argument(
        "--image",
        default="visual/hero.png",
        help="source frame (default visual/hero.png; e.g. visual/oracle.png for the anchor)",
    )
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)

    hero = run_dir / args.image
    if not hero.exists():
        notice(f"briefing: no {args.image} — run render_visuals.py first; degrading")
        record_pipeline_status(
            run_dir,
            "briefing",
            "skipped",
            f"Source image {args.image} missing — run render_visuals.py first.",
        )
        return 0
    if not env_key("FAL_KEY", "FAL_API_KEY"):
        notice("briefing: skipped (no FAL_KEY); run degrades without video")
        record_pipeline_status(
            run_dir,
            "briefing",
            "skipped",
            "FAL_KEY not set — no briefing video generated.",
        )
        return 0
    if not env_key("OPENAI_API_KEY"):
        notice("briefing: skipped (no OPENAI_API_KEY for TTS audio); run degrades without video")
        record_pipeline_status(
            run_dir,
            "briefing",
            "skipped",
            "OPENAI_API_KEY not set — no TTS audio for briefing.",
        )
        return 0

    try:
        audio = tts_audio(briefing_script(run_dir, facts))
        audio_path = run_dir / "visual" / "briefing-audio.mp3"
        audio_path.write_bytes(audio)
        notice(f"briefing: TTS audio -> {audio_path.relative_to(run_dir)}")

        url = fabric_video(hero, audio_path, args.resolution)
        video_path = run_dir / "visual" / "briefing.mp4"
        download(url, video_path)
        if not media_committable(video_path):
            # The full briefing is the watch-on-demand artifact: keep it
            # locally (or object storage later) — the deployed Observatory
            # only ships the ≤4MB clips that git+Netlify can host.
            warn(
                f"briefing.mp4 is {video_path.stat().st_size / 1048576:.1f}MB "
                "— over the commit cap; keeping local, not publishing."
            )
            record_pipeline_status(
                run_dir,
                "briefing",
                "failed",
                "Briefing video exceeds the 4MB committed-media cap.",
            )
            return 0
        notice(f"briefing: wrote {video_path.relative_to(run_dir)}")
        set_visual_paths(run_dir, facts, briefing=str(video_path.relative_to(run_dir)))
        record_pipeline_status(
            run_dir,
            "briefing",
            "done",
            f"TTS audio + fal Fabric video generated ({args.resolution}).",
        )
    except ImportError:
        warn("openai/fal_client not installed (`uv sync --extra obs`); run degrades without video")
        record_pipeline_status(
            run_dir,
            "briefing",
            "skipped",
            "openai/fal_client not installed — no briefing video.",
        )
    except Exception as exc:
        warn(f"briefing failed ({exc}); run degrades without video")
        record_pipeline_status(
            run_dir,
            "briefing",
            "failed",
            f"Briefing generation failed: {exc}.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
