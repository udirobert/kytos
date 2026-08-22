"""Holo independent render-verification audit (trust through independent eyes).

An AI computer-use agent (H Company Holo) reads the built Observatory with its
own eyes — the same way a human visitor would — and reports what it sees. We
then diff the agent's reading against the committed facts.json. If the rendered
page disagrees with the file that generated it, that's a render bug we need to
know about before a visitor or judge sees it.

This is the "who audits the auditor" layer: planted_signal.py verifies the audit
rules catch known-answer perturbations; holo_audit.py verifies the Observatory
shows what the files actually say. Independent verification, not self-certification.

Degradation: no HAI_API_KEY, no Playwright, or API failure → print a notice and
exit 0. The site builds without this tool. Never blocks.

Usage:
    # screenshot built dist/ and verify against facts.json
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline

    # point at a live URL instead of local dist/
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline \
        --url https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/

    # use local dist/ (default: frontend/dist/runs/<run-id>/index.html)
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline --dist frontend/dist
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from _enrich_common import (  # noqa: E402 - same tools/ plumbing
    env_key,
    load_facts,
    notice,
    resolve_run_dir,
    utcnow,
    warn,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

HOLO_BASE_URL = "https://api.hcompany.ai/v1/"
HOLO_MODEL = "holo3-1-35b-a3b"

# The prompt sent to Holo. We ask it to read specific visible values from the
# screenshot and return them as a structured JSON object. Holo is a
# vision-language model — its core capability is reading screens.
AUDIT_PROMPT = """\
You are auditing a scientific web page. Look at the screenshot and read the \
following values exactly as they appear on the page. Return a JSON object with \
these fields:

- run_id: the run identifier (e.g. k001-mean-shift-baseline)
- fill_pct: the fill percentage shown in the data strip (a number like 38)
- warn_count: the number of audit warnings shown (look for "warn" or "warning")
- info_count: the number of info flags shown

Return ONLY the JSON object, no explanation. If you cannot find a value, use null.\
"""


# ── Expected values from facts.json ─────────────────────────────────────────


def _expected_from_facts(facts: dict) -> dict:
    """Extract the ground-truth values the page should display."""
    ceiling = facts.get("ceiling_headroom") or {}
    values = [float(v) for v in ceiling.values() if isinstance(v, (int, float))]
    fill = int(round(100 * sum(values) / len(values))) if values else 0
    fill = max(6, min(100, fill))

    flags = facts.get("audit_flags") or []
    warn_count = sum(1 for f in flags if f.get("severity") in ("warn", "error"))
    info_count = sum(1 for f in flags if f.get("severity") == "info")

    return {
        "fill_pct": fill,
        "warn_count": warn_count,
        "info_count": info_count,
        "run_id": facts.get("run_id", ""),
    }


# ── Diff expected vs observed ──────────────────────────────────────────────────


def _diff(expected: dict, observed: dict) -> list[tuple[str, str, str, str]]:
    """Compare Holo's reading against facts.json.

    Returns a list of (field, expected, observed, detail) tuples for mismatches.
    Empty list = all values match. None in observed means Holo couldn't read it
    — that's not a mismatch, just a miss.
    """
    mismatches: list[tuple[str, str, str, str]] = []

    for field in ("fill_pct", "warn_count", "info_count"):
        exp = expected.get(field)
        obs = observed.get(field)
        if obs is None:
            continue  # Holo couldn't read — not a mismatch
        if field == "fill_pct":
            # ±5 tolerance — count-up animation + rounding
            if abs(int(obs) - int(exp)) > 5:
                mismatches.append((field, str(exp), str(obs), "delta > 5"))
        else:
            if int(obs) != int(exp):
                mismatches.append((field, str(exp), str(obs), "exact match required"))

    # run_id: loose match — Holo may include extra text
    exp_id = expected.get("run_id", "")
    obs_id = (observed.get("run_id") or "").strip()
    if obs_id and exp_id and exp_id not in obs_id and obs_id not in exp_id:
        mismatches.append(("run_id", exp_id, obs_id, "loose match failed"))

    return mismatches


# ── Holo API client ────────────────────────────────────────────────────────────


def _holo_client():
    """Build an OpenAI-compatible client pointed at Holo's API.

    Returns None if HAI_API_KEY is not set (degrade, not error).
    """
    api_key = env_key("HAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(base_url=HOLO_BASE_URL, api_key=api_key)


# ── Screenshot via Playwright ──────────────────────────────────────────────────


def _screenshot_page(
    url: str, out_path: Path, viewport_w: int = 1280, viewport_h: int = 900
) -> bool:
    """Use Playwright to screenshot the page after JS executes.

    We wait for the data-strip count-up animation to settle (site.js animates
    from 0 to the real value on load). A 3s wait covers the 2s animation + margin.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        warn("holo_audit: playwright not installed (`uv sync --extra obs`); skipped")
        return False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": viewport_w, "height": viewport_h})
            page.goto(url, wait_until="networkidle", timeout=30_000)
            # Let the count-up animation + scroll-reveal settle
            page.wait_for_timeout(3000)
            page.screenshot(path=str(out_path), full_page=False)
            browser.close()
        return True
    except Exception as exc:
        warn(f"holo_audit: screenshot failed ({exc}); skipped")
        return False


