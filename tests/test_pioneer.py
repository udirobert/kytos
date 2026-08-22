"""Tests for Pioneer GLiNER2 biomedical NER tool.

Must pass with NO Pioneer API key and NO billing — the fallback extractor
is deterministic (famile lesson: enrichment degrades, never blocks).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FIXTURE = ROOT / "tests" / "fixtures" / "k001-mean-shift-baseline"

sys.path.insert(0, str(TOOLS))

import pioneer_ner  # noqa: E402

SAMPLE_TEXT = (
    "CRISPRi knockdown of ACTB in K562 cells caused a 2.1 log2 fold-change "
    "shift in housekeeping genes including GAPDH. The interferon response "
    "pathway showed mixed directionality with ISG15 upregulated and IFIT1 "
    "downregulated. TP53 and MYC were unaffected. The cells showed signs of "
    "apoptosis and dna damage response activation."
)


def test_fallback_extracts_genes() -> None:
    entities = pioneer_ner.extract_entities_fallback(SAMPLE_TEXT)
    labels = {e["label"] for e in entities}
    assert "gene" in labels
    gene_texts = {e["text"] for e in entities if e["label"] == "gene"}
    assert "ACTB" in gene_texts
    assert "GAPDH" in gene_texts
    assert "ISG15" in gene_texts
    assert "TP53" in gene_texts


def test_fallback_extracts_pathways() -> None:
    entities = pioneer_ner.extract_entities_fallback(SAMPLE_TEXT)
    pathway_texts = {e["text"].lower() for e in entities if e["label"] == "pathway"}
    assert "interferon response" in pathway_texts
    assert "apoptosis" in pathway_texts


def test_fallback_extracts_perturbation_types() -> None:
    entities = pioneer_ner.extract_entities_fallback(SAMPLE_TEXT)
    ptype_texts = {e["text"] for e in entities if e["label"] == "perturbation_type"}
    assert "CRISPRi" in ptype_texts
    assert "knockdown" in ptype_texts


def test_fallback_deduplicates() -> None:
    text = "ACTB and ACTB and more ACTB"
    entities = pioneer_ner.extract_entities_fallback(text)
    gene_entities = [e for e in entities if e["label"] == "gene" and e["text"] == "ACTB"]
    assert len(gene_entities) == 1


def test_parse_pioneer_unified_result_map() -> None:
    resp = {
        "type": "encoder",
        "result": {
            "data": {
                "entities": {
                    "gene": [{"text": "ACTB", "confidence": 1.0, "start": 21, "end": 25}],
                    "pathway": [],
                    "cell_type": [
                        {"text": "K562 cells", "confidence": 0.99, "start": 29, "end": 39}
                    ],
                }
            }
        },
    }
    entities = pioneer_ner.parse_pioneer_inference_response(resp)
    assert len(entities) == 2
    labels = {e["label"] for e in entities}
    assert labels == {"gene", "cell_type"}
    assert entities[0]["text"] == "ACTB"
    assert entities[0]["score"] == 1.0


def test_parse_pioneer_legacy_string_map() -> None:
    resp = {
        "result": {
            "entities": {
                "gene": ["ACTB", "GAPDH"],
                "pathway": ["interferon response"],
            }
        }
    }
    entities = pioneer_ner.parse_pioneer_inference_response(resp)
    assert len(entities) == 3
    gene_texts = {e["text"] for e in entities if e["label"] == "gene"}
    assert gene_texts == {"ACTB", "GAPDH"}


def test_parse_pioneer_legacy_span_list() -> None:
    resp = {
        "entities": [
            {"text": "ACTB", "label": "gene", "start": 10, "end": 14, "score": 0.91},
            {"text": "CRISPRi", "label": "perturbation_type", "start": 0, "end": 7},
        ]
    }
    entities = pioneer_ner.parse_pioneer_inference_response(resp)
    assert len(entities) == 2
    assert entities[0]["text"] == "ACTB"
    assert entities[0]["score"] == 0.91


def test_entity_schema_uses_named_entities() -> None:
    schema = pioneer_ner._entity_schema()
    assert schema["entities"][0] == {"name": "gene"}
    assert all("name" in item for item in schema["entities"])


def test_extract_entities_uses_fallback_without_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIONEER_API_KEY", raising=False)
    entities, method = pioneer_ner.extract_entities(SAMPLE_TEXT, model_id=None)
    assert method == "fallback"
    assert len(entities) > 0


@pytest.fixture()
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("PIONEER_API_KEY", raising=False)
    dest = tmp_path / "k001-mean-shift-baseline"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_enrich_literature_entities_writes_output(run_dir: Path) -> None:
    count = pioneer_ner.enrich_literature_entities(run_dir, model_id=None)
    assert count >= 1

    entities_path = run_dir / "literature" / "ACTB.entities.json"
    assert entities_path.is_file()

    payload = json.loads(entities_path.read_text(encoding="utf-8"))
    assert payload["method"] == "fallback"
    assert payload["entity_count"] > 0
    assert "gene" in payload["by_label"]

    gene_texts = payload["by_label"]["gene"]
    assert "ACTB" in gene_texts
    assert "ISG15" in gene_texts


def test_enrich_skips_existing_entities_files(run_dir: Path) -> None:
    # First pass creates .entities.json
    pioneer_ner.enrich_literature_entities(run_dir, model_id=None)
    # Second pass should skip the .entities.json file
    count = pioneer_ner.enrich_literature_entities(run_dir, model_id=None)
    # Should still process the original ACTB.json but skip ACTB.entities.json
    assert count >= 1


def test_enrich_handles_no_literature_dir(tmp_path: Path) -> None:
    count = pioneer_ner.enrich_literature_entities(tmp_path, model_id=None)
    assert count == 0
