from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

axis = import_module("audit_gene_axis")
contract = import_module("check_cell_eval2_contract")


def test_aligned_axes_report_aligned():
    report = axis.build_report(["A", "B", "C"], {"src": ["C", "B", "A", "D"]})
    assert report["decision"] == "aligned"
    assert report["missing_from_source"] == {"src": []}
    assert report["extra_in_source"] == {"src": 1}
    assert report["resolutions"] == {}


def test_make_unique_artifact_is_flagged_not_mapped():
    consumer = ["HSPA14", "HSPA14-1", "TBCE", "X"]
    sources = {"src": ["HSPA14", "TBCE", "X"]}
    var = pd.DataFrame(
        {"gene_id": ["ENSG000001", "ENSG000002", "ENSG000003", "ENSG000004"]},
        index=consumer,
    )
    report = axis.build_report(consumer, sources, consumer_var=var)
    assert report["decision"] == "review_required"
    res = report["resolutions"]["HSPA14-1"]
    assert res["suffix_analysis"]["looks_like_make_unique_artifact"] is True
    assert res["suffix_analysis"]["base"] == "HSPA14"
    assert res["suffix_analysis"]["base_present_in_sources"] == ["src"]
    rules = {c["rule"] for c in res["candidates"]}
    assert {"suffix_base_map", "drop_from_diagnostic_axis", "stable_id_map"} <= rules
    mapping = [c for c in res["candidates"] if c["rule"] == "suffix_base_map"][0]
    assert mapping["confidence"] == "requires_verification"
    assert "distinct feature" in mapping["caveat"]
    assert res["var_rows"]["HSPA14-1"]["gene_id"] == "ENSG000002"
    assert res["var_rows"]["HSPA14"]["gene_id"] == "ENSG000001"
    assert report["labels_without_source_mapping"] == []


def test_suffix_alias_without_duplicate_gets_different_caveat():
    consumer = ["TMSB15B-1", "X"]
    report = axis.build_report(consumer, {"src": ["TMSB15B", "X"]})
    res = report["resolutions"]["TMSB15B-1"]
    assert res["suffix_analysis"]["looks_like_make_unique_artifact"] is False
    assert res["suffix_analysis"]["base_in_consumer_axis"] is False
    mapping = [c for c in res["candidates"] if c["rule"] == "suffix_base_map"][0]
    assert "not a duplicate-artifact" in mapping["caveat"]


def test_gene_with_no_candidate_is_unmappable():
    report = axis.build_report(["ZZZ", "X"], {"src": ["X"]})
    assert report["decision"] == "review_required"
    assert report["labels_without_source_mapping"] == ["ZZZ"]
    res = report["resolutions"]["ZZZ"]
    assert res["has_mapping_candidate"] is False
    assert {c["rule"] for c in res["candidates"]} == {
        "drop_from_diagnostic_axis",
        "stable_id_map",
    }


def test_missing_in_reference_is_recorded():
    report = axis.build_report(
        ["A-1", "B"],
        {"src": ["A", "B"]},
        references={"panel": ["A", "B", "C"]},
    )
    assert report["missing_in_references"] == {"A-1": []}
    assert report["missing_from_source"] == {"src": ["A-1"]}


def test_nonunique_axis_fails_closed():
    with pytest.raises(ValueError, match="unique"):
        axis.build_report(["A", "A"], {"src": ["A"]})


def test_apply_axis_mapping_exact_and_approved():
    source = ["A", "B", "C"]
    consumer = ["B", "A-1", "C"]
    cols = axis.apply_axis_mapping(source, consumer, {"A-1": "A"})
    assert cols == [1, 0, 2]
    with pytest.raises(ValueError, match="no approved source column"):
        axis.apply_axis_mapping(source, consumer, {})
    with pytest.raises(ValueError, match="outside the source axis"):
        axis.apply_axis_mapping(source, consumer, {"A-1": "QQ"})


def test_cli_end_to_end(tmp_path):
    import anndata as ad

    consumer = ad.AnnData(
        np.ones((3, 3)),
        var=pd.DataFrame(
            {"gene_id": ["ENSG1", "ENSG2", "ENSG3"]},
            index=["HSPA14", "HSPA14-1", "X"],
        ),
    )
    consumer_path = tmp_path / "consumer.h5ad"
    consumer.write_h5ad(consumer_path)
    source_path = tmp_path / "source.npz"
    np.savez(source_path, genes=np.array(["HSPA14", "X"]), other=np.array([1]))
    ref_path = tmp_path / "gene_names.csv"
    ref_path.write_text("gene_name\nHSPA14\nX\nY\n")
    out = tmp_path / "report.json"
    rc = axis.main(
        [
            "--consumer-h5ad",
            str(consumer_path),
            "--source-npz",
            str(source_path),
            "--reference-csv",
            str(ref_path),
            "--out",
            str(out),
        ]
    )
    assert rc == 2  # review_required
    report = json.loads(out.read_text())
    assert report["decision"] == "review_required"
    assert report["missing_from_source"] == {"source.npz": ["HSPA14-1"]}
    assert report["var_id_columns"]["gene_id"]["ensg_like_fraction"] == 1.0


def test_npz_without_genes_array_fails_closed(tmp_path):
    bad = tmp_path / "bad.npz"
    np.savez(bad, targets=np.array(["T"]), deltas=np.ones((1, 2)))
    with pytest.raises(ValueError, match="no 'genes'"):
        axis._read_npz_genes(bad)


def test_contract_fixture_is_counts_and_exercisable(tmp_path):
    fixture = contract.make_fixture(tmp_path, seed=1)
    import anndata as ad

    real = ad.read_h5ad(fixture["real"])
    pred = ad.read_h5ad(fixture["pred"])
    assert real.shape == (1200, 400) and pred.shape == (1200, 400)
    assert real.obs["target"].value_counts()["non-targeting"] == 600
    for t in fixture["targets"]:
        assert t in set(real.var_names)
        assert real.obs["target"].value_counts()[t] == 150
    assert np.all(np.asarray(real.X.todense()) == np.floor(np.asarray(real.X.todense())))
    assert np.all(np.asarray(real.X.todense()) >= 0)
