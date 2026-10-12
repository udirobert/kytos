"""Modal k040 step 1: build sagr consensus variants on the volume.

Runs tools/build_consensus_deltas_v3.py inside Modal so the k036
per-sample vote stores (genome-wide, ~3 GB each) never leave the volume:
src deltas from /kytos-vol/k035-src, stats from /kytos-vol/k036-samplestats,
variants written to /kytos-vol/k035-machinery.

Cheap CPU step (~16 GB peak: pos/neg int16 loads per arm).

Run:
  modal run tools/modal_k040_sagr_build.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import modal

app = modal.App("kytos-k040-sagr-build")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = Path("/root/kytos")

image = (
    modal.Image.debian_slim()
    .pip_install("numpy")
    .add_local_file(
        str(LOCAL_ROOT / "tools/consensus_deltas.py"),
        str(REMOTE_ROOT / "tools/consensus_deltas.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/build_consensus_deltas.py"),
        str(REMOTE_ROOT / "tools/build_consensus_deltas.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/build_consensus_deltas_v2.py"),
        str(REMOTE_ROOT / "tools/build_consensus_deltas_v2.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/build_consensus_deltas_v3.py"),
        str(REMOTE_ROOT / "tools/build_consensus_deltas_v3.py"),
        copy=True,
    )
)


@app.function(
    image=image,
    timeout=60 * 60,
    memory=16 * 1024,
    cpu=2,
    volumes={"/kytos-vol": vol},
)
def build(force: bool = False) -> dict:
    cmd = [
        "python",
        "tools/build_consensus_deltas_v3.py",
        "--src-dir",
        "/kytos-vol/k035-src",
        "--stats-dir",
        "/kytos-vol/k036-samplestats",
        "--out-dir",
        "/kytos-vol/k035-machinery",
    ]
    if force:
        cmd.append("--force")
    r = subprocess.run(cmd, cwd=str(REMOTE_ROOT), capture_output=True, text=True)
    print(r.stdout)
    print(r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"build failed: {r.returncode}")
    return {"status": "ok"}


@app.local_entrypoint()
def main(force: bool = False):
    print(build.remote(force=force))
