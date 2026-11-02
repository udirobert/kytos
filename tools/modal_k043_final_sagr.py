"""Modal k043 job: final-phase (Oct-22 test set) sagr consensus submission.

Ship recipe: ``consensus_w_ctr_sagr`` deltas through the unchanged champion
dual-moment generator (amplitude 1.0, bulk_amplitude 0.5, pool_k 4,
bulk_delta space, seed 0, 400 cells/pert) — the exact k040 mechanism,
re-targeted at the final panel (contexts D/E/F, panel vcc2026-test-1).

Differences vs ``modal_k034_final_submit.py``:

- dataset ``controls-final`` (D/E/F), not a placeholder id;
- deltas = ``variant_consensus_w_ctr_sagr.npz`` built fresh for the FINAL
  300-target panel — the validation-panel artifact at
  /kytos-vol/k035-machinery/ is for the OLD 343-target list and must NOT be
  shipped (171/300 final targets differ);
- sources restricted to the four champion WEIGHTED arms (k562, hct116,
  hek293t, cd4). Jurkat is deliberately absent — consensus_delta defaults
  unlisted sources to weight 1.0 and k030 showed adding Jurkat regressed;
- ``vcc-cli==0.3.0`` pinned everywhere (final submissions reject older
  CLIs; 0.3.0 resolves contexts from the controls bundle's manifest.json,
  and --contexts D,E,F is still passed explicitly as a guard);
- sagr shrinkage reads genome-wide stats from /kytos-vol/k036-samplestats.

Stages (each idempotent, artifacts persist to /kytos-vol/k043-final/):

  modal run tools/modal_k043_final_sagr.py::audit_final_coverage
  modal run tools/modal_k043_final_sagr.py::build_final_deltas
  modal run -d tools/modal_k043_final_sagr.py::build_and_prep
  modal run -d tools/modal_k043_final_sagr.py::submit_from_volume   # approval only
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import modal

app = modal.App("kytos-k043-final-sagr")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = Path("/root/kytos")
VOL_OUT = "/kytos-vol/k043-final"
TAG = "k043-final-sagr-dm"
MODEL_NAME = "kytos-k043-final-sagr-dm"

# The four champion WEIGHTED sources only. Order does not matter; the
# subsetter emits all sources on the same final-target order.
SOURCE_NPZ = {
    "k562": "/kytos-vol/k034-final-prep/k034-k562-all/deltas_k562.npz",
    "hct116": "/kytos-vol/k034-final-prep/k034-hct116-all/deltas_hct116.npz",
    "hek293t": "/kytos-vol/k034-final-prep/k034-hek293t-all/deltas_hek293t.npz",
    "cd4": "/kytos-vol/k034-final-prep/k034-cd4-all/deltas_cd4.npz",
}
STATS_DIR = "/kytos-vol/k036-samplestats"

build_image = (
    modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli==0.3.0", "anndata", "scanpy", "numpy", "pandas", "scipy")
    .add_local_dir(LOCAL_ROOT / "src/kytos", str(REMOTE_ROOT / "src/kytos"), copy=True)
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k007_neighbor_prior.py"),
        str(REMOTE_ROOT / "tools/run_k007_neighbor_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k005_atlas_prior.py"),
        str(REMOTE_ROOT / "tools/run_k005_atlas_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k006_replogle_prior.py"),
        str(REMOTE_ROOT / "tools/run_k006_replogle_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/perturbation_priors.py"),
        str(REMOTE_ROOT / "tools/perturbation_priors.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k027_dual_moment_submit.py"),
        str(REMOTE_ROOT / "tools/run_k027_dual_moment_submit.py"),
        copy=True,
    )
)

consensus_image = (
    modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli==0.3.0", "numpy", "pandas")
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
    .add_local_file(
        str(LOCAL_ROOT / "tools/subset_deltas_npz.py"),
        str(REMOTE_ROOT / "tools/subset_deltas_npz.py"),
        copy=True,
    )
)


def _run_step(name: str, cmd: str, check: bool = True) -> int:
    print(f"\n=== {name} ===", flush=True)
    result = subprocess.run(
        ["bash", "-c", f"set -ex\n{cmd}"],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {result.returncode}")
    return result.returncode


def _download_final_controls(raw_dir: str) -> None:
    """Fetch controls-final and unpack so manifest.json sits beside the CSVs."""
    _run_step(
        "download controls-final",
        f"vcc datasets download controls-final -d {raw_dir}\n"
        f"cd {raw_dir}\n"
        "unzip -q -o vcc_2026_controls_final.zip -d .\n"
        "ls -lh",
    )


@app.function(
    image=consensus_image,
    timeout=60 * 60,
    memory=32 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def audit_final_coverage() -> dict:
    """Verify every staged artifact covers the FINAL panel before building.

    Cheap read of npz target/coverage arrays and sagr stats indexes — the
    only gate that decides whether the ship recipe is buildable.
    """
    raw_dir = "/root/final-controls"
    _run_step("mkdir", f"mkdir -p {raw_dir}")
    _download_final_controls(raw_dir)

    audit = (
        "import csv, json\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        "raw = Path('%s')\n"
        "genes = [r[0] for r in csv.reader(open(raw/'gene_names.csv'))][1:]\n"
        "targets = [r[0] for r in csv.reader(open(raw/'pert_counts.csv'))][1:]\n"
        "manifest = json.load(open(raw/'manifest.json'))\n"
        "report = {'manifest': manifest, 'n_genes': len(genes),\n"
        "          'n_targets': len(targets), 'sources': {}}\n"
        "paths = %r\n"
        "for name, p in paths.items():\n"
        "    with np.load(p, allow_pickle=False) as d:\n"
        "        g = d['genes'].astype(str).tolist()\n"
        "        ts = d['targets'].astype(str).tolist()\n"
        "        cov = (d['covered'].astype(bool) if 'covered' in d.files\n"
        "               else np.ones(len(ts), bool))\n"
        "    covered = {t for t, c in zip(ts, cov) if c}\n"
        "    present = {t for t in targets} & set(ts)\n"
        "    report['sources'][name] = {\n"
        "        'gene_axis_exact': g == genes, 'n_source_targets': len(ts),\n"
        "        'final_present': len(present), 'final_covered': len(set(targets) & covered),\n"
        "        'missing': sorted(set(targets) - covered),\n"
        "    }\n"
        "for name in ('hct116', 'hek293t'):\n"
        "    p = f'%s/{name}_samplestats.npz'\n"
        "    with np.load(p, allow_pickle=False) as d:\n"
        "        st = d['targets'].astype(str).tolist()\n"
        "        nv = d['n_samples_voting']\n"
        "        report['sources'][name]['stats_targets'] = len(st)\n"
        "        report['sources'][name]['stats_cover_final'] = len(set(targets) & set(st))\n"
        "        sg = int(len(d['genes'])) if 'genes' in d.files else None\n"
        "        report['sources'][name]['stats_genes'] = sg\n"
        "        idx = [st.index(t) for t in targets if t in st]\n"
        "        if idx:\n"
        "            mv = float(np.median(nv[idx]))\n"
        "            report['sources'][name]['stats_median_voting_final'] = mv\n"
        "Path('%s').mkdir(parents=True, exist_ok=True)\n"
        "Path('%s/coverage_report.json').write_text(json.dumps(report, indent=2))\n"
        "print(json.dumps(report, indent=2))\n"
    ) % (raw_dir, SOURCE_NPZ, STATS_DIR, VOL_OUT, VOL_OUT)
    _run_step("audit coverage", f'python -c "{audit}"')

    import json as _json

    return _json.loads(Path(f"{VOL_OUT}/coverage_report.json").read_text())


@app.function(
    image=consensus_image,
    timeout=60 * 60 * 2,
    memory=32 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def build_final_deltas(force: bool = False) -> dict:
    """Subset the four genome-wide sources to the final panel, then build
    variant_consensus_w_ctr_sagr.npz on the new target order."""
    raw_dir = "/root/final-controls"
    src_dir = f"{VOL_OUT}/src"
    var_dir = f"{VOL_OUT}/machinery"
    _run_step("mkdir", f"mkdir -p {raw_dir} {src_dir} {var_dir}")
    _download_final_controls(raw_dir)

    subset_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "python tools/subset_deltas_npz.py \\\n"
        f"  --in {SOURCE_NPZ['k562']} {SOURCE_NPZ['hct116']} "
        f"{SOURCE_NPZ['hek293t']} {SOURCE_NPZ['cd4']} \\\n"
        f"  --targets-file {raw_dir}/pert_counts.csv \\\n"
        f"  --out-dir {src_dir}\n"
        f"cat {src_dir}/subset_report.json"
    )
    _run_step("subset sources to final panel", subset_cmd)

    build_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "python tools/build_consensus_deltas_v3.py \\\n"
        f"  --src-dir {src_dir} \\\n"
        f"  --stats-dir {STATS_DIR} \\\n"
        f"  --out-dir {var_dir}"
        + (" --force" if force else "")
        + f"\ncat {var_dir}/build_manifest_v3.json\n"
        f"sha256sum {var_dir}/variant_consensus_w_ctr_sagr.npz"
    )
    _run_step("build sagr consensus", build_cmd)
    vol.commit()

    import hashlib
    import json as _json

    vpath = Path(f"{var_dir}/variant_consensus_w_ctr_sagr.npz")
    return {
        "status": "ok",
        "variant": str(vpath),
        "sha256": hashlib.sha256(vpath.read_bytes()).hexdigest(),
        "manifest": _json.loads((Path(var_dir) / "build_manifest_v3.json").read_text()),
    }


@app.function(
    image=build_image,
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def build_and_prep(
    contexts: str = "D,E,F",
    cells_per_pert: int = 400,
    seed: int = 0,
    amplitude: float = 1.0,
    bulk_amplitude: float = 0.5,
    prep_dry_run: bool = False,
) -> dict:
    """Generate prediction.h5ad on the final controls, run vcc prep (0.3.0),
    persist the .vcc to the volume."""
    t_start = time.time()
    raw_dir = f"{REMOTE_ROOT}/data/raw/{TAG}"
    out_dir = f"{REMOTE_ROOT}/experiments/{TAG}"
    deltas_remote = "/root/deltas.npz"

    _run_step("mkdir", f"mkdir -p {raw_dir} {out_dir}")
    _download_final_controls(raw_dir)

    _run_step(
        "assert CLI 0.3.0",
        "vcc --version | tee /dev/stderr | grep -q 'vcc 0\\.3\\.0'",
    )

    deltas_vol = f"{VOL_OUT}/machinery/variant_consensus_w_ctr_sagr.npz"
    _run_step("stage deltas", f"cp {deltas_vol} {deltas_remote}\nls -lh {deltas_remote}")

    build_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "python tools/run_k027_dual_moment_submit.py \\\n"
        f"  --raw-dir {raw_dir} \\\n"
        f"  --deltas-npz {deltas_remote} \\\n"
        f"  --out-dir {out_dir} \\\n"
        f"  --contexts {contexts} \\\n"
        f"  --amplitude {amplitude} \\\n"
        f"  --bulk-amplitude {bulk_amplitude} \\\n"
        f"  --cells-per-pert {cells_per_pert} \\\n"
        f"  --seed {seed} \\\n"
        f"  --run-id {TAG}"
    )
    _run_step("build dual-moment prediction", build_cmd)

    vcc_path = f"{out_dir}/prediction.prep.vcc"
    # CLI 0.3.0 reads contexts from manifest.json beside --perts; passing
    # --contexts anyway keeps the intended panel explicit and fails fast on
    # a wrong-bundle accident.
    prep_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "vcc prep \\\n"
        f"  -g {raw_dir}/gene_names.csv \\\n"
        f"  --perts {raw_dir}/pert_counts.csv \\\n"
        f"  --contexts {contexts} \\\n"
        f"  -o {vcc_path} \\\n"
        f"  {'--dry-run ' if prep_dry_run else ''}"
        f"  {out_dir}/prediction.h5ad"
    )
    _run_step("vcc prep", prep_cmd)

    if not prep_dry_run:
        persist_cmd = (
            f"mkdir -p {VOL_OUT}\n"
            f"cp {vcc_path} {VOL_OUT}/prediction.prep.vcc\n"
            f"cp {out_dir}/meta.json {VOL_OUT}/meta.json\n"
            f"sha256sum {vcc_path} | tee {VOL_OUT}/prediction.prep.vcc.sha256\n"
            f"ls -lh {VOL_OUT}"
        )
        _run_step("persist .vcc to Modal Volume", persist_cmd)
        vol.commit()

    return {
        "status": "ok",
        "elapsed_s": time.time() - t_start,
        "out_dir": out_dir,
        "vcc_path": None if prep_dry_run else vcc_path,
        "volume_path": VOL_OUT,
        "contexts": contexts,
        "dry_run": prep_dry_run,
        "model_name": MODEL_NAME,
    }


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli==0.3.0"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume() -> dict:
    """Submit the persisted .vcc — CALL ONLY AFTER EXPLICIT USER APPROVAL."""
    vcc_path = f"{VOL_OUT}/prediction.prep.vcc"
    print(f"submitting {vcc_path}", flush=True)
    result = subprocess.run(
        ["vcc", "submit", vcc_path, "--model-name", MODEL_NAME, "--wait"],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"status": "ok", "returncode": result.returncode}
