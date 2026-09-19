"""TypeSafe QC helper for Kytos VCC decisions.

Uses the TypeSafe SystemOne API to answer structured questions about
experiment state. The API key is read from the environment or `.env`:

    TYPESAFE_API_KEY=...
    TYPESAFE_MODEL=jev-latest              # optional
    TYPESAFE_BASE_URL=https://api.typesafe.ai  # optional

Examples:
  # Free-form structured ask:
  python tools/typesafe_qc.py ask \
      --state /tmp/state.json \
      --questions /tmp/questions.json \
      --out /tmp/typesafe_answer.json

  # Built-in VCC next-experiment gate:
  python tools/typesafe_qc.py vcc-gate --state /tmp/vcc_state.json
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.request
from pathlib import Path

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - fallback to system certs
    _SSL_CONTEXT = ssl.create_default_context()

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_if_present(path: Path | None = None) -> None:
    """Minimal .env loader that never overwrites existing env vars."""
    env_path = path or (REPO_ROOT / ".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def require_api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise SystemExit("TYPESAFE_API_KEY is not set (put it in .env or environment).")
    return key


def post_systemone(payload: dict, timeout: int = 120) -> dict:
    key = require_api_key()
    base = os.environ.get("TYPESAFE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    url = f"{base}/v1/systemone"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "kytos-typesafe-qc/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_json_or_text(path: str) -> object:
    p = Path(path)
    raw = p.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_ask(args: argparse.Namespace) -> int:
    state = load_json_or_text(args.state)
    questions = json.loads(Path(args.questions).read_text())
    if not isinstance(questions, dict) or not questions:
        raise SystemExit("--questions must be a non-empty JSON object")

    payload = {
        "model": args.model or os.environ.get("TYPESAFE_MODEL", DEFAULT_MODEL),
        "state": state,
        "questions": questions,
    }
    result = post_systemone(payload, timeout=args.timeout)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
    return 0


def vcc_gate_questions() -> dict:
    return {
        "safe_to_submit": {
            "type": "noul",
            "instructions": (
                "Based only on the experiment evidence and rules, should this candidate "
                "be submitted now rather than waiting for more offline validation?"
            ),
            "criteria": {
                "true": (
                    "Evidence shows a likely improvement or a deliberate controlled "
                    "experiment with acceptable risk."
                ),
                "false": (
                    "Evidence is insufficient, likely regression, or violates constraints "
                    "such as daily submission limits."
                ),
            },
        },
        "next_focus": {
            "type": "choice",
            "instructions": "Choose the single highest expected-value next workstream.",
            "criteria": {
                "fix_delta_magnitude": (
                    "The main failure is delta scale or count generation; "
                    "recalibration/dual-moment is likely."
                ),
                "improve_context_transfer": (
                    "The main failure is context mismatch; use H1/Jurkat/RPE1 transfer "
                    "or context-specific deltas."
                ),
                "replicate_top_method": (
                    "The best route is to adopt or adapt the public top-100 pipeline."
                ),
                "offline_eval_harness": (
                    "No more submissions until an offline holdout evaluation harness is built."
                ),
            },
        },
        "risk_level": {
            "type": "score",
            "instructions": (
                "Rate the risk that the next proposed submission regresses leaderboard score."
            ),
            "criteria": [
                "Very low risk",
                "Low risk",
                "Medium risk",
                "High risk",
                "Very high risk",
            ],
        },
        "blocking_issues": {
            "type": "noul",
            "instructions": (
                "Does the state indicate any blocking data, evaluation, or resource issue "
                "that should be fixed before the next submission?"
            ),
        },
    }


def cmd_vcc_gate(args: argparse.Namespace) -> int:
    state = load_json_or_text(args.state)
    payload = {
        "model": args.model or os.environ.get("TYPESAFE_MODEL", DEFAULT_MODEL),
        "state": state,
        "questions": vcc_gate_questions(),
    }
    result = post_systemone(payload, timeout=args.timeout)

    # Add deterministic guardrail interpretation.
    answers = result.get("answers", {})
    safe = answers.get("safe_to_submit", {}).get("noul")
    verdict = "UNKNOWN"
    if isinstance(safe, (int, float)):
        verdict = "SUBMIT" if safe >= args.submit_threshold else "HOLD"
    result["kytos_guardrail"] = {
        "verdict": verdict,
        "submit_threshold": args.submit_threshold,
        "safe_to_submit_noul": safe,
        "note": "TypeSafe is advisory; final gating uses offline metrics and submission budget.",
    }

    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Send arbitrary state + questions JSON to TypeSafe")
    p_ask.add_argument("--state", required=True, help="Path to JSON or text state")
    p_ask.add_argument("--questions", required=True, help="Path to questions JSON object")
    p_ask.add_argument("--out", help="Optional output JSON path")
    p_ask.add_argument("--model", default=None)
    p_ask.add_argument("--timeout", type=int, default=120)
    p_ask.set_defaults(func=cmd_ask)

    p_gate = sub.add_parser("vcc-gate", help="Built-in VCC submission/QA gate")
    p_gate.add_argument("--state", required=True, help="Path to JSON state summary")
    p_gate.add_argument("--out", help="Optional output JSON path")
    p_gate.add_argument("--model", default=None)
    p_gate.add_argument("--timeout", type=int, default=120)
    p_gate.add_argument("--submit-threshold", type=float, default=0.65)
    p_gate.set_defaults(func=cmd_vcc_gate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
