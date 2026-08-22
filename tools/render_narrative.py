"""OpenAI narration for a run — grounded digest rendered from facts.json only.

Hard rules (docs/observatory.md §5, docs/run-protocol.md):
- reads facts.json only; never invents metrics or claims
- every LLM claim must trace to a facts.json field (citations in parentheses)
- on missing key / client / API failure: write a DETERMINISTIC fallback digest
  and exit 0 — the site must build with zero API keys at view time

Spend: at most 1 LLM call per run (gpt-4o-mini).

Usage:
    python tools/render_narrative.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json

from _enrich_common import (
    chat_model,
    env_key,
    load_facts,
    narration_provider,
    notice,
    openai_chat_client,
    resolve_run_dir,
    utcnow,
    warn,
)

MODEL = chat_model()
MAX_TOKENS = 700
OUT = "narrative/report.md"

SYSTEM_PROMPT = (
    "You write a short scientific run digest for a virtual-cell competition. "
    "GROUND EVERY CLAIM in the facts JSON provided. "
    "Cite the source field inline in parentheses, e.g. (facts: headline_metrics.DESigGenesRecall). "
    "Never invent numbers, genes, thresholds, or conclusions. "
    "Output GitHub-flavored markdown, max ~250 words. "
    "Start with one sentence on the run's headline result."
)


def fallback_digest(facts: dict) -> str:
    """Deterministic digest rendered purely from facts.json fields (no LLM)."""
    provenance = facts.get("provenance") or {}
    lines = [
        f"# {facts.get('run_id', 'run')} — run digest",
        "",
        f"> Fallback digest rendered deterministically from `facts.json` (no LLM call). "
        f"Generated {utcnow()} UTC.",
        "",
        "## Headline",
        f"{facts.get('headline', 'no headline in facts.json')}",
        "",
        "## Metrics",
        "",
        "| metric | value | ceiling |",
        "|---|---|---|",
    ]
    headline_metrics = facts.get("headline_metrics") or {}
    ceiling = facts.get("ceiling_headroom") or {}
    for metric, value in headline_metrics.items():
        lines.append(f"| {metric} | {value} | {ceiling.get(metric, '')} |")
    if not headline_metrics:
        lines.append("| _none in facts.json_ | | |")
    lines += ["", "## Audit flags", ""]
    flags = facts.get("audit_flags") or []
    if not flags:
        lines.append("_none_")
    for flag in flags:
        genes = ", ".join(flag.get("genes") or [])
        lines.append(
            f"- **[{flag.get('severity', 'info')}]** `{flag.get('rule', '?')}` — "
            f"{genes} (`{flag.get('id', '?')}`)"
        )
    lines += [
        "",
        "## Provenance",
        "",
        f"- commit: `{provenance.get('commit', '?')}`",
        f"- seed: {provenance.get('seed', '?')}",
        f"- code hash: `{provenance.get('code_hash', '?')}`",
        f"- hypotheses pre-registered: {facts.get('hypotheses_preregistered', [])}",
    ]
    return "\n".join(lines) + "\n"


def render_with_openai(facts: dict) -> str:
    client = openai_chat_client()
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"facts.json for this run:\n{json.dumps(facts, indent=2)}",
            },
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty narrative")
    header = (
        f"<!-- kytos narrative · generated_by=llm · provider={narration_provider()} "
        f"· model={MODEL} · {utcnow()} UTC -->"
    )
    return f"{header}\n\n{text}\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    facts = load_facts(run_dir)

    text = None
    provider = narration_provider()
    if provider == "venice":
        if not env_key("VENICE_INFERENCE_KEY", "VENICE_API_KEY"):
            warn("NARRATION_PROVIDER=venice but no VENICE_INFERENCE_KEY; using fallback digest")
        else:
            try:
                text = render_with_openai(facts)
                notice(f"narrative: LLM digest via venice / {MODEL}")
            except ImportError:
                warn("openai client not installed (`uv pip install openai`); using fallback digest")
            except Exception as exc:
                warn(f"Venice call failed ({exc}); using fallback digest")
    elif env_key("OPENAI_API_KEY"):
        try:
            text = render_with_openai(facts)
            notice(f"narrative: LLM digest via openai / {MODEL}")
        except ImportError:
            warn("openai client not installed (`uv pip install openai`); using fallback digest")
        except Exception as exc:
            warn(f"OpenAI call failed ({exc}); using fallback digest")
    if text is None:
        text = (
            f"<!-- kytos narrative · generated_by=fallback · {utcnow()} UTC -->\n\n"
            f"{fallback_digest(facts)}"
        )
        notice("narrative: deterministic fallback digest (no API key or call failed)")

    out = run_dir / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    notice(f"wrote {out.relative_to(run_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
