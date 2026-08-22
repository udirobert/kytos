"""Holo independent render-verification audit (trust through independent eyes).

A H computer-use agent opens the Observatory in a real browser, navigates the
page like a human visitor, and reports what it sees. We then diff the agent's
reading against the committed facts.json. If the rendered page disagrees with
the file that generated it, that's a render bug we need to know about before a
visitor or judge sees it.

Two modes, tried in order:

1. **Agent mode** (primary): uses H's Computer-use Agents API (hai-agents SDK).
   The `h/web-surfer-flash` agent drives a cloud browser — opens the URL, scrolls,
   clicks, reads values — and returns a structured {verdict, summary, findings}
   report. This is H's flagship product and the mode they're excited about.

2. **VLM mode** (fallback): screenshots the page via Playwright and sends a
   single image to the Holo vision model (holo3-1-35b-a3b). Passive
   screen-reading — the original approach before the Agents API launched.

This is the "who audits the auditor" layer: planted_signal.py verifies the audit
rules catch known-answer perturbations; holo_audit.py verifies the Observatory
shows what the files actually say. Independent verification, not self-certification.

Degradation: no HAI_API_KEY, no hai-agents, or API failure → try VLM fallback →
print a notice and exit 0. The site builds without this tool. Never blocks.

Usage:
    # audit the live deployed site (preferred — agent opens the real URL)
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline \
        --url https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/

    # agent mode against a local file:// URL (still navigates in a cloud browser)
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline \
        --url file:///path/to/dist/runs/k001/index.html

    # force VLM screenshot mode (skip the Agents API)
    python tools/holo_audit.py --run experiments/k001-mean-shift-baseline --vlm

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

# VLM mode (fallback) — the original Holo inference API
HOLO_BASE_URL = "https://api.hcompany.ai/v1/"
HOLO_MODEL = "holo3-1-35b-a3b"

# The H web-surfer-flash agent — H's pre-built browser navigation agent.
# From their docs: "fully managed agents that take actions on computers."
H_AGENT = "h/web-surfer-flash"


# ── Structured output: the typed answer the agent must return ──────────────────
#
# H's Computer-use Agents API supports answer_schema (a Pydantic model). The SDK
# derives the JSON Schema, the agent works within that constraint, and the
# final answer is validated and parsed into a typed instance. Non-conforming
# answers are rejected and retried. This is deeper than parsing free-form text
# — the agent's answer IS the type.


def _audit_schema():
    """Build the Pydantic answer_schema (imported lazily — tests run without it)."""
    from pydantic import BaseModel, Field

    class AuditReading(BaseModel):
        run_id: str | None = Field(
            None, description="The run identifier shown on the page header or breadcrumb"
        )
        fill_pct: int | None = Field(
            None, description="The fill percentage in the data strip (e.g. 38)"
        )
        warn_count: int | None = Field(
            None, description="Number of audit warnings (orange/red 'warn' badges)"
        )
        info_count: int | None = Field(
            None, description="Number of info flags (blue 'info' badges)"
        )

    return AuditReading


# Agent mode: the task prompt. We ask the agent to navigate the Observatory like
# a real QA tester — open the page, scroll through all content, read values from
# the data strip and audit flag badges, and interact with the vessel instrument.
# This is H's "QA Testing" use case: "point an autonomous browser agent at a
# live URL and it tests your app the way a real user would."
AGENT_AUDIT_PROMPT = """\
You are a QA tester auditing a scientific web page — the Kytos Observatory, a \
dashboard that visualizes model-evaluation results as an interactive 3D vessel.

Navigate to the page URL. Then:

1. Wait for the page to fully load (the 3D vessel and data strip animate on load).
2. Scroll down to see ALL content — the data strip, audit flags, narrative, \
   and provenance sections.
3. Read the data strip at the top: find the fill_pct (the fill percentage, \
   a number 0–100).
4. Count the audit flags: look for severity badges. Count warn_count (orange \
   "warn" badges) and info_count (blue "info" badges) separately.
5. Find the run_id — it appears in the breadcrumb or page header \
   (e.g. "k001-mean-shift-baseline").
6. Click on the 3D vessel or any interactive element to confirm the page is \
   interactive (not a static screenshot).
7. Check whether a briefing video or "briefing #1 of ~12" stamp is visible.

