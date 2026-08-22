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
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from _enrich_common import (  # noqa: E402
    REPO_ROOT,
    env_key,
    load_facts,
    notice,
    record_pipeline_status,
    resolve_run_dir,
    warn,
)

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


def _entity_schema() -> dict:
    """Unified GLiNER2 schema (Pioneer API v2026)."""
    return {"entities": [{"name": label} for label in BIO_ENTITY_LABELS]}


def parse_pioneer_inference_response(resp: dict | list) -> list[dict]:
    """Normalize Pioneer /inference payloads into [{text, label, start, end, score?}]."""
    entities: list[dict] = []

    def _append_span(item: dict) -> None:
        text_val = item.get("text") or item.get("span") or ""
        label = item.get("label") or item.get("type") or ""
        if text_val and label:
            entities.append(
                {
                    "text": text_val,
                    "label": label,
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                    **({"score": item["score"]} if "score" in item else {}),
                }
            )

    def _append_label_map(label_map: dict) -> None:
        for label, items in label_map.items():
            if isinstance(items, str):
                items = [items]
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    text_val = item.get("text") or item.get("span") or ""
                    if not text_val:
                        continue
                    ent: dict = {
                        "text": text_val,
                        "label": label,
                        "start": item.get("start", 0),
                        "end": item.get("end", 0),
                    }
                    if "confidence" in item:
                        ent["score"] = item["confidence"]
                    elif "score" in item:
                        ent["score"] = item["score"]
                    entities.append(ent)
                elif item:
                    entities.append({"text": str(item), "label": label, "start": 0, "end": 0})

    if isinstance(resp, list):
        for item in resp:
            if isinstance(item, dict):
                _append_span(item)
        return entities

    if not isinstance(resp, dict):
        return entities

    result = resp.get("result")
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and isinstance(data.get("entities"), dict):
            _append_label_map(data["entities"])
            if entities:
                return entities
        if isinstance(result.get("entities"), dict):
            _append_label_map(result["entities"])
            if entities:
                return entities

    top_entities = resp.get("entities")
    if isinstance(top_entities, dict):
        sample = next(iter(top_entities.values()), None)
        if isinstance(sample, list) or isinstance(sample, str):
            _append_label_map(top_entities)
            return entities

    if isinstance(top_entities, list):
        for item in top_entities:
            if isinstance(item, dict):
                _append_span(item)

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
                    "schema": _entity_schema(),
                    "threshold": 0.3,
                },
            )
            entities = parse_pioneer_inference_response(resp)
            if entities:
                return entities, "pioneer"
            warn("pioneer: inference returned no entities; using fallback extractor")
        except urllib.error.HTTPError as exc:
            if _is_billing_error(exc):
                warn(
                    "pioneer: billing required — add a card at "
                    "https://agent.pioneer.ai/billing to run inference"
                )
            else:
                warn(f"pioneer: inference failed (HTTP {exc.code}); using fallback extractor")
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


