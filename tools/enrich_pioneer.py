"""Pioneer (Fastino) biomedical NER — fine-tuned GLiNER2 for perturbation biology.

Replaces a general-purpose LLM call (GPT-4o) with a 205M-param fine-tuned
encoder model for deterministic biomedical entity extraction from literature.

**Side challenge (Best Use of Pioneer, 500€):**
- Fine-tuned GLiNER2 replaces an LLM API call for biomedical NER
- Uses Pioneer's synthetic data generation to create training examples
- GLiNER2 is deterministic — no hallucinated gene names (critical for biology audit)
- 205M params, runs on CPU, ~$0 cost per inference vs ~$0.01 for GPT-4o

Two modes:
  --train:  generate synthetic data → fine-tune GLiNER2 → cache model ID
  --run:    extract entities from literature/*.json using the fine-tuned model

Model resolution order (for --run):
  1. PIONEER_MODEL_ID env var (explicit override)
  2. tools/.pioneer_model_id file (cached after --train)
  3. fastino/gliner2-base-v1 (zero-shot fallback — still works, less accurate)

Degradation: missing key, billing issue, or API failure → exit 0. The site
builds without the entity enrichment (famile lesson — auxiliary never blocks).

Usage:
    # Train (one-time, ~20 min):
    python tools/enrich_pioneer.py --train

    # Extract entities from a run's literature:
    python tools/enrich_pioneer.py --run experiments/k001-mean-shift-baseline
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from _enrich_common import env_key, load_facts, notice, resolve_run_dir, utcnow, warn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PIONEER_BASE = "https://api.pioneer.ai"
BASE_MODEL = "fastino/gliner2-base-v1"
DATASET_NAME = "kytos-bio-ner"
MODEL_CACHE = Path(__file__).resolve().parent / ".pioneer_model_id"

ENTITY_LABELS = [
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
    "Texts describe gene knockdown experiments, perturbation responses, pathway "
    "analysis, gene expression changes in cell lines, and biological audit of "
    "computational predictions. Examples include descriptions of housekeeping "
    "gene shifts, interferon pathway coherence, CRISPRi knockdown effects, and "
    "differential expression analysis."
)

NUM_EXAMPLES = 200
TRAINING_EPOCHS = 5
TRAINING_LR = 5e-5

POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC = 1200  # 20 min max for generation + training

# ---------------------------------------------------------------------------
# Pioneer API client (stdlib urllib — no third-party deps)
# ---------------------------------------------------------------------------


class PioneerClient:
    """Minimal Pioneer API client using stdlib urllib."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _request(
        self, method: str, path: str, body: dict | None = None, timeout: int = 120
    ) -> dict:
        url = f"{PIONEER_BASE}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            try:
                err = json.loads(body_text)
            except json.JSONDecodeError:
                err = {"error": body_text}
            raise PioneerAPIError(exc.code, err) from exc

    # -- Data generation --

    def generate_data(
        self,
        dataset_name: str,
        labels: list[str],
        domain_description: str,
        num_examples: int,
    ) -> str:
        """Start synthetic data generation; return job_id."""
        resp = self._request(
            "POST",
            "/generate",
            {
                "task_type": "ner",
                "dataset_name": dataset_name,
                "labels": labels,
                "domain_description": domain_description,
                "num_examples": num_examples,
            },
        )
        job_id = resp.get("job_id")
        if not job_id:
            raise RuntimeError(f"no job_id in generate response: {resp}")
        return job_id

    def poll_generation(self, job_id: str) -> dict:
        return self._request("GET", f"/generate/jobs/{job_id}")

    # -- Training --

    def start_training(
        self,
        model_name: str,
        base_model: str,
        dataset_name: str,
        training_type: str = "lora",
        nr_epochs: int = TRAINING_EPOCHS,
        learning_rate: float = TRAINING_LR,
    ) -> str:
        """Start a fine-tuning job; return training job id."""
        resp = self._request(
            "POST",
            "/felix/training-jobs",
            {
                "model_name": model_name,
                "base_model": base_model,
                "datasets": [{"name": dataset_name}],
                "training_type": training_type,
                "nr_epochs": nr_epochs,
                "learning_rate": learning_rate,
            },
        )
        job_id = resp.get("id")
        if not job_id:
            raise RuntimeError(f"no id in training response: {resp}")
        return job_id

    def poll_training(self, job_id: str) -> dict:
        return self._request("GET", f"/felix/training-jobs/{job_id}")

    # -- Inference --

    def infer(self, model_id: str, text: str, labels: list[str], threshold: float = 0.3) -> dict:
        """Run NER inference; return extracted entities."""
        return self._request(
            "POST",
            "/inference",
            {
                "model_id": model_id,
                "text": text,
                "schema": {"entities": labels},
                "threshold": threshold,
            },
        )


