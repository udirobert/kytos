"""Fetch and analyze the VCC 2026 public leaderboard for offline calibration.

Usage:
  python tools/leaderboard_calibrate.py [--save /tmp/vcc_leaderboard.json]

Outputs:
  - Top-100 threshold and component breakdowns
  - Where our submissions rank
  - Score distribution analysis to guide next moves
"""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.request

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL_CONTEXT = ssl.create_default_context()

LEADERBOARD_URL = "https://virtualcellchallenge.org/api/leaderboard"
OUR_TEAM = "kytos"


def fetch_leaderboard() -> dict:
    req = urllib.request.Request(LEADERBOARD_URL, headers={"User-Agent": "kytos-research/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read())


def analyze(data: dict) -> None:
    entries = data.get("entries", data if isinstance(data, list) else [])
    scored = [e for e in entries if e.get("score_avg") is not None]
    scored.sort(key=lambda x: x["score_avg"], reverse=True)

    print(f"Total entries: {len(entries)}, scored: {len(scored)}")
    if not scored:
        print("No scored entries found.")
        return

    # Top-100 threshold
    top100_idx = min(99, len(scored) - 1)
    threshold = scored[top100_idx]["score_avg"]
    print(f"\nTop-100 threshold: {threshold:.4f}")
    print(f"  Team: {scored[top100_idx].get('team_name', '?')}")
    print(f"  Model: {scored[top100_idx].get('model_name', '?')}")
    print("  Components at rank 100:")
    for key in ["score_pds", "score_mse", "score_nmae", "score_fid", "score_reach", "score_jac"]:
        val = scored[top100_idx].get(key)
        if val is not None:
            print(f"    {key}: {val:.4f}")

    # Top 5
    print("\nTop 5:")
    for i, e in enumerate(scored[:5]):
        print(
            f"  {i + 1}. {e.get('team_name', '?'):25s} {e.get('model_name', '?'):35s} "
            f"score={e['score_avg']:.4f} pds={e.get('score_pds', 0):.4f} "
            f"nmae={e.get('score_nmae', 0):.4f} mse={e.get('score_mse', 0):.4f}"
        )

    # Our entries
    our = [
        (i, e)
        for i, e in enumerate(scored)
        if OUR_TEAM in str(e.get("model_name", "")).lower()
        or OUR_TEAM in str(e.get("team_name", "")).lower()
    ]
    print(f"\nOur entries ({len(our)}):")
    for rank_idx, e in our:
        print(
            f"  Rank {rank_idx + 1}: {e.get('model_name', '?'):40s} "
            f"score={e['score_avg']:.4f} pds={e.get('score_pds', 0):.4f} "
            f"nmae={e.get('score_nmae', 0):.4f} mse={e.get('score_mse', 0):.4f} "
            f"fid={e.get('score_fid', 0):.4f}"
        )

    # Gap analysis: what do we need?
    if our:
        best_score = max(e["score_avg"] for _, e in our)
        gap = threshold - best_score
        print(
            f"\nGap to top-100: {gap:.4f} (our best: {best_score:.4f}, threshold: {threshold:.4f})"
        )

        # Component gap analysis
        best_entry = max(our, key=lambda x: x[1]["score_avg"])[1]
        thresh_entry = scored[top100_idx]
        print("\nComponent gaps (threshold - our best):")
        keys = ["score_pds", "score_mse", "score_nmae", "score_fid", "score_reach", "score_jac"]
        for key in keys:
            t = thresh_entry.get(key, 0) or 0
            o = best_entry.get(key, 0) or 0
            print(f"  {key:12s}: {t:.4f} - {o:.4f} = {t - o:+.4f}")

    # Score distribution
    print("\nScore distribution:")
    brackets = [0.3, 0.2, 0.15, 0.1, 0.05, 0.0, -0.05, -0.1]
    for i, b in enumerate(brackets):
        lower = brackets[i + 1] if i + 1 < len(brackets) else -999
        count = sum(1 for e in scored if lower <= e["score_avg"] < b)
        print(f"  [{lower:+.2f}, {b:+.2f}): {count}")
    neg = sum(1 for e in scored if e["score_avg"] < brackets[-1])
    print(f"  < {brackets[-1]:+.2f}: {neg}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--save", type=str, default=None, help="Save JSON to this path")
    args = parser.parse_args()

    print("Fetching leaderboard...", flush=True)
    data = fetch_leaderboard()

    if args.save:
        with open(args.save, "w") as f:
            json.dump(data, f)
        print(f"Saved to {args.save}")

    analyze(data)


if __name__ == "__main__":
    main()