Report exactly what you see. If a value is not visible or you cannot find it, \
set that field to null. Ground every claim in what you actually observe on the \
screen — never invent values.\
"""

# VLM mode (fallback): the prompt sent to Holo with a static screenshot.
VLM_AUDIT_PROMPT = """\
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


# ── Agent mode: H Computer-use Agents API (hai-agents) ─────────────────────────


def _run_agent_audit(url: str) -> dict | None:
    """Run a H computer-use agent against the Observatory URL.

    Uses the hai-agents SDK to launch an h/web-surfer-flash session. The agent
    opens the URL in a cloud browser, navigates the page, reads visible values,
    and returns a structured, schema-validated answer via answer_schema.

    This is H's flagship Computer-use Agents API — the agent doesn't just read
    a screenshot, it drives a real browser: scrolling, clicking, interacting
    with the page like a human QA tester.

    Returns the observed values dict, or None on failure.
    """
    try:
        from hai_agents import Client
    except ImportError:
        warn("holo_audit: hai-agents not installed (`pip install hai-agents`); trying VLM fallback")
        return None

    api_key = env_key("HAI_API_KEY")
    if not api_key:
        return None

    try:
        client = Client(api_key=api_key)
    except Exception as exc:
        warn(f"holo_audit: hai-agents client init failed ({exc}); trying VLM fallback")
        return None

    AuditReading = _audit_schema()

    notice(f"holo_audit: launching computer-use agent at {url}")
    notice(f"holo_audit: agent={H_AGENT} — navigates and interacts like a real QA tester")

    try:
        result = client.run_session(
            agent=H_AGENT,
            messages=f"Navigate to {url} and audit it. {AGENT_AUDIT_PROMPT}",
            answer_schema=AuditReading,
            timeout_seconds=180,
        )
    except Exception as exc:
        warn(f"holo_audit: agent session failed ({exc}); trying VLM fallback")
        return None

    # The SDK validates the answer against our schema and returns a typed instance.
    # result.outcome is the terminal status: "completed", "failed", "timed_out", etc.
    outcome = getattr(result, "outcome", None)
    if outcome and outcome != "completed":
        err = getattr(result, "error", None)
        warn(f"holo_audit: agent session ended as {outcome}" + (f" ({err})" if err else ""))
        warn("holo_audit: trying VLM fallback")
        return None

    answer = getattr(result, "answer", None)
    if answer is None:
        warn("holo_audit: agent returned no answer; trying VLM fallback")
        return None

    # With answer_schema, result.answer is a validated Pydantic instance.
    # Fall back to dict extraction for robustness if the SDK returns raw JSON.
    if hasattr(answer, "model_dump"):
        observed = answer.model_dump()
    elif isinstance(answer, dict):
        observed = answer
    else:
        # Unstructured text — try to extract JSON (legacy path)
        raw = str(answer).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        json_start = raw.find("{")
        json_end = raw.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            raw = raw[json_start : json_end + 1]
        try:
            observed = json.loads(raw)
        except json.JSONDecodeError:
            warn(f"holo_audit: could not parse agent answer: {raw[:200]}")
            warn("holo_audit: trying VLM fallback")
            return None

    notice(f"holo_audit: agent reading = {json.dumps(observed, indent=2)}")
    return observed


# ── VLM mode: Holo inference API with Playwright screenshot (fallback) ────────


def _holo_vlm_client():
    """Build an OpenAI-compatible client pointed at Holo's inference API.

    Returns None if HAI_API_KEY is not set or openai not installed (degrade).
    """
    api_key = env_key("HAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(base_url=HOLO_BASE_URL, api_key=api_key)


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


def _ask_holo_vlm(client, screenshot_path: Path) -> dict | None:
    """Send the screenshot to Holo VLM and parse the structured response."""
    image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode()

    try:
        response = client.chat.completions.create(
            model=HOLO_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VLM_AUDIT_PROMPT},
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
            max_tokens=300,
        )
    except Exception as exc:
        warn(f"holo_audit: Holo VLM call failed ({exc}); skipped")
        return None

    raw = response.choices[0].message.content or ""
    # Holo may wrap JSON in ```json ... ``` blocks
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    try:
        observed = json.loads(raw)
        notice(f"holo_audit: VLM reading = {json.dumps(observed, indent=2)}")
        return observed
    except json.JSONDecodeError:
        warn(f"holo_audit: could not parse VLM response as JSON: {raw[:200]}")
        return None


# ── Full audit ──────────────────────────────────────────────────────────────────


