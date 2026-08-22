"""Shared plumbing for the Observatory enrichment tools (Developer B).

Small stdlib-only helpers so each `tools/render_*.py` tool stays a thin
script: resolve the run folder, load/update `facts.json`, download artifacts,
and print consistent notices. Importing this module must NEVER require a
third-party package — partner clients (openai, tavily, fal_client) are
imported lazily inside each tool and degrade on absence.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent


def die(msg: str) -> NoReturn:
    """Print to stderr and exit 1 — used for contract violations, not API failures."""
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def notice(msg: str) -> None:
    print(f"[enrich] {msg}")


def warn(msg: str) -> None:
    print(f"[enrich] warning: {msg}", file=sys.stderr)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def env_key(*names: str) -> str | None:
    """First non-empty value among the given env var names (upper + lower)."""
    for name in names:
        for candidate in (name, name.upper()):
            value = os.environ.get(candidate, "").strip()
            if value:
                return value
    return None


def resolve_run_dir(run: str) -> Path:
    """Resolve a `--run` value (path or `experiments/<run-id>`) to a folder."""
    p = Path(run)
    if not p.is_dir():
        candidate = REPO_ROOT / run
        if candidate.is_dir():
            p = candidate
    if not p.is_dir():
        die(f"run folder not found: {run}")
    return p


def load_facts(run_dir: Path) -> dict:
    """Read and validate the run's facts.json (the single render contract)."""
    fp = run_dir / "facts.json"
    if not fp.exists():
        die(f"missing {fp} — run the facts assembler first (Developer A)")
    try:
        facts = json.loads(fp.read_text())
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {fp}: {exc}")
    if not isinstance(facts, dict):
        die(f"{fp} must contain a JSON object")
    return facts


def write_facts(run_dir: Path, facts: dict) -> None:
    (run_dir / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")


def set_visual_paths(run_dir: Path, facts: dict, **paths: str | None) -> bool:
    """Set facts.json['visual'][key] = value for non-None values; persist if changed.

    Only touched on successful generation — a degraded run leaves facts.json
    untouched (the site renders without the media).
    """
    visual = facts.setdefault("visual", {})
    changed = False
    for key, value in paths.items():
        if value:
            visual[key] = value
            changed = True
    if changed:
        write_facts(run_dir, facts)
    return changed


def download(url: str, dest: Path, timeout: int = 180) -> None:
    """Download a URL to a file (fal media URLs are signed https links)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "kytos-enrich/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
