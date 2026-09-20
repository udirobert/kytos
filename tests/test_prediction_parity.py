from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

k006 = import_module("run_k006_replogle_prior")
k007 = import_module("run_k007_neighbor_prior")
k011 = import_module("run_k011_delta_scale")
k014 = import_module("run_k014_trained_model")

GENES = ["G0", "G1", "G2", "G3", "G4"]
TARGETS = GENES[:3]
PRIOR = np.array([-0.4, 0.15, 0.0, 0.0, 0.0], dtype=np.float32)


def save_artifact(
    path, *, genes=GENES, contexts=("A",), targets=("G0",), deltas=None, mask=None, **extra
):
    if deltas is None:
        deltas = PRIOR[None, None, :]
    if mask is None:
        mask = np.ones((len(contexts), len(targets)), dtype=bool)
    payload = dict(
        gene_names=np.asarray(genes),
        contexts=np.asarray(contexts),
        vcc_targets=np.asarray(targets),
        deltas=deltas,
        coverage_mask=mask,
        effect_space=np.array("additive_log1p"),
        schema_version=np.array(1),
    )
    payload.update(extra)
    np.savez_compressed(path, **payload)
    return path


@pytest.fixture
def panel(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame({"gene": GENES}).to_csv(raw / "gene_names.csv", index=False)
    pd.DataFrame({"target": TARGETS}).to_csv(raw / "pert_counts.csv", index=False)
    for ci, context in enumerate("ABC"):
        x = np.random.default_rng(ci).poisson(12 + ci, size=(24, len(GENES)))
        ad.AnnData(sparse.csr_matrix(x), var=pd.DataFrame(index=GENES)).write_h5ad(
            raw / f"context_{context}.h5ad"
        )
    source = tmp_path / "source.h5ad"
    source.touch()
    neighbor = tmp_path / "neighbors.json"
    neighbor.write_text("{}")
    priors = {"G0": PRIOR.copy()}
    monkeypatch.setattr(k006, "build_combined_deltas", lambda *a, **kw: priors)
    monkeypatch.setattr(k014, "build_combined_deltas", lambda *a, **kw: priors)
    monkeypatch.setattr(
        k007,
        "build_neighbor_deltas",
        lambda *a, **kw: {"G1": np.array([0.0, -0.5, 0.1, 0.0, 0.0], dtype=np.float32)},
    )
    common = [
        "--raw-dir",
        str(raw),
        "--replogle-src",
        str(source),
        "--neighbor-map",
        str(neighbor),
        "--cells-per-pert",
        "7",
        "--seed",
        "19",
        "--delta-scale",
        "1.7",
        "--kd-std",
        "2.0",
    ]
    return tmp_path, common, priors


def render_pair(panel, artifact):
    root, common, _ = panel
    champion_dir = root / "champion"
    candidate_dir = root / "candidate"
    assert k011.main(common + ["--out-dir", str(champion_dir)]) == 0
    assert k014.main(common + ["--out-dir", str(candidate_dir), "--deltas", str(artifact)]) == 0
    return (
        ad.read_h5ad(champion_dir / "prediction.h5ad"),
        ad.read_h5ad(candidate_dir / "prediction.h5ad"),
    )


@pytest.mark.parametrize("covered", [False, True])
def test_noop_matches_champion_exactly(panel, covered):
    root, _, priors = panel
    artifact = save_artifact(root / "deltas.npz", mask=np.array([[covered]]))
    baseline, candidate = render_pair(panel, artifact)
    np.testing.assert_array_equal(baseline.X.toarray(), candidate.X.toarray())
    pd.testing.assert_frame_equal(baseline.obs, candidate.obs)
    np.testing.assert_array_equal(priors["G0"], PRIOR)


def test_a_override_preserves_b_c_and_uncovered_a_targets(panel):
    root, _, priors = panel
    artifact = save_artifact(root / "deltas.npz", deltas=np.array([[[1.0, -0.4, 0.3, 0, 0]]]))
    baseline, candidate = render_pair(panel, artifact)
    changed = (
        (baseline.obs[k014.CONTEXT_COL] == "A") & (baseline.obs[k014.PERT_COL] == "G0")
    ).to_numpy()
    np.testing.assert_array_equal(baseline.X[~changed].toarray(), candidate.X[~changed].toarray())
    assert not np.array_equal(baseline.X[changed].toarray(), candidate.X[changed].toarray())
    np.testing.assert_array_equal(priors["G0"], PRIOR)


def test_gene_axis_is_remapped_by_name(tmp_path):
    order = [2, 4, 0, 3, 1]
    artifact = save_artifact(
        tmp_path / "deltas.npz", genes=[GENES[i] for i in order], deltas=PRIOR[order][None, None, :]
    )
    loaded, _, _, _ = k014.load_trained_deltas(artifact, GENES)
    np.testing.assert_array_equal(loaded["A"]["G0"], PRIOR)


@pytest.mark.parametrize(
    "field,value",
    [
        ("gene_names", np.array(["G0", "G1", "G2", "G3", "G3"])),
        ("gene_names", np.array(["G0", "G1", "G2", "G3", "UNKNOWN"])),
        ("contexts", np.array(["A", "A"])),
        ("contexts", np.array(["D"])),
        ("vcc_targets", np.array(["G0", "G0"])),
        ("deltas", np.zeros((1, 1, 4))),
        ("deltas", np.full((1, 1, 5), np.nan)),
        ("deltas", np.full((1, 1, 5), np.inf)),
        ("coverage_mask", np.array([[1]], dtype=np.int64)),
        ("coverage_mask", np.array([True])),
        ("effect_space", np.array("log2fc")),
        ("schema_version", np.array(2)),
    ],
)
def test_rejects_ambiguous_or_invalid_artifacts(tmp_path, field, value):
    artifact = save_artifact(tmp_path / "invalid.npz", **{field: value})
    with pytest.raises(ValueError):
        k014.load_trained_deltas(artifact, GENES)


def test_legacy_unlabelled_artifact_is_rejected(tmp_path):
    path = tmp_path / "legacy.npz"
    np.savez(
        path,
        contexts=np.array(["A"]),
        vcc_targets=np.array(["G0"]),
        deltas=PRIOR[None, None, :],
        coverage_mask=np.array([[True]]),
    )
    with pytest.raises(ValueError, match="gene_names|schema|metadata"):
        k014.load_trained_deltas(path, GENES)


def test_unexpected_target_is_rejected_before_generation(panel):
    root, common, _ = panel
    artifact = save_artifact(root / "unknown.npz", targets=("NOT_IN_PANEL",))
    with pytest.raises(ValueError, match="target"):
        k014.main(common + ["--out-dir", str(root / "candidate"), "--deltas", str(artifact)])
    assert not (root / "candidate" / "prediction.h5ad").exists()


def test_prediction_manifest_records_dispatch_and_hashes(panel):
    import json

    root, _, _ = panel
    render_pair(panel, save_artifact(root / "deltas.npz"))
    meta = json.loads((root / "candidate" / "meta.json").read_text())
    assert meta["override_counts"] == {"A": 1, "B": 0, "C": 0}
    assert meta["dispatch_by_context"]["C"] == {"real": 1, "neighbor": 1, "fallback": 1}
    assert meta["effect_space"] == "additive_log1p"
    for value in meta["input_hashes"].values():
        assert len(value) == 64
    assert "context_C" in meta["input_hashes"]
    assert "run_k007_neighbor_prior.py" in meta["code_hashes"]
    assert "layer_b.py" in meta["code_hashes"]


def test_existing_input_staging_directory_is_allowed(panel):
    root, common, _ = panel
    out = root / "staged"
    out.mkdir()
    artifact = save_artifact(out / "prediction_deltas.npz")
    before = artifact.read_bytes()
    assert k014.main(common + ["--out-dir", str(out), "--deltas", str(artifact)]) == 0
    assert (out / "prediction.h5ad").exists()
    assert artifact.read_bytes() == before


def test_existing_prediction_is_never_overwritten(panel):
    root, common, _ = panel
    out = root / "existing"
    out.mkdir()
    saved = out / "prediction.h5ad"
    saved.write_bytes(b"existing prediction")
    artifact = save_artifact(root / "deltas.npz")
    with pytest.raises(FileExistsError):
        k014.main(common + ["--out-dir", str(out), "--deltas", str(artifact)])
    assert saved.read_bytes() == b"existing prediction"