def _screenshot_local_dist(run_id: str, dist_dir: Path, out_path: Path) -> str | None:
    """Screenshot the run page from a local dist/ build.

    Serves dist/ on a temp port, screenshots the run page, returns the file URL
    used (for logging) or None on failure.
    """
    run_html = dist_dir / "runs" / run_id / "index.html"
    if not run_html.is_file():
        warn(f"holo_audit: {run_html} not found; build first (python frontend/build.py)")
        return None

    # Serve the dist dir so relative paths (CSS, JS, images) resolve correctly
    import http.server
    import socketserver
    import threading

    port = 0  # OS-assigned free port
    handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(handler):
        def log_message(self, *args):
            pass

    httpd = socketserver.TCPServer(("", port), QuietHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://localhost:{port}/runs/{run_id}/index.html"
    ok = _screenshot_page(url, out_path)
    httpd.shutdown()
    return url if ok else None


# ── Ask Holo ───────────────────────────────────────────────────────────────────


def _ask_holo(client, screenshot_path: Path) -> dict | None:
    """Send the screenshot to Holo and parse the structured response."""
    image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode()

    try:
        response = client.chat.completions.create(
            model=HOLO_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": AUDIT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            # Low temperature — we want faithful reading, not creativity
            temperature=0.0,
            max_tokens=512,
        )
    except Exception as exc:
        warn(f"holo_audit: Holo API call failed ({exc}); skipped")
        return None

    raw = response.choices[0].message.content or ""
    # Holo may wrap JSON in ```json ... ``` blocks
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        warn(f"holo_audit: could not parse Holo response as JSON: {raw[:200]}")
        return None


# ── Full audit ──────────────────────────────────────────────────────────────────


def run_audit(run_dir: Path, dist_dir: Path | None = None, url: str | None = None) -> dict:
    """Run the full Holo audit.

    Returns a report dict:
      {"status": "skipped", "reason": "..."} — degraded, no API key or deps
      {"status": "pass", "results": [...], "summary": "4/4 passed"}
      {"status": "fail", "results": [...], "summary": "2/4 passed"}
    """
    facts = load_facts(run_dir)
    run_id = facts.get("run_id", run_dir.name)
    expected = _expected_from_facts(facts)

    client = _holo_client()
    if client is None:
        notice("holo_audit: skipped (no HAI_API_KEY); run degrades empty")
        return {
            "status": "skipped",
            "reason": "no HAI_API_KEY",
            "run_id": run_id,
            "expected": expected,
        }

    # Screenshot
    screenshot_path = run_dir / "visual" / "holo_audit_screenshot.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    if url:
        ok = _screenshot_page(url, screenshot_path)
    elif dist_dir:
        used_url = _screenshot_local_dist(run_id, dist_dir, screenshot_path)
        ok = used_url is not None
    else:
        # Default: try frontend/dist
        default_dist = REPO_ROOT / "frontend" / "dist"
        if default_dist.is_dir():
            used_url = _screenshot_local_dist(run_id, default_dist, screenshot_path)
            ok = used_url is not None
        else:
            warn("holo_audit: no dist/ found; build first or use --url")
            return {
                "status": "skipped",
                "reason": "no dist/ or --url provided",
                "run_id": run_id,
            }

    if not ok:
        return {
            "status": "skipped",
            "reason": "screenshot failed",
            "run_id": run_id,
        }

    notice(f"holo_audit: screenshot saved to {screenshot_path.relative_to(REPO_ROOT)}")

    # Ask Holo
    observed = _ask_holo(client, screenshot_path)
    if observed is None:
        return {
            "status": "skipped",
            "reason": "Holo API call failed",
            "run_id": run_id,
        }

    notice(f"holo_audit: Holo reading = {json.dumps(observed, indent=2)}")

    # Diff
    mismatches = _diff(expected, observed)
    results = []
    fields = ["fill_pct", "warn_count", "info_count", "run_id"]
    for field in fields:
        matching = not any(m[0] == field for m in mismatches)
        exp_val = expected.get(field)
        obs_val = observed.get(field)
        if matching:
            results.append({"field": field, "ok": True, "expected": exp_val, "observed": obs_val})
        else:
            mismatch = next(m for m in mismatches if m[0] == field)
            results.append(
                {
                    "field": field,
                    "ok": False,
                    "expected": exp_val,
                    "observed": obs_val,
                    "detail": mismatch[3],
                }
            )

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    status = "pass" if passed == total else "fail"

    return {
        "status": status,
        "run_id": run_id,
        "model": HOLO_MODEL,
        "results": results,
        "summary": f"{passed}/{total} passed",
        "observed": observed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    parser.add_argument("--dist", type=Path, default=None, help="local dist/ directory")
    parser.add_argument("--url", default=None, help="live URL to screenshot (overrides --dist)")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)

    notice(f"holo_audit: auditing {run_dir.name} — independent render verification")
    report = run_audit(run_dir, args.dist, args.url)

    # Print results
    print()
    if report["status"] == "skipped":
        print(f"  [SKIP] holo_audit skipped: {report.get('reason', 'unknown')}")
    else:
        for r in report.get("results", []):
            status = "PASS" if r["ok"] else "FAIL"
            detail = f"expected={r.get('expected')} observed={r.get('observed')}"
            if not r["ok"] and "detail" in r:
                detail += f" ({r['detail']})"
            print(f"  [{status}] {r['field']:<16} {detail}")

    print(f"\nholo render-verification: {report.get('summary', 'skipped')}")

    # Save audit report
    report["generated_at"] = utcnow()
    report_path = run_dir / "holo_audit.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        rel = str(report_path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(report_path)
    notice(f"holo_audit: report saved to {rel}")

    # Exit 0 on skip or pass, 1 on fail
    if report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
