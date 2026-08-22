"""Provenance helpers for experiment runs."""

from __future__ import annotations

import subprocess
from pathlib import Path


def read_text_if_exists(path: Path) -> str | None:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def git_head_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def provenance_from_run(run_dir: Path, meta: dict) -> dict:
    """Build provenance block for facts.json from meta.json and run artifacts."""
    code = meta.get("code") or {}
    commit = code.get("commit") or read_text_if_exists(run_dir / "codehash")
    if not commit:
        repo_root = run_dir
        for parent in [run_dir, *run_dir.parents]:
            if (parent / ".git").exists():
                repo_root = parent
                break
        commit = git_head_commit(repo_root)

    prov: dict = {
        "commit": commit or "unknown",
        "seed": int(meta.get("seed", 0)),
        "code_hash": code.get("hash") or read_text_if_exists(run_dir / "codehash") or "unknown",
    }
    # Scoring coverage caveat (e.g. seeded subsample) must be visible wherever
    # provenance is shown — real numbers on reduced coverage are still real,
    # but the reader must see the reduction.
    if meta.get("scoring_subsample"):
        prov["coverage"] = str(meta["scoring_subsample"])
    return prov
