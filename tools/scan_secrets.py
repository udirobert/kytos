"""Deterministic, offline secret scanner for the Kytos pre-commit hook.

Mirrors the project ethos (NOTES §6 weft / §5 | lenitnes): the verdict is made
by *rules*, not heuristics-they-rely-on-a-network; nothing depends on a
third-party scanner that can silently rot between installs.

It flags high-confidence token *formats* plus high-signal "key = value"
assignments, and suppresses false positives via an inline allowlist
(`secrets-allowlist.txt`, one term or pattern per line, `#` comments allowed).

Usage:
    pre-commit (default): reads staged file paths from argv and exits 1 on any hit
    --all: scan the whole repository
    --paths: space-separated explicit paths (testing)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = Path(__file__).resolve().parent / "secrets-allowlist.txt"

# (description, compiled regex). Order matters little; each is tried per file.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "AWS secret access key",
        re.compile(
            r"(?i)(aws_secret_access_key|aws_secret|secret_access_key)"
            r"\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]"
        ),
    ),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Google OAuth client secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_\-]{15,}\b")),
    ("GitHub token", re.compile(r"\b(ghp_|gho_|ghu_|ghs_|github_pat_)[A-Za-z0-9_]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("OpenAI/generic API key", re.compile(r"\b(sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,})\b")),
    ("Stripe secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "connection string with password",
        re.compile(r"(?i)(postgres|mysql|redis|amqp|mongodb)(\+srv)?://[^\s:]+:[^@\s]+@"),
    ),
    (
        "high-signal assignment",
        re.compile(
            r"(?i)((api[_-]?key|secret|token|password|passwd|client[_-]?secret)"
            r"\s*[:=]\s*['\"][^'\"]{6,}['\"])"
        ),
    ),
]


def _allowlist() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        return []
    keep = []
    for line in ALLOWLIST_FILE.read_text(errors="replace").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            keep.append(s)
    return keep


def scan_text(path: Path) -> list[tuple[str, str, str, str]]:
    """Return (path, line_no, description, matched_secret) for each hit."""
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:  # binary — skip
        return []
    text = raw.decode(errors="replace")
    allowlist = _allowlist()
    hits: list[tuple[str, str, str, str]] = []
    for desc, pat in PATTERNS:
        for m in pat.finditer(text):
            secret = m.group(0)
            if any(term in secret for term in allowlist):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append((str(path), str(line_no), desc, secret[:120]))
    return hits


def scan_paths(paths: list[Path]) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for p in paths:
        if not p.is_file():
            continue
        out.extend(scan_text(p))
    return out


def all_repo_files() -> list[Path]:
    """Every file in the repo except VCS/virtualenv/generated dirs.

    Scanning `.venv/` (installed package metadata) or build output would drown
    real signals in false positives.
    """
    skip_parts = {
        ".git",
        ".venv",
        ".venv-science",
        "venv",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        "dist",
    }
    return [
        p
        for p in sorted(REPO_ROOT.rglob("*"))
        if p.is_file() and not skip_parts.intersection(p.parts)
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="scan the whole repository")
    ap.add_argument(
        "paths", nargs="*", default=[], help="file paths to scan (pre-commit passes these)"
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.all:
        paths = all_repo_files()
    elif args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        paths = []  # pre-commit passes zero or more paths

    hits = scan_paths(paths)
    if not hits:
        return 0
    for path, line, desc, secret in hits:
        print(f"{path}:{line}  [{desc}]  {secret}", file=sys.stderr)
    print(f"secret scan: {len(hits)} hit(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
