"""Plotly chart JSON for metrics vs ceiling."""

from __future__ import annotations

import json
from typing import Any


METRIC_DESCRIPTIONS: dict[str, str] = {
    "DESigGenesRecall": "DE gene recall (FDR < 0.05)",
    "pearson_delta": "Pearson correlation of expression Δ",
    "DEDirectionMatch": "DE direction concordance (+/-)",
    "DESpearmanSignificant": "Spearman rank correlation (sig genes)",
    "DESpearmanLFC": "Spearman rank correlation (all genes)",
    "DENsigCounts": "DE gene count recovery accuracy",
    "mse": "Mean squared error (full matrix)",
    "mae": "Mean absolute error (full matrix)",
    "mse_delta": "MSE on perturbation delta vector",
    "mae_delta": "MAE on perturbation delta vector",
    "clustering_agreement": "Latent cluster preservation",
    "discrimination_score": "Control vs perturbed discriminability",
}


def metrics_bar_chart(metrics: list[str], scores: list[float], ceilings: list[float]) -> str:
    hover_scores = [
        f"<b>{m}</b><br>Score: {s:.4g}<br><i>{METRIC_DESCRIPTIONS.get(m, '')}</i>"
        for m, s in zip(metrics, scores)
    ]
    hover_ceilings = [
        f"<b>{m}</b><br>Ceiling: {c:.4g}<br><i>{METRIC_DESCRIPTIONS.get(m, '')}</i>"
        for m, c in zip(metrics, ceilings)
    ]

    figure: dict[str, Any] = {
        "data": [
            {
                "type": "bar",
                "name": "Score",
                "x": metrics,
                "y": scores,
                "hovertext": hover_scores,
                "hoverinfo": "text",
                "marker": {"color": "#5eead4"},
            },
            {
                "type": "bar",
                "name": "Ceiling",
                "x": metrics,
                "y": ceilings,
                "hovertext": hover_ceilings,
                "hoverinfo": "text",
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
            "height": 240,
        },
        "config": {"displayModeBar": False, "responsive": True},
    }
    return json.dumps(figure)