class PioneerAPIError(Exception):
    """Wraps a Pioneer API HTTP error."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Pioneer API {status_code}: {body}")


# ---------------------------------------------------------------------------
# Model ID resolution
# ---------------------------------------------------------------------------


def resolve_model_id() -> tuple[str, str]:
    """Return (model_id, source) — env var → cache file → base model."""
    env_model = env_key("PIONEER_MODEL_ID")
    if env_model:
        return env_model, "env:PIONEER_MODEL_ID"

    if MODEL_CACHE.is_file():
        cached = MODEL_CACHE.read_text().strip()
        if cached:
            return cached, f"cache:{MODEL_CACHE.name}"

    return BASE_MODEL, "base-model (zero-shot)"


def cache_model_id(model_id: str) -> None:
    MODEL_CACHE.write_text(model_id + "\n")
    notice(f"pioneer: cached model id → {MODEL_CACHE.name}")


# ---------------------------------------------------------------------------
# Training pipeline (--train mode)
# ---------------------------------------------------------------------------


def _poll_until(
    client: PioneerClient,
    poll_fn,
    job_id: str,
    terminal: set[str],
    label: str,
) -> dict:
    """Poll a job until it reaches a terminal state or timeout."""
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        try:
            status = poll_fn(job_id)
        except Exception as exc:
            warn(f"pioneer: poll error for {label} ({exc}); retrying")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        state = status.get("status", "unknown")
        count = status.get("count", "")
        detail = f" ({count} examples)" if count else ""
        notice(f"pioneer: {label} status={state}{detail}")

        if state in terminal:
            return status
        if state == "failed":
            err = status.get("error", "unknown error")
            raise RuntimeError(f"{label} failed: {err}")
        time.sleep(POLL_INTERVAL_SEC)

    raise RuntimeError(f"{label} timed out after {POLL_TIMEOUT_SEC}s")


def run_training(client: PioneerClient) -> str:
    """Full training pipeline: generate data → train → return model id."""
    # Step 1: generate synthetic data
    notice(f"pioneer: generating {NUM_EXAMPLES} synthetic NER examples...")
    gen_job_id = client.generate_data(
        dataset_name=DATASET_NAME,
        labels=ENTITY_LABELS,
        domain_description=DOMAIN_DESCRIPTION,
        num_examples=NUM_EXAMPLES,
    )
    notice(f"pioneer: generation job {gen_job_id} queued")

    gen_result = _poll_until(
        client,
        client.poll_generation,
        gen_job_id,
        terminal={"ready"},
        label="data generation",
    )
    notice(f"pioneer: dataset '{DATASET_NAME}' ready ({gen_result.get('count', '?')} examples)")

    # Step 2: start training
    notice(f"pioneer: starting training on {BASE_MODEL} (LoRA, {TRAINING_EPOCHS} epochs)...")
    train_job_id = client.start_training(
        model_name="kytos-bio-ner-v1",
        base_model=BASE_MODEL,
        dataset_name=DATASET_NAME,
    )
    notice(f"pioneer: training job {train_job_id} requested")

    train_result = _poll_until(
        client,
        client.poll_training,
        train_job_id,
        terminal={"complete", "deployed"},
        label="training",
    )

    metrics = train_result.get("metrics") or {}
    if metrics:
        notice(
            f"pioneer: training complete — F1={metrics.get('f1', '?')} "
            f"precision={metrics.get('precision', '?')} "
            f"recall={metrics.get('recall', '?')}"
        )
    else:
        notice("pioneer: training complete (no metrics returned)")

    # Step 3: cache model id
    cache_model_id(train_job_id)
    return train_job_id


# ---------------------------------------------------------------------------
# Entity extraction (--run mode)
# ---------------------------------------------------------------------------


def _combine_text(literature_payload: dict) -> str:
    """Concatenate all search result snippets into one text for NER."""
    parts = []
    for result in literature_payload.get("results") or []:
        title = result.get("title") or ""
        snippet = result.get("snippet") or result.get("content") or ""
        if title:
            parts.append(title)
        if snippet:
            parts.append(snippet)
    return " ".join(parts)[:3000]  # cap at 3k chars


def extract_entities(client: PioneerClient, model_id: str, text: str) -> list[dict]:
    """Run NER and normalize to a clean entity list."""
    raw = client.infer(model_id, text, ENTITY_LABELS, threshold=0.3)
    # Pioneer /inference returns entities in various shapes; normalize.
    entities = raw.get("entities") or raw.get("predictions") or raw.get("data") or []
    cleaned = []
    for ent in entities:
        if isinstance(ent, dict):
            cleaned.append(
                {
                    "text": ent.get("text") or ent.get("entity") or ent.get("span", ""),
                    "label": ent.get("label") or ent.get("type") or ent.get("class", ""),
                    "score": round(float(ent.get("score", 0.0)), 4),
                }
            )
        elif isinstance(ent, str):
            cleaned.append({"text": ent, "label": "", "score": 0.0})
    return cleaned


def run_extraction(run_dir: Path, client: PioneerClient, model_id: str, model_source: str) -> None:
    """Extract entities from all literature/*.json files in a run."""
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        notice("pioneer: no literature/ directory — run enrich_literature.py first; skipping")
        return

    lit_files = sorted(lit_dir.glob("*.json"))
    # Skip our own .entities.json files
    lit_files = [f for f in lit_files if not f.stem.endswith(".entities")]
    if not lit_files:
        notice("pioneer: no literature JSON files found; skipping")
        return

    notice(
        f"pioneer: extracting entities from {len(lit_files)} literature file(s) via {model_source}"
    )

    for lit_path in lit_files:
        gene = lit_path.stem
        try:
            payload = json.loads(lit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warn(f"pioneer: skip {lit_path.name} (invalid JSON)")
            continue

        text = _combine_text(payload)
        if not text.strip():
            notice(f"pioneer: skip {lit_path.name} (no text to extract)")
            continue

        try:
            entities = extract_entities(client, model_id, text)
        except Exception as exc:
            warn(f"pioneer: extraction failed for {gene} ({exc}); continuing")
            continue

        out_path = lit_dir / f"{gene}.entities.json"
        result = {
            "gene": gene,
            "model_id": model_id,
            "model_source": model_source,
            "entities": entities,
            "generated_at": utcnow(),
        }
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        notice(f"pioneer: wrote {out_path.name} ({len(entities)} entities)")

    # Record Pioneer usage in facts.json
    facts = load_facts(run_dir)
    facts.setdefault("enrichment", {})["pioneer"] = {
        "model_id": model_id,
        "model_source": model_source,
        "entity_labels": ENTITY_LABELS,
    }
    (run_dir / "facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    notice("pioneer: updated facts.json enrichment.pioneer")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train", action="store_true", help="Generate data + fine-tune GLiNER2")
    mode.add_argument("--run", type=str, help="Extract entities from a run's literature")
    args = parser.parse_args(argv)

    api_key = env_key("PIONEER_API_KEY")
    if not api_key:
        notice("pioneer: skipped (no PIONEER_API_KEY); run degrades without entity enrichment")
        return 0

    client = PioneerClient(api_key)

    if args.train:
        try:
            model_id = run_training(client)
            notice(f"pioneer: training complete — model_id={model_id}")
            notice(
                "pioneer: run `python tools/enrich_pioneer.py "
                "--run experiments/<run-id>` to extract"
            )
        except PioneerAPIError as exc:
            if exc.status_code == 402 or "payment_method" in str(exc.body).lower():
                warn(
                    "pioneer: billing required — add a payment method at "
                    "https://agent.pioneer.ai/billing to enable training"
                )
            else:
                warn(f"pioneer: API error during training ({exc}); degrading")
            return 0
        except Exception as exc:
            warn(f"pioneer: training failed ({exc}); degrading")
            return 0

    elif args.run:
        run_dir = resolve_run_dir(args.run)
        model_id, model_source = resolve_model_id()
        try:
            run_extraction(run_dir, client, model_id, model_source)
        except PioneerAPIError as exc:
            if exc.status_code == 402 or "payment_method" in str(exc.body).lower():
                warn(
                    "pioneer: billing required — add a payment method at "
                    "https://agent.pioneer.ai/billing to enable inference"
                )
            else:
                warn(f"pioneer: API error during extraction ({exc}); degrading")
            return 0
        except Exception as exc:
            warn(f"pioneer: extraction failed ({exc}); degrading")
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
