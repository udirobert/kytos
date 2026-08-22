"""Narrative grounding check — the digest may only cite numbers facts.json knows.

The narrative panel is LLM-generated (OpenAI prod / Venice dev). Its only
license to exist is the hard rule "read facts.json only — never invent metrics
or claims". This tool enforces that rule deterministically and offline,
the same way planted_signal.py polices the audit rules:

1. Every numeric literal in narrative/report.md must appear somewhere in
   facts.json (metric values, ceilings, flag-message thresholds, counts
   derivable from the JSON, dates). Rounding to the narrative's own precision
   is accepted.
2. Regression guards: no ``(facts: key.path)`` debug annotations, no empty
   placeholder digests.

Missing artifacts degrade to ``status: skip`` (exit 0) — the site must build
with zero enrichment.

Usage:
    python tools/check_narrative.py --run experiments/k001-mean-shift-baseline
    python tools/check_narrative.py --run … --json …/verification/narrative_check.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
FACTS_ANNOTATION_RE = re.compile(r"\(facts:\s*[^)]*\)")
GENE_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,9}\b")


def _mask_genes(text: str) -> str:
    """Remove gene symbols before numeric extraction: ISG15 must not leak '15'."""
    return GENE_TOKEN_RE.sub(" ", text)


GENE_RE = r"[A-Z][A-Z0-9]{2,9}"
DIRECTION_RE = r"(?:up|down|upregulated|downregulated|increased|decreased)"
# "ISG15 up", "MX1, OAS1 down" (gene(s) then direction), in either order.
_GENE_THEN_DIR_RE = re.compile(
    rf"\b(?P<g1>{GENE_RE})(?:\s*[,;]\s*(?P<g2>{GENE_RE}))*\s+(?P<dir>(?i:{DIRECTION_RE}))\b"
)
_DIR_THEN_GENE_RE = re.compile(
    rf"\b(?P<dir>(?i:{DIRECTION_RE}))\b[^.\n;]{{0,30}}?\b(?P<g1>{GENE_RE})\b"
)
_DIRECTION_NORMALIZE = {
    "up": "up",
    "upregulated": "up",
    "increased": "up",
    "down": "down",
    "downregulated": "down",
    "decreased": "down",
}


def _facts_strings(obj: Any, out: list[str]) -> None:
    """Collect every string value in facts.json for verbatim claim support."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            _facts_strings(item, out)
    elif isinstance(obj, dict):
        for value in obj.values():
            _facts_strings(value, out)


def _sentence_containing(body: str, pos: int) -> str:
    start = (
        max(
            body.rfind(".", 0, pos),
            body.rfind("!", 0, pos),
            body.rfind("?", 0, pos),
            body.rfind("\n", 0, pos),
        )
        + 1
    )
    end_match = re.search(r"[.!?\n]", body[pos:])
    end = pos + end_match.start() if end_match else len(body)
    return body[start:end]


def _gene_direction_pairs(body: str) -> set[tuple[str, str]]:
    """Per-gene direction assignments ("IFIT1 up").

    Gene-then-direction pairs are always per-gene claims. Direction-then-gene
    pairs are ignored when the sentence names both directions — "2 up and
    2 down across ISG15, …" is a pathway-level count summary, not a per-gene
    assignment.
    """
    pairs: set[tuple[str, str]] = set()
    for match in _GENE_THEN_DIR_RE.finditer(body):
        direction = _DIRECTION_NORMALIZE[match.group("dir").lower()]
        for gene in (match.group("g1"), match.group("g2")):
            if gene:
                pairs.add((gene, direction))
    for match in _DIR_THEN_GENE_RE.finditer(body):
        sentence = _sentence_containing(body, match.start()).lower()
        if re.search(r"\bup\b", sentence) and re.search(r"\bdown\b", sentence):
            continue  # pathway-level count summary
        pairs.add((match.group("g1"), _DIRECTION_NORMALIZE[match.group("dir").lower()]))
    return pairs


