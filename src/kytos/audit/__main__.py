"""CLI: ``python -m kytos.audit --run experiments/<run-id>``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kytos.audit.rules import run_all_rules


def audit_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    context_path = run_dir / "audit" / "context.json"
    if not context_path.is_file():
        raise FileNotFoundError(context_path)

    context = json.loads(context_path.read_text(encoding="utf-8"))
    flags = run_all_rules(context)
    payload = {
        "run_id": context.get("run_id", run_dir.name),
        "flags": flags,
    }

    out_dir = run_dir / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    flags_path = out_dir / "flags.json"
    flags_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run biological audit rules on a run.")
    parser.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Experiment run directory",
    )
    args = parser.parse_args(argv)
    payload = audit_run(args.run)
    summary = json.dumps(
        {"flags": len(payload["flags"]), "path": str(args.run / "audit" / "flags.json")}
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
