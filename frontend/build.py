"""Static site build orchestration."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = FRONTEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from frontend.observatory.render import (  # noqa: E402 - after sys.path bootstrap
    render_about,
    render_home,
    render_run_detail,
    render_runs_index,
)
from frontend.observatory.meta import render_robots_txt, render_sitemap_xml  # noqa: E402
from frontend.observatory.runs import discover_runs  # noqa: E402


def _copy_tree(src: Path, dest: Path) -> None:
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _copy_run_media(run_dir: Path, out_run_dir: Path) -> str:
    """Copy visual/ and return URL prefix relative to run index.html."""
    visual_src = run_dir / "visual"
    if not visual_src.is_dir():
        return ""
    visual_dest = out_run_dir / "visual"
    _copy_tree(visual_src, visual_dest)
    return "visual/"


def build(experiments_dir: Path, out_dir: Path, frontend_root: Path) -> None:
    experiments_dir = experiments_dir.resolve()
    out_dir = out_dir.resolve()
    frontend_root = frontend_root.resolve()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    static_src = frontend_root / "static"
    static_dest = out_dir / "static"
    _copy_tree(static_src, static_dest)

    runs = discover_runs(experiments_dir)
    (out_dir / "index.html").write_text(render_home(runs, root_prefix=""), encoding="utf-8")

    about_dir = out_dir / "about"
    about_dir.mkdir()
    (about_dir / "index.html").write_text(render_about(runs, root_prefix="../"), encoding="utf-8")

    runs_dir = out_dir / "runs"
    runs_dir.mkdir()
    (runs_dir / "index.html").write_text(
        render_runs_index(runs, root_prefix="../"), encoding="utf-8"
    )

    for run in runs:
        run_out = runs_dir / run.run_id
        run_out.mkdir(parents=True)
        media_prefix = _copy_run_media(run.path, run_out)
        # Provenance drill-down: ship the committed metrics CSVs next to the page
        # so every headline value links to its actual source file.
        metrics_src = run.path / "metrics"
        if metrics_src.is_dir():
            _copy_tree(metrics_src, run_out / "metrics")
        # Verification layer: ship the Holo agent's screenshot so the
        # independent-audit panel can show what the agent actually saw.
        holo_shot = run.path / "holo_screenshot.png"
        if holo_shot.is_file():
            shutil.copy2(holo_shot, run_out / "holo_screenshot.png")
        html = render_run_detail(
            run,
            runs,
            root_prefix="../../",
            media_prefix=media_prefix,
        )
        (run_out / "index.html").write_text(html, encoding="utf-8")

    sitemap_paths = ["/", "/about/", "/runs/"] + [f"/runs/{run.run_id}/" for run in runs]
    (out_dir / "robots.txt").write_text(render_robots_txt(), encoding="utf-8")
    (out_dir / "sitemap.xml").write_text(render_sitemap_xml(sitemap_paths), encoding="utf-8")

    print(f"Built {len(runs)} run(s) → {out_dir}")


def main(argv: list[str] | None = None) -> int:
    frontend_root = Path(__file__).resolve().parent
    repo_root = frontend_root.parent

    parser = argparse.ArgumentParser(description="Build Kytos Observatory static site.")
    parser.add_argument(
        "--experiments",
        type=Path,
        default=repo_root / "experiments",
        help="Experiments directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=frontend_root / "dist",
        help="Output directory",
    )
    args = parser.parse_args(argv)

    build(args.experiments, args.out, frontend_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
