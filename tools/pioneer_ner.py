"""Pioneer GLiNER2 biomedical NER — extract entities from literature results.

Fine-tunes a GLiNER2 encoder model on Pioneer to extract biomedical entities
(gene, pathway, disease, perturbation_type, drug, protein, cell_type,
biological_process) from Tavily literature search results. This replaces a
general-purpose LLM call with a deterministic 205M model — no hallucinated
gene names, which is critical for a biology audit project.

Pipeline (when PIONEER_API_KEY is set and billing is active):
  1. Generate synthetic training data (POST /generate, task_type=ner)
  2. Fine-tune fastino/gliner2-base-v1 on the dataset (POST /felix/training-jobs)
  3. Poll until complete, then run inference on literature/*.json snippets
  4. Write extracted entities into literature/<gene>.entities.json

Degradation (famile lesson): no key, no billing, or API failure → fall back to a
deterministic regex-based extractor using known gene sets from audit flags.
The site builds without Pioneer; the literature rail still gets entity highlights.

Side challenge fit (Pioneer — Best Use of Pioneer):
  - Fine-tuned model replaces a general-purpose LLM API call (GPT-4o) for NER
  - Deterministic outputs: no hallucinated gene names (critical for biology)
  - 205M model runs on CPU; could be downloaded and run locally post-hackathon

Usage:
    # Full pipeline: train + inference
    python tools/pioneer_ner.py --run experiments/k001-mean-shift-baseline

    # Inference only (skip training; use base or previously-trained model)
    python tools/pioneer_ner.py --run experiments/k001-mean-shift-baseline --skip-train

    # Train only (generate data + fine-tune; no inference)
    python tools/pioneer_ner.py --train-only
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from _enrich_common import env_key, notice, resolve_run_dir, warn

PIONEER_BASE = "https://api.pioneer.ai"
BASE_MODEL = "fastino/gliner2-base-v1"
DATASET_NAME = "kytos-bio-ner"
MODEL_NAME = "kytos-bio-ner-v1"
NUM_EXAMPLES = 200
NUM_EPOCHS = 5
LEARNING_RATE = 5e-5
POLL_INTERVAL = 30  # seconds between training job status checks
POLL_TIMEOUT = 1800  # 30 min max wait for training

# Entity types the model extracts from biomedical literature
ENTITY_TYPES = [
    "gene",
    "pathway",
    "disease",
    "perturbation_type",
    "drug",
    "protein",
    "cell_type",
    "biological_process",
]

DOMAIN_DESCRIPTION = (
    "CRISPRi perturbation biology and single-cell genomics literature. "
    "Texts describe gene knockdown experiments, perturbation responses, "
    "pathway analysis, gene expression changes in cell lines, and biological "
    "audit of computational predictions. Examples include descriptions of "
    "housekeeping gene shifts, interferon pathway coherence, CRISPRi knockdown "
    "effects, and differential expression analysis."
)


# --------------------------------------------------------------------------- #
# Pioneer API client (stdlib only — no third-party deps)
# --------------------------------------------------------------------------- #


def _pioneer_headers() -> dict[str, str]:
    key = env_key("PIONEER_API_KEY")
    if not key:
        raise RuntimeError("PIONEER_API_KEY not set")
    return {"X-API-Key": key, "Content-Type": "application/json"}


def _pioneer_post(path: str, body: dict) -> dict:
    import urllib.request

    url = f"{PIONEER_BASE}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_pioneer_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pioneer_get(path: str) -> dict:
    import urllib.request

    url = f"{PIONEER_BASE}{path}"
    req = urllib.request.Request(url, headers=_pioneer_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_billing() -> bool:
    """Quick probe — does inference work, or is billing blocked?"""
    import urllib.request

    try:
        url = f"{PIONEER_BASE}/inference"
        body = json.dumps(
            {
                "model_id": BASE_MODEL,
                "text": "test",
                "schema": {"entities": ["gene"]},
                "threshold": 0.5,
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=_pioneer_headers(), method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Training pipeline
# --------------------------------------------------------------------------- #


def generate_dataset() -> str | None:
    """Start synthetic data generation; return job_id or None on failure."""
    try:
        result = _pioneer_post(
            "/generate",
            {
                "task_type": "ner",
                "dataset_name": DATASET_NAME,
                "labels": ENTITY_TYPES,
                "num_examples": NUM_EXAMPLES,
                "domain_description": DOMAIN_DESCRIPTION,
            },
        )
        job_id = result.get("job_id")
        notice(f"pioneer: synthetic data generation started — job_id={job_id}")
        return job_id
    except Exception as exc:
        warn(f"pioneer: data generation failed ({exc})")
        return None


def poll_generation(job_id: str, timeout: int = 600) -> bool:
    """Poll generation job until ready or failed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = _pioneer_get(f"/generate/jobs/{job_id}")
            status = result.get("status", "unknown")
            count = result.get("count", 0)
            notice(f"pioneer: generation status={status} count={count}")
            if status == "ready":
                return True
            if status == "failed":
                warn(f"pioneer: generation failed — {result.get('error', 'unknown')}")
                return False
        except Exception as exc:
            warn(f"pioneer: poll error ({exc}); retrying")
        time.sleep(15)
    warn("pioneer: generation timed out")
    return False