def _numbers_in_obj(obj: Any, out: set[float]) -> None:
    """Collect every numeric literal in a JSON value, including numbers
    embedded in strings (flag messages carry thresholds like '+2.10')."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        return
    if isinstance(obj, str):
        for match in NUMBER_RE.finditer(_mask_genes(obj)):
            out.add(float(match.group()))
        return
    if isinstance(obj, list):
        for item in obj:
            _numbers_in_obj(item, out)
        return
    if isinstance(obj, dict):
        for value in obj.values():
            _numbers_in_obj(value, out)


def _grounded(candidate: float, text: str, allowed: set[float]) -> bool:
    """True if the candidate (or its rounding at the text's own precision)
    matches a number present in facts.json."""
    decimals = len(text.partition(".")[2])
    probe = round(candidate, decimals)
    for value in allowed:
        if abs(value - probe) < 1e-9 or abs(round(value, decimals) - probe) < 10**-decimals / 2:
            return True
    return False


def run_checks(narrative: str, facts: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Return (case, ok, detail) per grounding case."""
    allowed: set[float] = set()
    _numbers_in_obj(facts, allowed)
    # Counts derivable from facts are legitimate (e.g. "2 warnings").
    for value in (facts.get("audit_flags") or [], facts.get("hypotheses_preregistered") or []):
        if isinstance(value, list):
            allowed.add(float(len(value)))
    for flag in facts.get("audit_flags") or []:
        genes = flag.get("genes") or []
        if isinstance(genes, list):
            allowed.add(float(len(genes)))

    # Strip the generator provenance comment; it is metadata, not prose.
    body = re.sub(r"^\s*<!--.*?-->", "", narrative, count=1, flags=re.DOTALL)
    # Strip markdown images/links: their URLs contain arbitrary version numbers.
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
    body = re.sub(r"\]\([^)]*\)", "]", body)

    results: list[tuple[str, bool, str]] = []

    seen: set[str] = set()
    ungrounded = []
    for match in NUMBER_RE.finditer(_mask_genes(body)):
        text = match.group()
        if text in seen:
            continue
        seen.add(text)
        if not _grounded(float(text), text, allowed):
            ungrounded.append(text)
    results.append(
        (
            "numbers_grounded",
            not ungrounded,
            f"{len(seen) - len(ungrounded)}/{len(seen)} numbers trace to facts.json"
            + (f" — ungrounded: {', '.join(sorted(ungrounded))}" if ungrounded else ""),
        )
    )

    leaks = FACTS_ANNOTATION_RE.findall(body)
    results.append(
        (
            "no_facts_annotation_leak",
            not leaks,
            "no (facts: …) debug annotations"
            if not leaks
            else f"{len(leaks)} '(facts: …)' debug annotation(s) leaked into prose",
        )
    )

    prose = re.sub(r"[#*\-\s]", "", body)
    results.append(
        (
            "non_empty_digest",
            len(prose) >= 200,
            "digest has substantive prose"
            if len(prose) >= 200
            else "digest is empty or a stub (<200 chars of prose)",
        )
    )

    # Per-gene direction claims ("ISG15 up") need verbatim support in some
    # facts.json string containing both the gene and a matching direction
    # word. The facts schema carries pathway-level directionality in flag
    # messages only — anything more specific is invented, and invented
    # per-gene claims are exactly what the grounding contract forbids.
    strings: list[str] = []
    _facts_strings(facts, strings)
    inverse = {"up": "down", "down": "up"}
    unsupported = []
    for gene, direction in sorted(_gene_direction_pairs(body)):
        supported = False
        for s in strings:
            if gene not in s:
                continue
            if re.search(rf"\b{inverse[direction]}\b", s):
                continue  # source string states the conflicting direction
            if re.search(rf"\b{direction}\b", s):
                supported = True
                break
        if not supported:
            unsupported.append(f"{gene} {direction}")
    results.append(
        (
            "gene_direction_claims",
            not unsupported,
            "per-gene direction claims trace to facts.json"
            if not unsupported
            else f"unsupported per-gene direction claims: {', '.join(unsupported)}",
        )
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="experiment run directory")
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="write machine-readable result (default: <run>/verification/narrative_check.json)",
    )
    args = parser.parse_args(argv)
    run_dir = args.run

    narrative_path = run_dir / "narrative" / "report.md"
    facts_path = run_dir / "facts.json"
    out_path = Path(args.json) if args.json else run_dir / "verification" / "narrative_check.json"

    if not narrative_path.is_file() or not facts_path.is_file():
        payload = {
            "status": "skip",
            "summary": "no narrative to check",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cases": [],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"[SKIP] narrative grounding check: {payload['summary']}")
        return 0

    narrative = narrative_path.read_text(encoding="utf-8")
    facts = json.loads(facts_path.read_text(encoding="utf-8"))

    results = run_checks(narrative, facts)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<28} {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    summary = f"{len(results) - failed}/{len(results)} checks passed"
    print(f"\nnarrative grounding check: {summary}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "pass" if failed == 0 else "fail",
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in results],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
