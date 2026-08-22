"""fal hero still + share card for a run (gen media for engagement, never metrics).

Generates the κύτος vessel portrait (hero.png) and a share card from fal image
generation, downloads them into `visual/`, and records the paths in
`facts.json` -> `visual`. Degrades to a no-op (exit 0) when FAL_KEY is missing,
the client is absent, or a call fails — the site builds without media.

Spend: at most 2 fal image generations per run.

Usage:
    python tools/render_visuals.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse

from _enrich_common import (
    download,
    env_key,
    load_facts,
    notice,
    resolve_run_dir,
    set_visual_paths,
    warn,
)

MODEL = "fal-ai/flux/dev"
IMAGE_SIZE = "landscape_16_9"

HERO_PROMPT = (
    "cinematic scientific observatory instrument panel, a single hollow glass "
    "vessel (κύτος) floating in dark space, phosphor cyan and amber accents, "
    "dark lab palette, volumetric light, ultra detailed, 16:9"
)

SHARE_PROMPT = (
    "dark mission-control dashboard background with a glowing hollow glass "
    "vessel centerpiece, reserved negative space in the upper third for a "
    "title, phosphor cyan and amber accents, editorial, 16:9"
)


def _configure_fal_client() -> str:
    import fal_client  # lazy: partner client is optional

    key = env_key("FAL_KEY", "FAL_API_KEY")
    fal_client.api_key = key  # explicit; overrides env so either var works
    return key


def generate_still(prompt: str) -> str:
    """Run one fal image generation; return the output image URL."""
    import fal_client  # lazy: partner client is optional

    result = fal_client.subscribe(
        MODEL, arguments={"prompt": prompt, "image_size": IMAGE_SIZE, "num_images": 1}
    )
    try:
        return result["images"][0]["url"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected fal response shape: {result}") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)

    if not env_key("FAL_KEY", "FAL_API_KEY"):
        notice("visuals: skipped (no FAL_KEY); run degrades without media")
        return 0

    try:
        _configure_fal_client()
    except ImportError:
        warn("fal_client not installed (`uv sync --extra obs`); run degrades without media")
        return 0

    generated: dict[str, str] = {}
    for name, prompt in (("hero", HERO_PROMPT), ("share_card", SHARE_PROMPT)):
        try:
            url = generate_still(prompt)
            dest = run_dir / "visual" / f"{'hero' if name == 'hero' else 'share-card'}.png"
            download(url, dest)
            generated[name] = str(dest.relative_to(run_dir))
            notice(f"visuals: wrote {generated[name]}")
        except Exception as exc:
            warn(f"fal generation failed for {name} ({exc}); continuing")

    if generated:
        set_visual_paths(run_dir, facts, **generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
