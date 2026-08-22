"""Tests for Observatory data loaders."""

from __future__ import annotations

from frontend.observatory import data as data_mod


def test_entity_model_label_finetuned() -> None:
    item = {"method": "pioneer", "model_id": "4225fc3e-3839-42fb-9cfb-e41d7c08dfe2"}
    assert data_mod.entity_model_label(item) == "fine-tuned LoRA"


def test_entity_model_label_base() -> None:
    item = {"method": "pioneer", "model_id": data_mod.PIONEER_BASE_MODEL}
    assert data_mod.entity_model_label(item) == "base GLiNER2"


def test_summarize_entity_extractions() -> None:
    items = [
        {
            "method": "pioneer",
            "model_id": "4225fc3e-3839-42fb-9cfb-e41d7c08dfe2",
            "entity_count": 3,
            "by_label": {"gene": ["ACTB"], "pathway": ["interferon", "JAK-STAT"]},
        },
        {
            "method": "pioneer",
            "model_id": "4225fc3e-3839-42fb-9cfb-e41d7c08dfe2",
            "entity_count": 2,
            "by_label": {"gene": ["GAPDH"], "cell_type": ["K562"]},
        },
    ]
    summary = data_mod.summarize_entity_extractions(items)
    assert summary["total_entities"] == 5
    assert summary["gene_count"] == 2
    assert summary["is_fine_tuned"] is True
    assert summary["label_totals"]["gene"] == 2
    assert summary["label_totals"]["pathway"] == 2
