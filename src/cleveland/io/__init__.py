"""Run-protocol writers for cleveland experiments."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any


def git_commit(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_run_bundle(
    run_dir: Path,
    *,
    run_id: str,
    config: dict[str, Any],
    facts: dict[str, Any],
    meta: dict[str, Any],
    metrics: dict[str, Any],
    flags: list[dict[str, Any]],
    repo_root: Path,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(exist_ok=True)
    (run_dir / "audit").mkdir(exist_ok=True)
    (run_dir / "reproduce").mkdir(exist_ok=True)

    commit = git_commit(repo_root)
    meta = {
        **meta,
        "run_id": run_id,
        "created": meta.get("created", date.today().isoformat()),
        "code": {"commit": commit},
    }
    write_json(run_dir / "meta.json", meta)
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "facts.json", facts)
    write_json(run_dir / "metrics" / "summary.json", metrics)
    write_json(run_dir / "audit" / "flags.json", {"flags": flags})
    (run_dir / "codehash").write_text(commit + "\n")
    write_json(
        run_dir / "reproduce" / "seeds.json",
        {"seed": config.get("seed", 0), "walk_time": config.get("walk_time")},
    )
