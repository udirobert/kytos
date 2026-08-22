"""Plotly chart JSON for metrics vs ceiling."""

from __future__ import annotations

import json
from typing import Any


def metrics_bar_chart(metrics: list[str], scores: list[float], ceilings: list[float]) -> str:
    figure: dict[str, Any] = {
        "data": [
            {
                "type": "bar",
                "name": "Score",
                "x": metrics,
                "y": scores,
                "marker": {"color": "#5eead4"},
            },
            {
                "type": "bar",
                "name": "Ceiling",
                "x": metrics,
                "y": ceilings,
                "marker": {"color": "#67e8f9", "opacity": 0.55},
            },
        ],
        "layout": {
            "barmode": "group",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#cbd5e1", "family": "IBM Plex Mono, monospace", "size": 11},
            "margin": {"l": 48, "r": 16, "t": 24, "b": 72},
            "xaxis": {
                "tickangle": -28,
                "gridcolor": "rgba(148,163,184,0.12)",
                "linecolor": "rgba(148,163,184,0.2)",
            },
            "yaxis": {
                "range": [0, max([*ceilings, *scores, 0.1]) * 1.15],
                "gridcolor": "rgba(148,163,184,0.12)",
                "linecolor": "rgba(148,163,184,0.2)",
            },
            "legend": {
                "orientation": "h",
                "y": 1.12,
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
            },
            "height": 320,
        },
        "config": {"displayModeBar": False, "responsive": True},
    }
    return json.dumps(figure)