def start_training() -> str | None:
    """Submit a fine-tuning job; return job_id or None on failure."""
    try:
        result = _pioneer_post(
            "/felix/training-jobs",
            {
                "model_name": MODEL_NAME,
                "base_model": BASE_MODEL,
                "datasets": [{"name": DATASET_NAME}],
                "training_type": "lora",
                "nr_epochs": NUM_EPOCHS,
                "learning_rate": LEARNING_RATE,
            },
        )
        job_id = result.get("id")
        notice(f"pioneer: training job started — id={job_id}")
        return job_id
    except Exception as exc:
        warn(f"pioneer: training job failed ({exc})")
        return None


def poll_training(job_id: str, timeout: int = POLL_TIMEOUT) -> str | None:
    """Poll training job until complete; return model_id (job_id) or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = _pioneer_get(f"/felix/training-jobs/{job_id}")
            status = result.get("status", "unknown")
            notice(f"pioneer: training status={status}")
            if status == "complete":
                metrics = result.get("metrics") or {}
                notice(
                    f"pioneer: training complete — "
                    f"f1={metrics.get('f1', '?')} "
                    f"precision={metrics.get('precision', '?')} "
                    f"recall={metrics.get('recall', '?')}"
                )
                return job_id
            if status == "failed":
                warn("pioneer: training failed")
                return None
        except Exception as exc:
            warn(f"pioneer: training poll error ({exc}); retrying")
        time.sleep(POLL_INTERVAL)
    warn("pioneer: training timed out")
    return None


def run_training_pipeline() -> str | None:
    """Full pipeline: generate data → train → return model_id. Returns None on any failure."""
    key = env_key("PIONEER_API_KEY")
    if not key:
        warn("pioneer: PIONEER_API_KEY not set; skipping training")
        return None

    if not _check_billing():
        warn("pioneer: billing not set up (visit agent.pioneer.ai/billing); skipping training")
        return None

    # Step 1: generate synthetic data
    gen_job = generate_dataset()
    if not gen_job:
        return None
    if not poll_generation(gen_job):
        return None

    # Step 2: start training
    train_job = start_training()
    if not train_job:
        return None

    # Step 3: poll until complete
    model_id = poll_training(train_job)
    return model_id


# --------------------------------------------------------------------------- #
# Inference: extract entities from literature using fine-tuned model
# --------------------------------------------------------------------------- #


def extract_entities_pioneer(text: str, model_id: str) -> list[dict]:
    """Run GLiNER2 inference to extract biomedical entities from text."""
    try:
        result = _pioneer_post(
            "/inference",
            {
                "model_id": model_id,
                "text": text[:4000],  # cap input length
                "schema": {"entities": ENTITY_TYPES},
                "threshold": 0.35,
            },
        )
        # Response shape: {"entities": [{"text": "ACTB", "label": "gene", "score": 0.92}, ...]}
        entities = result.get("entities") or result.get("predictions") or []
        return [
            {
                "text": e.get("text", ""),
                "label": e.get("label", ""),
                "score": round(float(e.get("score", 0)), 3),
            }
            for e in entities
            if e.get("text")
        ]
    except Exception as exc:
        warn(f"pioneer: inference failed ({exc})")
        return []


# --------------------------------------------------------------------------- #
# Fallback: deterministic regex-based entity extraction (no API)
# --------------------------------------------------------------------------- #

# Known gene symbols from audit flags + common housekeeping/cell-cycle genes
_KNOWN_GENES = {
    "ACTB",
    "GAPDH",
    "B2M",
    "PPIA",
    "ISG15",
    "IFIT1",
    "MX1",
    "OAS1",
    "TP53",
    "MYC",
    "CDK2",
    "CCND1",
    "RB1",
    "BRCA1",
    "BRCA2",
    "EGFR",
    "KRAS",
    "PTEN",
    "STAT1",
    "STAT3",
    "IRF1",
    "IRF7",
    "IFNB1",
    "IFNG",
    "TNF",
    "IL6",
    "CXCL10",
    "CXCL11",
    "OAS2",
    "OAS3",
    "IFIH1",
    "DDX58",
    "CDKN1A",
    "CDKN1B",
    "MDM2",
    "ATM",
    "CHEK1",
    "CHEK2",
    "ATR",
}

_KNOWN_PATHWAYS = {
    "interferon response",
    "interferon signaling",
    "cell cycle",
    "apoptosis",
    "p53 pathway",
    "pi3k/akt",
    "mapk/erk",
    "nf-kb",
    "nf-kappa b",
    "jAK-STAT",
    "wnt signaling",
    "notch signaling",
    "tgf-beta",
    "dna damage response",
    "unfolded protein response",
    "er stress",
    "autophagy",
    "pyroptosis",
}

_KNOWN_DISEASES = {
    "cancer",
    "leukemia",
    "lymphoma",
    "carcinoma",
    "melanoma",
    "glioblastoma",
    "diabetes",
    "alzheimer",
    "parkinson",
    "inflammation",
    "autoimmune",
    "fibrosis",
    "neurodegeneration",
}

_KNOWN_PERTURBATIONS = {
    "CRISPRi",
    "CRISPR",
    "knockdown",
    "knockout",
    "overexpression",
    "RNAi",
    "siRNA",
    "shRNA",
    "perturbation",
    "gene editing",
}


def extract_entities_fallback(text: str) -> list[dict]:
    """Deterministic regex-based extraction using known gene/pathway/disease sets."""
    entities: list[dict] = []
    text_lower = text.lower()

    # Genes (case-sensitive match against known symbols as word boundaries)
    for gene in _KNOWN_GENES:
        pattern = r"\b" + re.escape(gene) + r"\b"
        for m in re.finditer(pattern, text):
            entities.append({"text": m.group(), "label": "gene", "score": 1.0})

    # Pathways (case-insensitive)
    for pathway in _KNOWN_PATHWAYS:
        if pathway in text_lower:
            idx = text_lower.index(pathway)
            entities.append(
                {
                    "text": text[idx : idx + len(pathway)],
                    "label": "pathway",
                    "score": 0.9,
                }
            )

    # Diseases (case-insensitive)
    for disease in _KNOWN_DISEASES:
        pattern = r"\b" + re.escape(disease) + r"\b"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append({"text": m.group(), "label": "disease", "score": 0.85})

    # Perturbation types
    for ptype in _KNOWN_PERTURBATIONS:
        pattern = r"\b" + re.escape(ptype) + r"\b"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append({"text": m.group(), "label": "perturbation_type", "score": 0.95})

    # Deduplicate by (text, label)
    seen = set()
    unique = []
    for e in entities:
        key = (e["text"].lower(), e["label"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def extract_entities(text: str, model_id: str | None) -> tuple[list[dict], str]:
    """Extract entities using Pioneer if available, else fallback. Returns (entities, method)."""
    if model_id and env_key("PIONEER_API_KEY") and _check_billing():
        entities = extract_entities_pioneer(text, model_id)
        if entities:
            return entities, "pioneer"
    return extract_entities_fallback(text), "fallback"


# --------------------------------------------------------------------------- #
# Enrichment: process literature/*.json files
# --------------------------------------------------------------------------- #


def enrich_literature_entities(run_dir: Path, model_id: str | None) -> int:
    """Extract entities from each literature/*.json file; write .entities.json alongside."""
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        notice("pioneer_ner: no literature/ directory; nothing to enrich")
        return 0

    count = 0
    for lit_path in sorted(lit_dir.glob("*.json")):
        if lit_path.name.endswith(".entities.json"):
            continue
        try:
            payload = json.loads(lit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        # Combine all result snippets into one text for entity extraction
        results = payload.get("results") or []
        combined_text = " ".join(
            (r.get("content") or "") + " " + (r.get("title") or "") for r in results
        )
        if not combined_text.strip():
            continue

        entities, method = extract_entities(combined_text, model_id)

        # Group by label for structured output
        by_label: dict[str, list[str]] = {}
        for e in entities:
            label = e["label"]
            by_label.setdefault(label, [])
            text_val = e["text"]
            if text_val not in by_label[label]:
                by_label[label].append(text_val)

        enriched = {
            "source_file": lit_path.name,
            "method": method,
            "model": model_id or "fallback",
            "entity_count": len(entities),
            "entities": entities,
            "by_label": by_label,
        }

        out_path = lit_path.with_suffix(".entities.json")
        out_path.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
        notice(
            f"pioneer_ner: {lit_path.name} → {len(entities)} entities ({method}) → {out_path.name}"
        )
        count += 1

    return count


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="run folder or experiments/<run-id>")
    parser.add_argument(
        "--train-only", action="store_true", help="generate data + train; skip inference"
    )
    parser.add_argument(
        "--skip-train", action="store_true", help="skip training; inference with base model"
    )
    args = parser.parse_args(argv)

    # Mode 1: train-only (no --run needed)
    if args.train_only:
        model_id = run_training_pipeline()
        if model_id:
            notice(f"pioneer_ner: training complete — model_id={model_id}")
            # Persist model_id for later inference runs
            config_path = Path(__file__).resolve().parent / "pioneer_model.json"
            config_path.write_text(
                json.dumps({"model_id": model_id, "trained": True}, indent=2) + "\n"
            )
            notice(f"pioneer_ner: model_id saved to {config_path.name}")
        else:
            notice("pioneer_ner: training did not complete (check warnings above)")
        return 0

    if not args.run:
        parser.error("--run is required unless --train-only")

    run_dir = resolve_run_dir(args.run)

    # Determine model_id: skip-train uses base, else try training
    model_id = None
    if not args.skip_train:
        # Check if we have a previously trained model
        config_path = Path(__file__).resolve().parent / "pioneer_model.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                model_id = config.get("model_id")
                if model_id:
                    notice(f"pioneer_ner: using previously trained model — {model_id}")
            except json.JSONDecodeError:
                pass

        if not model_id:
            model_id = run_training_pipeline()
            if model_id:
                config_path.write_text(
                    json.dumps({"model_id": model_id, "trained": True}, indent=2) + "\n"
                )

    if not model_id and not args.skip_train:
        notice("pioneer_ner: no trained model; will use fallback extractor")
    elif args.skip_train:
        model_id = BASE_MODEL
        notice(f"pioneer_ner: using base model — {model_id}")

    # Run entity extraction on literature files
    count = enrich_literature_entities(run_dir, model_id)
    if count == 0:
        notice("pioneer_ner: no literature files found; run tools/enrich_literature.py first")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
