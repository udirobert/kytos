"""cell-eval wrappers, run-ID generation, and metric aggregation.

Thin, deterministic layer over cell-eval run/prep/score/ceiling so a run is
reproducible from its meta.json. Produces facts JSON for any report surface.
"""
