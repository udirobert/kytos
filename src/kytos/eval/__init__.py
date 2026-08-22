"""cell-eval wrappers, run-ID generation, and metric aggregation.

Thin, deterministic layer over cell-eval run/prep/score/ceiling so a run is
reproducible from its meta.json. Assembles facts.json for the Observatory and
other report surfaces (see docs/run-protocol.md, docs/observatory.md).

CLI: ``python -m kytos.audit --run <dir>`` then ``python -m kytos.eval.facts --run <dir>``.
"""

__all__: list[str] = []