def _ssl_context() -> ssl.SSLContext:
    """CA bundle for macOS/Python builds with incomplete cert stores."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _post(api_key: str, path: str, body: dict) -> dict:
    url = f"{PIONEER_BASE}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
        return json.loads(resp.read())


def _get(api_key: str, path: str) -> dict:
    url = f"{PIONEER_BASE}{path}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
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


def label_existing_texts(api_key: str, texts: list[str]) -> list[dict]:
    """Auto-label real text via POST /generate/ner/label-existing (synchronous).

    This is the recommended path when synthetic /generate produces empty entities.
    Takes 1-1000 raw text strings, returns NER-labeled examples synchronously.

    Returns a list of {"text": ..., "entities": [[text, label], ...]} dicts
    ready for JSONL upload.
    """
    if not texts:
        return []
    notice(f"pioneer: auto-labeling {len(texts)} text(s) via /generate/ner/label-existing...")
    try:
        resp = _post(
            api_key,
            "/generate/ner/label-existing",
            {
                "labels": BIO_ENTITY_LABELS,
                "inputs": texts,
            },
        )
    except Exception as exc:
        warn(f"pioneer: label-existing failed ({exc})")
        return []

    # Response format: {"result": {"data": {"entities": {label: [span, ...]}}}}
    # or a list of per-input annotation dicts. Normalize to NER training rows.
    labeled: list[dict] = []
    if isinstance(resp, list):
        for i, item in enumerate(resp):
            if isinstance(item, dict):
                ents = _parse_label_existing_item(item, texts[i] if i < len(texts) else "")
                if ents:
                    labeled.append({"text": texts[i] if i < len(texts) else "", "entities": ents})
    elif isinstance(resp, dict):
        result = resp.get("result") or resp
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list) and isinstance(resp.get("data"), list):
            data = resp["data"]
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    text_val = item.get("text") or (texts[i] if i < len(texts) else "")
                    ents = _parse_label_existing_item(item, text_val)
                    if ents:
                        labeled.append({"text": text_val, "entities": ents})

    notice(f"pioneer: label-existing produced {len(labeled)} labeled examples")
    return labeled


def _parse_label_existing_item(item: dict, original_text: str) -> list[list[str]]:
    """Extract [[text, label], ...] from a label-existing annotation item."""
    entities: list[list[str]] = []
    ent_data = item.get("entities")
    if isinstance(ent_data, dict):
        for label, spans in ent_data.items():
            if isinstance(spans, str):
                spans = [spans]
            if isinstance(spans, list):
                for span in spans:
                    if isinstance(span, dict):
                        text_val = span.get("text") or span.get("span") or ""
                        if text_val:
                            entities.append([text_val, label])
                    elif isinstance(span, str) and span:
                        entities.append([span, label])
    elif isinstance(ent_data, list):
        for span in ent_data:
            if isinstance(span, dict):
                text_val = span.get("text") or span.get("span") or ""
                label = span.get("label") or span.get("type") or ""
                if text_val and label:
                    entities.append([text_val, label])
    return entities


def _collect_literature_texts(run_dir: Path | None = None, max_texts: int = 50) -> list[str]:
    """Gather text snippets from k001 literature/*.json for labeling.

    Uses the 'content' field from Tavily search results — real biomedical text
    that the Pioneer generator should be able to annotate with entity spans.
    """
    if run_dir is None:
        run_dir = REPO_ROOT / "experiments" / "k001-mean-shift-baseline"
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        return []

    texts: list[str] = []
    for lit_file in sorted(lit_dir.glob("*.json")):
        if lit_file.name.endswith(".entities.json"):
            continue
        try:
            data = json.loads(lit_file.read_text())
        except Exception:
            continue
        for result in data.get("results") or []:
            content = result.get("content") or ""
            if content and len(content) > 50:
                texts.append(content[:500])  # cap length for the API
                if len(texts) >= max_texts:
                    return texts
    return texts


def upload_dataset(
    api_key: str, dataset_name: str, rows: list[dict], dataset_type: str = "ner"
) -> str | None:
    """Upload labeled examples as a JSONL dataset via the 3-step upload pipeline.

    Steps: POST /felix/datasets/upload/url → PUT to S3 → POST .../upload/process
    Returns the dataset_id, or None on failure.
    """
    if not rows:
        warn("pioneer: no rows to upload")
        return None

    import tempfile

    # Write JSONL to temp file
    jsonl_path = Path(tempfile.mktemp(suffix=".jsonl"))
    with jsonl_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    try:
        # Step 1: get presigned URL
        notice(f"pioneer: requesting upload URL for '{dataset_name}' ({len(rows)} rows)...")
        resp = _post(
            api_key,
            "/felix/datasets/upload/url",
            {
                "dataset_name": dataset_name,
                "dataset_type": dataset_type,
                "type": "training",
                "filename": "data.jsonl",
            },
        )
        presigned_url = resp.get("presigned_url")
        dataset_id = resp.get("dataset_id")
        if not presigned_url or not dataset_id:
            warn(f"pioneer: upload URL response missing fields: {list(resp.keys())}")
            return None

        # Step 2: PUT file to S3
        notice("pioneer: uploading JSONL to S3...")
        data = jsonl_path.read_bytes()
        req = urllib.request.Request(
            presigned_url,
            data=data,
            method="PUT",
            headers={"Content-Type": "application/octet-stream"},
        )
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as r:
            if r.status not in (200, 204):
                warn(f"pioneer: S3 upload returned status {r.status}")
                return None

        # Step 3: trigger processing
        notice("pioneer: triggering dataset processing...")
        _post(api_key, "/felix/datasets/upload/process", {"dataset_id": dataset_id})
        notice(f"pioneer: dataset '{dataset_name}' uploaded (dataset_id={dataset_id})")
        return dataset_id
    except Exception as exc:
        warn(f"pioneer: dataset upload failed ({exc})")
        return None
    finally:
        jsonl_path.unlink(missing_ok=True)


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
            err = resp.get("error") or resp.get("message") or "unknown"
            warn(f"pioneer: generation failed: {err}")
            return False
        time.sleep(GEN_POLL_INTERVAL)
    warn("pioneer: generation timed out")
    return False


def _dataset_ready(api_key: str, dataset_name: str) -> dict | None:
    """Return the latest ready dataset version dict, or None."""
    try:
        resp = _get(api_key, f"/felix/datasets/{dataset_name}")
    except Exception as exc:
        warn(f"pioneer: dataset lookup failed ({exc})")
        return None
    for version in resp.get("versions") or []:
        if version.get("status") == "ready" and (version.get("sample_size") or 0) > 0:
            return version
    return None


DATASET_READY_TIMEOUT = 300
DATASET_READY_POLL = 5


def poll_dataset_ready(api_key: str, dataset_name: str) -> dict | None:
    """Poll until an uploaded dataset version is ready, or timeout."""
    deadline = time.time() + DATASET_READY_TIMEOUT
    while time.time() < deadline:
        version = _dataset_ready(api_key, dataset_name)
        if version:
            notice(
                f"pioneer: dataset '{dataset_name}' ready "
                f"(v{version.get('version_number')}, n={version.get('sample_size')})"
            )
            return version
        time.sleep(DATASET_READY_POLL)
    warn(f"pioneer: dataset '{dataset_name}' not ready after {DATASET_READY_TIMEOUT}s")
    return None


def _entities_to_training_pairs(entities: list[dict]) -> list[list[str]]:
    """Convert inference spans to NER JSONL entity pairs [[text, label], ...]."""
    pairs: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for ent in entities:
        text_val = ent.get("text") or ""
        label = ent.get("label") or ""
        if not text_val or not label:
            continue
        key = (text_val, label)
        if key in seen:
            continue
        seen.add(key)
        pairs.append([text_val, label])
    return pairs


def build_training_rows_from_inference(
    api_key: str, texts: list[str], model_id: str = BASE_MODEL
) -> list[dict]:
    """Silver-label texts with base GLiNER2 when /generate/label-existing is empty."""
    rows: list[dict] = []
    for text in texts:
        if not text.strip():
            continue
        try:
            resp = _post(
                api_key,
                "/inference",
                {
                    "model_id": model_id,
                    "text": text,
                    "schema": _entity_schema(),
                    "threshold": 0.3,
                },
            )
            entities = parse_pioneer_inference_response(resp)
        except Exception as exc:
            warn(f"pioneer: inference labeling failed ({exc})")
            entities = []
        if not entities:
            entities = extract_entities_fallback(text)
        pairs = _entities_to_training_pairs(entities)
        if pairs:
            rows.append({"text": text, "entities": pairs})
    notice(f"pioneer: built {len(rows)} training row(s) from inference/fallback labels")
    return rows


def _upload_train_validate(api_key: str, dataset_name: str, rows: list[dict]) -> str | None:
    """Upload JSONL rows, wait for ready, validate entities, start training."""
    if not upload_dataset(api_key, dataset_name, rows):
        return None
    version = poll_dataset_ready(api_key, dataset_name)
    if not version:
        return None
    version_no = str(version.get("version_number") or "1")
    if not _validate_ner_dataset(api_key, dataset_name, version_no):
        return None
    train_job = start_training(api_key, dataset_name)
    if not train_job:
        return None
    result = poll_training(api_key, train_job)
    return train_job if result else None


def _dataset_preview(api_key: str, dataset_name: str, version: str, limit: int = 10) -> dict | None:
    """Fetch a sample of stored rows via GET /felix/datasets/{name}/{version}/preview."""
    try:
        return _get(api_key, f"/felix/datasets/{dataset_name}/{version}/preview?limit={limit}")
    except Exception as exc:
        warn(f"pioneer: dataset preview failed ({exc})")
        return None


def dataset_has_entity_labels(preview: dict) -> bool:
    """True if at least one preview row carries NER entity annotations."""
    for row in preview.get("rows") or []:
        entities = row.get("entities")
        if isinstance(entities, list) and entities:
            return True
        if isinstance(entities, dict) and entities:
            return True
    return False


def _validate_ner_dataset(api_key: str, dataset_name: str, version_no: str) -> bool:
    """Preflight: status=ready is not enough — rows must contain entity labels."""
    preview = _dataset_preview(api_key, dataset_name, version_no)
    if not preview:
        return False
    total = preview.get("total_rows") or 0
    if total <= 0:
        warn(f"pioneer: dataset '{dataset_name}' v{version_no} has zero rows")
        return False
    if dataset_has_entity_labels(preview):
        return True
    warn(
        f"pioneer: dataset '{dataset_name}' v{version_no} has {total} rows but preview "
        f"shows empty entity labels — training would fail with 'No valid datasets found'. "
        "Regenerate with simpler labels, use POST /generate/ner/label-existing on real "
        "text, or upload JSONL via /felix/datasets/upload/* "
        "(see docs.pioneer.ai/concepts/datasets)."
    )
    return False


def start_training(api_key: str, dataset_name: str = DATASET_NAME) -> str | None:
    """Start a fine-tuning job on the generated dataset. Returns job_id."""
    version = _dataset_ready(api_key, dataset_name)
    if not version:
        warn(f"pioneer: dataset '{dataset_name}' not ready — cannot train")
        return None
    version_no = str(version.get("version_number") or "1")
    if not _validate_ner_dataset(api_key, dataset_name, version_no):
        return None
    sample_size = version.get("sample_size")
    notice(
        f"pioneer: starting fine-tuning (base={BASE_MODEL}, lora, 5 epochs, "
        f"samples={sample_size})..."
    )
    body: dict = {
        "model_name": MODEL_NAME,
        "base_model": BASE_MODEL,
        "datasets": [{"name": dataset_name, "version": version_no}],
        "training_type": "lora",
        "nr_epochs": 5,
        "learning_rate": 5e-5,
    }
    project_id = version.get("project_id")
    if project_id:
        body["project_id"] = project_id
    try:
        resp = _post(api_key, "/felix/training-jobs", body)
        job_id = resp.get("id")
        notice(f"pioneer: training job started (id={job_id})")
        return job_id
    except urllib.error.HTTPError as exc:
        if _is_billing_error(exc):
            warn("pioneer: billing required — add a card at agent.pioneer.ai/billing to train")
        else:
            warn(f"pioneer: training start failed (HTTP {exc.code})")
        return None
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
        if status in ("failed", "errored", "error", "cancelled"):
            err = resp.get("error") or resp.get("message") or resp.get("detail") or status
            warn(f"pioneer: training failed ({err})")
            return None
        time.sleep(TRAIN_POLL_INTERVAL)
    warn("pioneer: training timed out")
    return None


def find_deployed_model(api_key: str) -> str | None:
    """Check if a previously trained model exists and return its job ID for inference."""
    try:
        resp = _get(api_key, "/felix/training-jobs?status=complete&limit=50")
        jobs = resp.get("training_jobs") or []
        prefix = MODEL_NAME
        candidates = [
            j
            for j in jobs
            if (j.get("model_name") or "").startswith(prefix)
            and j.get("status") in ("complete", "deployed")
            and j.get("is_deployable", True)
        ]
        if not candidates:
            return None
        # Prefer latest suffix (e.g. kytos-bio-ner-v1_2 over v1)
        candidates.sort(key=lambda j: j.get("model_name") or "", reverse=True)
        job = candidates[0]
        job_id = job.get("id")
        notice(f"pioneer: found existing trained model ({job.get('model_name')}, job_id={job_id})")
        return job_id
    except Exception:
        pass
    return None


def run_training_pipeline(api_key: str) -> str | None:
    """Full pipeline: label data → upload → train → return model job_id.

    Strategy (tried in order):
    1. Reuse an existing trained model if present.
    2. label-existing on Tavily literature → upload JSONL → train.
    3. Base GLiNER2 inference (silver labels) → upload → train.
    4. Synthetic /generate (last resort; often empty entities for niche domains).
    """
    existing = find_deployed_model(api_key)
    if existing:
        return existing

    texts = _collect_literature_texts()
    if not texts:
        warn("pioneer: no literature text found for training")
        return None

    # Path B: label-existing (Fastino recommended when synthetic fails)
    notice("pioneer: trying label-existing on real Tavily literature text...")
    labeled = label_existing_texts(api_key, texts[:50])
    if labeled:
        job_id = _upload_train_validate(api_key, f"{DATASET_NAME}-labeled", labeled)
        if job_id:
            return job_id
    else:
        warn("pioneer: label-existing returned empty — trying inference silver labels")

    # Path C: silver labels from base GLiNER2 + regex fallback
    silver = build_training_rows_from_inference(api_key, texts)
    if silver:
        job_id = _upload_train_validate(api_key, f"{DATASET_NAME}-silver", silver)
        if job_id:
            return job_id

    # Path A: synthetic generation (slow; often empty entities)
    notice("pioneer: falling back to synthetic /generate...")
    gen_job = generate_dataset(api_key)
    if gen_job and poll_generation(api_key, gen_job):
        version = poll_dataset_ready(api_key, DATASET_NAME) or _dataset_ready(api_key, DATASET_NAME)
        if version:
            version_no = str(version.get("version_number") or "1")
            if _validate_ner_dataset(api_key, DATASET_NAME, version_no):
                train_job = start_training(api_key, DATASET_NAME)
                if train_job:
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
        if model_id and model_id != "fallback" and model_id != BASE_MODEL:
            record_pipeline_status(
                run_dir,
                "ner",
                "done",
                f"Fine-tuned LoRA ({model_id}) — {count} literature files enriched.",
            )
        elif model_id == BASE_MODEL:
            record_pipeline_status(
                run_dir,
                "ner",
                "fallback",
                f"Base GLiNER2 ({model_id}) — trained model unavailable, "
                f"{count} files enriched with base model.",
            )
        else:
            record_pipeline_status(
                run_dir,
                "ner",
                "fallback",
                f"Regex fallback extractor — {count} files enriched "
                "(no API key or all model calls failed).",
            )
    else:
        notice("pioneer: no literature files were enriched (degrades empty)")
        record_pipeline_status(
            run_dir,
            "ner",
            "failed",
            "No literature files to enrich — run enrich_literature.py first.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