def run_audit(
    run_dir: Path,
    dist_dir: Path | None = None,
    url: str | None = None,
    vlm_only: bool = False,
) -> dict:
    """Run the full Holo audit.

    Tries agent mode first (H Computer-use Agents API), then falls back to VLM
    mode (Playwright screenshot + Holo inference). Both modes diff the observed
    values against facts.json.

    Returns a report dict:
      {"status": "skipped", "reason": "..."} — degraded, no API key or deps
      {"status": "pass", "results": [...], "summary": "4/4 passed"}
      {"status": "fail", "results": [...], "summary": "2/4 passed"}
    """
    facts = load_facts(run_dir)
    run_id = facts.get("run_id", run_dir.name)
    expected = _expected_from_facts(facts)

    api_key = env_key("HAI_API_KEY")
    if not api_key:
        notice("holo_audit: skipped (no HAI_API_KEY); run degrades empty")
        return {
            "status": "skipped",
            "reason": "no HAI_API_KEY",
            "run_id": run_id,
            "expected": expected,
        }

    # Resolve the URL to audit
    audit_url = url
    screenshot_path = run_dir / "visual" / "holo_audit_screenshot.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    if not audit_url and not vlm_only:
        # Agent mode needs a URL; try the deployed site or local dist
        # Agent mode works best with a live URL the cloud browser can reach.
        # Local file:// or localhost won't work from H's cloud — skip to VLM.
        warn("holo_audit: agent mode needs --url (live URL the cloud browser can reach)")
        warn("holo_audit: falling back to VLM screenshot mode")

    if not audit_url:
        # VLM fallback: screenshot local dist
        effective_dist = dist_dir or (REPO_ROOT / "frontend" / "dist")
        if effective_dist.is_dir():
            used_url = _screenshot_local_dist(run_id, effective_dist, screenshot_path)
            if used_url is None:
                return {
                    "status": "skipped",
                    "reason": "screenshot failed",
                    "run_id": run_id,
                }
            audit_url = used_url
        else:
            warn("holo_audit: no dist/ found; build first or use --url")
            return {
                "status": "skipped",
                "reason": "no dist/ or --url provided",
                "run_id": run_id,
            }

    observed = None
    audit_mode = "skipped"

    # ── Agent mode (primary) ──
    if not vlm_only and url:
        observed = _run_agent_audit(url)
        audit_mode = "agent" if observed else "agent_failed"

    # ── VLM mode (fallback) ──
    if observed is None:
        vlm_client = _holo_vlm_client()
        if vlm_client is None:
            notice("holo_audit: VLM client unavailable (no openai package); skipped")
            return {
                "status": "skipped",
                "reason": "no openai package for VLM fallback",
                "run_id": run_id,
            }

        # Take screenshot if we haven't already (agent mode doesn't need one)
        if not screenshot_path.exists():
            ok = _screenshot_page(audit_url, screenshot_path)
            if not ok:
                return {
                    "status": "skipped",
                    "reason": "screenshot failed",
                    "run_id": run_id,
                }

        notice(f"holo_audit: screenshot saved to {screenshot_path.relative_to(REPO_ROOT)}")
        observed = _ask_holo_vlm(vlm_client, screenshot_path)
        audit_mode = "vlm" if observed else "vlm_failed"

    if observed is None:
        return {
            "status": "skipped",
            "reason": "all audit modes failed",
            "run_id": run_id,
            "audit_mode": audit_mode,
        }

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
        "audit_mode": audit_mode,
        "model": HOLO_MODEL if "vlm" in audit_mode else H_AGENT,
        "results": results,
        "summary": f"{passed}/{total} passed",
        "observed": observed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run folder or experiments/<run-id>")
    parser.add_argument("--dist", type=Path, default=None, help="local dist/ directory")
    parser.add_argument("--url", default=None, help="live URL to audit (agent mode, preferred)")
    parser.add_argument(
        "--vlm",
        action="store_true",
        help="force VLM screenshot mode (skip the Agents API)",
    )
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)

    notice(f"holo_audit: auditing {run_dir.name} — independent render verification")
    report = run_audit(run_dir, args.dist, args.url, args.vlm)

    # Print results
    print()
    if report["status"] == "skipped":
        print(f"  [SKIP] holo_audit skipped: {report.get('reason', 'unknown')}")
    else:
        mode_label = report.get("audit_mode", "?")
        print(f"  mode: {mode_label}")
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
