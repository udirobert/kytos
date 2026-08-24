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
from typing import Any, NoReturn

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


def narration_provider() -> str:
    """Which backend powers run narration: venice (dev) or openai (hackathon)."""
    explicit = (env_key("NARRATION_PROVIDER", "KYTOS_NARRATION_PROVIDER") or "").lower()
    if explicit in ("venice", "openai"):
        return explicit
    if env_key("VENICE_INFERENCE_KEY", "VENICE_API_KEY"):
        return "venice"
    return "openai"


def chat_model() -> str:
    if narration_provider() == "venice":
        return env_key("VENICE_MODEL", "VENICE_CHAT_MODEL") or "stealth-ox-alpha"
    return env_key("OPENAI_MODEL", "OPENAI_NARRATIVE_MODEL") or "gpt-4o-mini"


def openai_chat_client():
    """OpenAI-compatible client for narration (Venice in dev, OpenAI in prod)."""
    import openai  # lazy

    if narration_provider() == "venice":
        key = env_key("VENICE_INFERENCE_KEY", "VENICE_API_KEY")
        if not key:
            raise RuntimeError("NARRATION_PROVIDER=venice but no VENICE_INFERENCE_KEY")
        base = env_key("VENICE_BASE_URL") or "https://api.venice.ai/api/v1"
        return openai.OpenAI(api_key=key, base_url=base)

    kwargs: dict = {"api_key": env_key("OPENAI_API_KEY")}
    base = env_key("OPENAI_BASE_URL", "OPENAI_API_BASE")
    if base:
        kwargs["base_url"] = base
    return openai.OpenAI(**kwargs)


def openai_tts_client():
    """OpenAI client for TTS — pinned to api.openai.com (not chat-only gateways).

    The OpenAI SDK auto-reads OPENAI_BASE_URL from the environment, so a chat
    gateway in .env silently hijacks the audio endpoint (404). Pin the direct
    path explicitly so TTS always reaches the real API.
    """
    import openai  # lazy

    direct = env_key("OPENAI_TTS_API_KEY", "OPENAI_DIRECT_API_KEY")
    if direct:
        return openai.OpenAI(api_key=direct, base_url="https://api.openai.com/v1")
    base = env_key("OPENAI_BASE_URL", "OPENAI_API_BASE") or ""
    if base and "api.openai.com" not in base:
        raise RuntimeError(
            "TTS unavailable on OPENAI_BASE_URL (chat-only gateway). "
            "Set OPENAI_TTS_API_KEY to a direct OpenAI key for briefing audio."
        )
    return openai.OpenAI(api_key=env_key("OPENAI_API_KEY"))


def resolve_run_dir(run: str) -> Path:
    """Resolve a `--run` value (path or `experiments/<run-id>`) to a folder."""
    p = Path(run)
    if not p.is_dir():
        candidate = REPO_ROOT / run
        if candidate.is_dir():
            p = candidate
    if not p.is_dir():
        die(f"run folder not found: {run}")
    return p.resolve()


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


MAX_COMMITTED_VIDEO_BYTES = 4 * 1024 * 1024  # keep git happy + pages light


def media_committable(dest: Path) -> bool:
    """Whether a generated video is small enough to commit to the repo.

    The Observatory deploys from git (Netlify) — anything over the cap stays
    local or needs object storage; the enrichment ledger records why.
    """
    try:
        return dest.stat().st_size <= MAX_COMMITTED_VIDEO_BYTES
    except OSError:
        return False


def download(url: str, dest: Path, timeout: int = 180) -> None:
    """Download a URL to a file (fal media URLs are signed https links)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "kytos-enrich/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


# ── Pipeline status ledger ────────────────────────────────────────────────
# Every enrichment tool records what it attempted and what happened into a
# shared pipeline_status.json so the agent trace can distinguish "never
# attempted" from "attempted but degraded."  Holo_audit already writes its
# own holo_audit.json with status="skipped"; this ledger covers the rest.

_PIPELINE_FILE = "pipeline_status.json"


def record_pipeline_status(run_dir: Path, step: str, status: str, detail: str) -> None:
    """Append/update one step's outcome in the run's pipeline_status.json.

    Args:
        run_dir:  the experiment run directory.
        step:     short key, e.g. "narrative", "literature", "ner".
        status:   "done" | "fallback" | "skipped" | "failed".
        detail:   one-line human-readable explanation.
    """
    path = run_dir / _PIPELINE_FILE
    ledger: dict[str, Any] = {}
    if path.is_file():
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ledger = {}
    steps = ledger.setdefault("steps", {})
    steps[step] = {
        "status": status,
        "detail": detail,
        "timestamp": utcnow(),
    }
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def load_pipeline_status(run_dir: Path) -> dict[str, Any]:
    """Read the pipeline_status.json ledger (empty dict if missing)."""
    path = run_dir / _PIPELINE_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}
