#!/usr/bin/env python3
"""Dr. Kytos presenter video — newsroom script + anchor portrait -> talking clip (fal).

The Observatory's cast: **Dr. Kytos is the anchor** (speaks the broadcast),
**the vessel is the instrument** (shows where biology says we're wrong), and
the cell/orb Fabric briefing stays the 45s watch-on-demand artifact. This
tool generates the presenter clip:

  1. script  — `newsroom/script.md` (deterministic broadcast wrapper over
               facts.json) when present, else `narrative/report.md`, else a
               facts-derived fallback — the spoken words trace to facts.json
  2. audio   — OpenAI TTS (tts-1, voice `shimmer`) -> `visual/presenter-audio.mp3`
  3. video   — fal `veed/fabric-1.0`, **source frame = the committed Dr. Kytos
               anchor portrait** (`--image visual/drkytos-2-young-energetic.png`
               by default; Fabric maps phonemes to facial keypoints, so the
               anchor's face is what lip-syncs) -> `visual/presenter.mp4`
  4. paths   — `visual.presenter` in facts.json on success

Degrades to a no-op (exit 0) at any step — the site builds without it.

Spend: 1 TTS call + 1 Fabric call per run. The presenter clip is short (~8s),
so with ~45s Fermata it stays well under the 4MB commit cap used for
companion videos (see `media_committable`).

Usage:
    python tools/render_presenter.py --run experiments/k001-mean-shift-baseline
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
TTS_VOICE = "shimmer"  # warm, correspondent-grade — not the onyx briefing voice
DEFAULT_ANCHOR_FRAME = "visual/drkytos-african-2.png"
MAX_SCRIPT_CHARS = 950  # ≈ 70 s of speech — bounds video length and spend


def strip_markdown(text: str) -> str:
    """Crude markdown -> plain speech text (drops comments, fences, headings,
    blockquotes, and markup). Multi-line HTML comments are tracked so their
    continuation lines are never spoken."""
    lines = []
    in_comment = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("```"):
            continue  # fenced blocks are not spoken
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("#") or s.startswith(">"):
            continue  # headings + blockquote annotations are never spoken
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # links -> label text
        s = re.sub(r"[*_`]", "", s)  # emphasis/backticks only (keep #, > never reach here)
        s = re.sub(r"\|", " ", s)  # table pipes -> spaces
        if s:
            lines.append(s)
    return " ".join(lines).strip()


def presenter_script(run_dir: Path, facts: dict, script: str | None = None) -> str:
    """Spoken script traced to committed artifacts; fallback to facts fields.

    ``script`` may override the default search order (newsroom/script.md,
    narrative/report.md) — used by the chronicle short workflow so specimen
    and episode scripts never pollute a run's canonical broadcast.
    """
    if script:
        explicit = Path(script)
        if explicit.exists():
            text = strip_markdown(explicit.read_text())
            return (text or "Kytos run briefing.")[:MAX_SCRIPT_CHARS]
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
        default=DEFAULT_ANCHOR_FRAME,
        help=f"anchor portrait for Fabric lip-sync (default {DEFAULT_ANCHOR_FRAME})",
    )
    parser.add_argument(
        "--script",
        default=None,
        help=(  # explicit script; default: newsroom/script.md, then narrative/report.md
            "explicit markdown script path"
        ),
    )
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)
    script_text = presenter_script(run_dir, facts, script=args.script)

    # Recent enrichment may have written facts.json with absolute visual paths
    # (run_enrichment.sh refreshes facts after each tool; keep compat).
    anchor = run_dir / args.image
    if not anchor.exists():
        notice(f"presenter: no anchor {args.image} — run render_visuals.py first; degrading")
        record_pipeline_status(
            run_dir,
            "presenter",
            "skipped",
            f"Anchor image {args.image} missing — run render_visuals.py first.",
        )
        return 0
    if not env_key("FAL_KEY", "FAL_API_KEY"):
        notice("presenter: skipped (no FAL_KEY); run degrades without presenter video")
        record_pipeline_status(run_dir, "presenter", "skipped", "FAL_KEY not set.")
        return 0
    if not env_key("OPENAI_API_KEY"):
        notice("presenter: skipped (no OPENAI_API_KEY for TTS audio); degrading")
        record_pipeline_status(run_dir, "presenter", "skipped", "OPENAI_API_KEY not set.")
        return 0

    try:
        audio = tts_audio(script_text)
        audio_path = run_dir / "visual" / "presenter-audio.mp3"
        audio_path.write_bytes(audio)
        notice(f"presenter: TTS audio -> {audio_path.relative_to(run_dir)}")

        url = fabric_video(anchor, audio_path, args.resolution)
        video_path = run_dir / "visual" / "presenter.mp4"
        download(url, video_path)
        if not media_committable(video_path):
            warn(
                f"presenter.mp4 is {video_path.stat().st_size / 1048576:.1f}MB "
                "— over the commit cap; not publishing to the Observatory."
            )
            record_pipeline_status(
                run_dir,
                "presenter",
                "failed",
                "Presenter video exceeds the 4MB committed-media cap.",
            )
            return 0
        notice(f"presenter: wrote {video_path.relative_to(run_dir)}")
        set_visual_paths(run_dir, facts, presenter=str(video_path.relative_to(run_dir)))
        record_pipeline_status(
            run_dir,
            "presenter",
            "done",
            f"TTS audio + fal Fabric presenter video generated ({args.resolution}).",
        )
    except ImportError:
        warn("openai/fal_client not installed (`uv sync --extra obs`); degrading")
        record_pipeline_status(
            run_dir,
            "presenter",
            "skipped",
            "openai/fal_client not installed — no presenter video.",
        )
    except Exception as exc:
        warn(f"presenter failed ({exc}); run degrades without presenter")
        record_pipeline_status(
            run_dir,
            "presenter",
            "failed",
            f"Presenter generation failed: {exc}.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
