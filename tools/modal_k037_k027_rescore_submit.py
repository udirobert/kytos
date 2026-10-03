"""Modal k037 job: re-score the k027 champion bundle for per-component officials.

Why this job exists
-------------------
`kytos-k027-consensus-dm` (+0.1262) is the champion by score, but its
per-component scores were never captured: the entry was purged from the API
before they could be read. Every component verdict since -- k028, k029, k030,
k034, k035 -- has been measured against confounded baselines (k034 is
uncentered, k030 adds a Jurkat source), each differing from k027 in more than
the variable being interpreted. This job supplies the missing unconfounded
baseline.

The champion's packaged `.vcc` is still on the volume at
`/kytos-vol/k027-consensus-dm/prediction.prep.vcc`, timestamped
2026-09-22T13:56Z -- the exact artifact that scored +0.1262. Submitting that
bundle is strictly better than rebuilding it: the input is byte-identical by
construction, so any score movement is attributable entirely to scorer or
panel drift rather than build nondeterminism (and it avoids the ~29 GB
`vcc prep` peak that killed the equivalent rebuild on the 31 GB VPS).

A distinct model name keeps this probe distinguishable from the champion
entry on the leaderboard.

Pre-declared predictions (written before submit, as the protocol requires):
experiments/_embargoed/k037-k027-rescore-predeclared.md

Run:
  modal run --detach tools/modal_k037_k027_rescore_submit.py::submit_rescore
"""

from __future__ import annotations

import subprocess

import modal

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

CHAMPION_VCC = "/kytos-vol/k027-consensus-dm/prediction.prep.vcc"
MODEL_NAME = "kytos-k037-k027-rescore"

app = modal.App("kytos-k037-k027-rescore")


@app.function(
    image=modal.Image.debian_slim().pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_rescore() -> dict:
    print(f"submitting {CHAMPION_VCC} as {MODEL_NAME}", flush=True)
    result = subprocess.run(
        ["vcc", "submit", CHAMPION_VCC, "--model-name", MODEL_NAME, "--wait"],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"status": "ok" if result.returncode == 0 else "failed", "returncode": result.returncode}
