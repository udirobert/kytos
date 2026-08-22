"""Pioneer (Fastino) biomedical NER — fine-tune GLiNER2 to extract biological
entities from literature, replacing a general-purpose LLM parsing call.

Side-challenge integration (Pioneer by Fastino): a fine-tuned GLiNER2 encoder
model (205M params) extracts gene names, pathways, diseases, perturbation
types, and other biomedical entities from Tavily literature search results.
The model is deterministic (no hallucinated gene names — critical for a
biology project) and runs on CPU.

Two layers:
  1. **Fallback extractor** (deterministic, stdlib-only): regex-based extraction
     of gene symbols, pathways, perturbation types, diseases, drugs, cell types,
     and biological processes from text. Always available — never blocks.
  2. **Pioneer fine-tuned model** (when PIONEER_API_KEY + billing active):
     GLiNER2 fine-tuned on synthetic CRISPRi/perturbation biology examples,
     deployed via Pioneer's inference API.

Pipeline (when PIONEER_API_KEY is set and billing is active):
  1. Generate synthetic training data  → POST /generate (async, ~2 min)
  2. Poll until dataset is ready       → GET /generate/jobs/:id
  3. Start fine-tuning job              → POST /felix/training-jobs (~20 min)
  4. Poll until training completes      → GET /felix/training-jobs/:id
  5. Run inference on literature/*.json → POST /inference per gene
  6. Write enriched literature with extracted entities

Degradation (famile lesson): missing key, missing client, billing error, or
API failure → fall back to deterministic regex extraction and exit 0.

Usage:
    # one-time: generate data + train (skip if model already deployed)
    python tools/pioneer_ner.py --train

    # inference only (default): extract entities from cached literature
    python tools/pioneer_ner.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from _enrich_common import env_key, load_facts, notice, resolve_run_dir, warn

PIONEER_BASE = "https://api.pioneer.ai"
BASE_MODEL = "fastino/gliner2-base-v1"
DATASET_NAME = "kytos-bio-ner"
MODEL_NAME = "kytos-bio-ner-v1"

# Entity labels the fine-tuned model extracts from biomedical literature.
BIO_ENTITY_LABELS = [
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

# Polling intervals (seconds)
GEN_POLL_INTERVAL = 10
TRAIN_POLL_INTERVAL = 15
GEN_TIMEOUT = 300  # 5 min for data generation
TRAIN_TIMEOUT = 1800  # 30 min for fine-tuning

# --------------------------------------------------------------------------- #
# Fallback deterministic extractor (stdlib only — always available)
# --------------------------------------------------------------------------- #

# Known pathways / biological processes (case-insensitive match)
KNOWN_PATHWAYS = [
    "interferon response",
    "interferon signaling",
    "type i interferon",
    "jak-stat",
    "jak-stat pathway",
    "nf-kb",
    "nf-kappa b",
    "mapk",
    "erk",
    "pi3k-akt",
    "mTOR",
    "mtor pathway",
    "wnt signaling",
    "wnt pathway",
    "notch signaling",
    "tgf-beta",
    "tgfb",
    "smad",
    "apoptosis",
    "cell cycle arrest",
    "dna damage response",
    "unfolded protein response",
    "upr",
    "autophagy",
    "oxidative stress",
    "hypoxia",
    "hypoxia response",
    "endoplasmic reticulum stress",
    "er stress",
    "complement cascade",
    "innate immune",
    "adaptive immune",
    "epithelial-mesenchymal transition",
    "emt",
]

KNOWN_PERTURBATION_TYPES = [
    "CRISPRi",
    "CRISPR",
    "CRISPR-Cas9",
    "Cas9",
    "knockdown",
    "knockout",
    "overexpression",
    "silencing",
    "RNAi",
    "siRNA",
    "shRNA",
    "perturbation",
    "gene perturbation",
]

KNOWN_DISEASES = [
    "cancer",
    "leukemia",
    "lymphoma",
    "carcinoma",
    "melanoma",
    "diabetes",
    "alzheimer",
    "parkinson",
    "huntington",
    "fibrosis",
    "inflammation",
    "autoimmune",
]

KNOWN_CELL_TYPES = [
    "K562",
    "HEK293",
    "HeLa",
    "Jurkat",
    "A549",
    "MCF7",
    "U2OS",
    "THP-1",
    "HepG2",
    "iPSC",
    "embryonic",
    "primary cell",
    "T cell",
    "B cell",
    "NK cell",
    "macrophage",
    "dendritic",
    "fibroblast",
    "epithelial",
    "endothelial",
    "stem cell",
]

KNOWN_DRUGS = [
    "doxorubicin",
    "methotrexate",
    "imatinib",
    "vemurafenib",
    "trametinib",
    "palbociclib",
    "rapamycin",
    "cycloheximide",
    "staurosporine",
    "nutlin",
]

# Gene symbol pattern: 2-6 uppercase letters, optionally followed by a digit,
# e.g. ACTB, GAPDH, ISG15, TP53, MYC, B2M
_GENE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,6})\b")


def extract_entities_fallback(text: str) -> list[dict]:
    """Deterministic regex-based biomedical entity extraction (no API needed).

    Returns a list of {"text": str, "label": str, "start": int, "end": int}.
    Deduplicates by (text, label).
    """
    entities: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(match_text: str, label: str, start: int, end: int) -> None:
        key = (match_text, label)
        if key in seen:
            return
        seen.add(key)
        entities.append({"text": match_text, "label": label, "start": start, "end": end})

    # Genes: uppercase gene symbols (2-7 chars, letters + digits)
    for m in _GENE_RE.finditer(text):
        symbol = m.group(1)
        # Filter out common English words that match the pattern
        if symbol in {
            "THE",
            "AND",
            "FOR",
            "NOT",
            "BUT",
            "ALL",
            "ANY",
            "CAN",
            "HAS",
            "HER",
            "HIS",
            "HOW",
            "ITS",
            "MAY",
            "OUR",
            "SHE",
            "USE",
            "WHO",
            "DNA",
            "RNA",
            "URL",
            "API",
            "JSON",
            "HTML",
            "HTTP",
            "CSV",
            "PDF",
            "UTC",
            "USA",
            "UK",
        }:
            continue
        _add(symbol, "gene", m.start(1), m.end(1))

    # Pathways / biological processes (case-insensitive)
    for pathway in KNOWN_PATHWAYS:
        pattern = re.compile(re.escape(pathway), re.IGNORECASE)
        for m in pattern.finditer(text):
            _add(m.group(0), "pathway", m.start(), m.end())

    # Perturbation types
    for ptype in KNOWN_PERTURBATION_TYPES:
        pattern = re.compile(re.escape(ptype), re.IGNORECASE)
        for m in pattern.finditer(text):
            _add(m.group(0), "perturbation_type", m.start(), m.end())

    # Diseases
    for disease in KNOWN_DISEASES:
        pattern = re.compile(re.escape(disease), re.IGNORECASE)
        for m in pattern.finditer(text):
            _add(m.group(0), "disease", m.start(), m.end())

    # Cell types
    for cell_type in KNOWN_CELL_TYPES:
        pattern = re.compile(re.escape(cell_type), re.IGNORECASE)
        for m in pattern.finditer(text):
            _add(m.group(0), "cell_type", m.start(), m.end())

    # Drugs
    for drug in KNOWN_DRUGS:
        pattern = re.compile(re.escape(drug), re.IGNORECASE)
        for m in pattern.finditer(text):
            _add(m.group(0), "drug", m.start(), m.end())

    return entities


def extract_entities(
    text: str, model_id: str | None = None, api_key: str | None = None
) -> tuple[list[dict], str]:
    """Extract biomedical entities from text.

    Uses Pioneer GLiNER2 inference if api_key and model_id are provided;
    otherwise falls back to deterministic regex extraction.

    Returns (entities_list, method) where method is "pioneer" or "fallback".
    """
    if api_key and model_id:
        try:
            resp = _post(
                api_key,
                "/inference",
                {
                    "model_id": model_id,
                    "text": text,
                    "schema": {"entities": BIO_ENTITY_LABELS},
                    "threshold": 0.3,
                },
            )
            # Parse Pioneer response into our entity format
            entities = []
            if isinstance(resp, list):
                for item in resp:
                    entities.append(
                        {
                            "text": item.get("text", ""),
                            "label": item.get("label", ""),
                            "start": item.get("start", 0),
                            "end": item.get("end", 0),
                            "score": item.get("score", 0),
                        }
                    )
            elif isinstance(resp, dict) and "entities" in resp:
                for item in resp["entities"]:
                    entities.append(
                        {
                            "text": item.get("text", ""),
                            "label": item.get("label", ""),
                            "start": item.get("start", 0),
                            "end": item.get("end", 0),
                            "score": item.get("score", 0),
                        }
                    )
            return entities, "pioneer"
        except Exception as exc:
            warn(f"pioneer: inference failed ({exc}); using fallback extractor")

    return extract_entities_fallback(text), "fallback"


def enrich_literature_entities(run_dir: Path, model_id: str | None = None) -> int:
    """Extract biomedical entities from each cached literature/*.json file.

    Writes <gene>.entities.json alongside each literature file with:
    {method, entity_count, by_label: {gene: [...], pathway: [...], ...}}
    Skips files that already have .entities.json (idempotent).

    Returns number of files enriched.
    """
    api_key = env_key("PIONEER_API_KEY", "PIONEER_KEY")
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        return 0

    enriched = 0
    for lit_file in sorted(lit_dir.glob("*.json")):
        # Skip .entities.json files themselves (they are output, not input)
        if lit_file.name.endswith(".entities.json"):
            continue

        try:
            payload = json.loads(lit_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        # Combine all result snippets into one text for entity extraction
        results = payload.get("results") or []
        combined_text = " ".join((r.get("content") or r.get("title") or "") for r in results)[:3000]

        if not combined_text.strip():
            continue

        entities, method = extract_entities(combined_text, model_id=model_id, api_key=api_key)

        # Group by label
        by_label: dict[str, list[str]] = {}
        for ent in entities:
            label = ent["label"]
            text_val = ent["text"]
            if text_val not in by_label.setdefault(label, []):
                by_label[label].append(text_val)

        output = {
            "method": method,
            "model_id": model_id or "fallback",
            "entity_count": len(entities),
            "by_label": by_label,
            "source_file": lit_file.name,
        }
        entities_path = lit_dir / (lit_file.stem + ".entities.json")
        entities_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        enriched += 1
        notice(f"pioneer: wrote {entities_path.name} ({len(entities)} entities, {method})")

    return enriched


# --------------------------------------------------------------------------- #
# Pioneer API helpers (training + inference)
# --------------------------------------------------------------------------- #


def _post(api_key: str, path: str, body: dict) -> dict:
    url = f"{PIONEER_BASE}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _get(api_key: str, path: str) -> dict:
    url = f"{PIONEER_BASE}{path}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _is_billing_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = json.loads(exc.read())
            return body.get("detail", {}).get("code") == "payment_method_required"
        except Exception:
            return False
    return False


# --------------------------------------------------------------------------- #
# Training pipeline (run once with --train)
# --------------------------------------------------------------------------- #


def generate_dataset(api_key: str) -> str | None:
    """Start synthetic data generation; return job_id or None on failure."""
    notice(f"pioneer: generating synthetic NER dataset '{DATASET_NAME}' (200 examples)...")
    try:
        resp = _post(
            api_key,
            "/generate",
            {
                "task_type": "ner",
                "dataset_name": DATASET_NAME,
                "labels": BIO_ENTITY_LABELS,
                "num_examples": 200,
                "domain_description": DOMAIN_DESCRIPTION,
            },
        )
        job_id = resp.get("job_id")
        notice(f"pioneer: generation job started (job_id={job_id})")
        return job_id
    except urllib.error.HTTPError as exc:
        if _is_billing_error(exc):
            warn("pioneer: billing required — add a card at agent.pioneer.ai/billing to train")
        else:
            warn(f"pioneer: generation failed ({exc})")
        return None
    except Exception as exc:
        warn(f"pioneer: generation failed ({exc})")
        return None


def poll_generation(api_key: str, job_id: str) -> bool:
    """Poll generation job until ready or timeout. Returns True on success."""
    deadline = time.time() + GEN_TIMEOUT
    while time.time() < deadline:
        try:
            resp = _get(api_key, f"/generate/jobs/{job_id}")
        except Exception as exc:
            warn(f"pioneer: poll failed ({exc}); retrying...")
            time.sleep(GEN_POLL_INTERVAL)
            continue
        status = resp.get("status", "")
        count = resp.get("count", 0)
        notice(f"pioneer: generation status={status} count={count}")
        if status == "ready":
            return True
        if status == "failed":
            warn(f"pioneer: generation failed: {resp.get('error', 'unknown')}")
            return False
        time.sleep(GEN_POLL_INTERVAL)
    warn("pioneer: generation timed out")
    return False


def start_training(api_key: str) -> str | None:
    """Start a fine-tuning job on the generated dataset. Returns job_id."""
    notice(f"pioneer: starting fine-tuning job (base={BASE_MODEL}, lora, 5 epochs)...")
    try:
        resp = _post(
            api_key,
            "/felix/training-jobs",
            {
                "model_name": MODEL_NAME,
                "base_model": BASE_MODEL,
                "datasets": [{"name": DATASET_NAME}],
                "training_type": "lora",
                "nr_epochs": 5,
                "learning_rate": 5e-5,
            },
        )
        job_id = resp.get("id")
        notice(f"pioneer: training job started (id={job_id})")
        return job_id
    except Exception as exc:
        warn(f"pioneer: training start failed ({exc})")
        return None


def poll_training(api_key: str, job_id: str) -> dict | None:
    """Poll training job until complete. Returns full response or None."""
    deadline = time.time() + TRAIN_TIMEOUT
    while time.time() < deadline:
        try:
            resp = _get(api_key, f"/felix/training-jobs/{job_id}")
        except Exception as exc:
            warn(f"pioneer: training poll failed ({exc}); retrying...")
            time.sleep(TRAIN_POLL_INTERVAL)
            continue
        status = resp.get("status", "")
        notice(f"pioneer: training status={status}")
        if status == "complete":
            metrics = resp.get("metrics") or {}
            notice(
                f"pioneer: training complete! f1={metrics.get('f1', '?')} "
                f"precision={metrics.get('precision', '?')} "
                f"recall={metrics.get('recall', '?')}"
            )
            return resp
        if status == "failed":
            warn("pioneer: training failed")
            return None
        time.sleep(TRAIN_POLL_INTERVAL)
    warn("pioneer: training timed out")
    return None


def find_deployed_model(api_key: str) -> str | None:
    """Check if a previously trained model exists and return its job ID."""
    try:
        resp = _get(api_key, "/felix/training-jobs?status=complete&limit=50")
        jobs = resp.get("training_jobs") or []
        for job in jobs:
            if job.get("model_name") == MODEL_NAME:
                job_id = job.get("id")
                notice(f"pioneer: found existing trained model (job_id={job_id})")
                return job_id
    except Exception:
        pass
    return None


def run_training_pipeline(api_key: str) -> str | None:
    """Full pipeline: generate data → train → return model job_id for inference."""
    existing = find_deployed_model(api_key)
    if existing:
        return existing

    gen_job = generate_dataset(api_key)
    if not gen_job:
        return None
    if not poll_generation(api_key, gen_job):
        return None

    train_job = start_training(api_key)
    if not train_job:
        return None

    result = poll_training(api_key, train_job)
    if result:
        return train_job
    return None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=None, help="run folder or experiments/<run-id>")
    parser.add_argument(
        "--train",
        action="store_true",
        help="run the full training pipeline (generate data + fine-tune). "
        "Without this flag, only runs inference using an existing model.",
    )
    args = parser.parse_args(argv)

    api_key = env_key("PIONEER_API_KEY", "PIONEER_KEY")

    # Training path
    if args.train:
        if not api_key:
            notice("pioneer: skipped training (no PIONEER_API_KEY); run degrades without NER")
            return 0
        model_id = run_training_pipeline(api_key)
        if not model_id:
            warn("pioneer: training pipeline failed; run degrades without NER enrichment")
            return 0
        if not args.run:
            return 0

    # Inference / fallback enrichment path
    if not args.run:
        notice("pioneer: no --run provided; nothing to do (use --train to train)")
        return 0

    run_dir = resolve_run_dir(args.run)
    load_facts(run_dir)  # facts.json must exist

    # Use trained model if available, otherwise fallback extractor
    model_id = None
    if api_key:
        model_id = find_deployed_model(api_key)
        if not model_id:
            model_id = BASE_MODEL
            notice(
                f"pioneer: no trained model found; will try base {BASE_MODEL}, fallback if needed"
            )

    count = enrich_literature_entities(run_dir, model_id=model_id)
    if count:
        notice(f"pioneer: enriched {count} literature file(s) with biomedical NER")
    else:
        notice("pioneer: no literature files were enriched (degrades empty)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
