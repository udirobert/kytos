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


def volcano_plot_chart(
    genes: list[str],
    log2fc: list[float],
    neg_log10_pval: list[float],
    *,
    flagged_genes: set[str] | None = None,
    target_genes: set[str] | None = None,
) -> str:
    """Generate Plotly interactive Volcano plot for differential expression."""
    flagged_set = flagged_genes or set()
    target_set = target_genes or set()

    # Split into category traces
    traces_data: dict[str, dict[str, list[Any]]] = {
        "Normal": {"x": [], "y": [], "text": []},
        "Significant DE": {"x": [], "y": [], "text": []},
        "Audit Flagged": {"x": [], "y": [], "text": []},
        "Target Gene": {"x": [], "y": [], "text": []},
    }

    for g, fc, p in zip(genes, log2fc, neg_log10_pval):
        hover = f"<b>{g}</b><br>log2FC: {fc:+.2f}<br>-log10(p): {p:.2f}"
        if g in target_set:
            cat = "Target Gene"
            hover += "<br><i>[CRISPRi Target]</i>"
        elif g in flagged_set:
            cat = "Audit Flagged"
            hover += "<br><i>[Biological Audit Flag]</i>"
        elif abs(fc) >= 1.0 and p >= 1.3:
            cat = "Significant DE"
        else:
            cat = "Normal"

        traces_data[cat]["x"].append(fc)
        traces_data[cat]["y"].append(p)
        traces_data[cat]["text"].append(hover)

    colors = {
        "Normal": "#64748b",
        "Significant DE": "#2dd4bf",
        "Audit Flagged": "#fb923c",
        "Target Gene": "#c084fc",
    }
    sizes = {
        "Normal": 5,
        "Significant DE": 7,
        "Audit Flagged": 10,
        "Target Gene": 11,
    }

    data = []
    for cat in ["Normal", "Significant DE", "Audit Flagged", "Target Gene"]:
        td = traces_data[cat]
        if td["x"]:
            data.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": cat,
                    "x": td["x"],
                    "y": td["y"],
                    "hovertext": td["text"],
                    "hoverinfo": "text",
                    "marker": {
                        "color": colors[cat],
                        "size": sizes[cat],
                        "opacity": 0.85 if cat != "Normal" else 0.45,
                        "line": {"width": 1, "color": "rgba(255,255,255,0.2)"},
                    },
                }
            )

    figure: dict[str, Any] = {
        "data": data,
        "layout": {
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#cbd5e1", "family": "IBM Plex Mono, monospace", "size": 11},
            "margin": {"l": 48, "r": 16, "t": 28, "b": 48},
            "xaxis": {
                "title": "log2 Fold Change (Effect Size)",
                "gridcolor": "rgba(148,163,184,0.12)",
                "linecolor": "rgba(148,163,184,0.2)",
                "zerolinecolor": "rgba(148,163,184,0.3)",
            },
            "yaxis": {
                "title": "-log10(p-value)",
                "gridcolor": "rgba(148,163,184,0.12)",
                "linecolor": "rgba(148,163,184,0.2)",
            },
            "legend": {
                "orientation": "h",
                "y": 1.15,
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
            },
            "shapes": [
                # -log10(p)=1.3 (p=0.05) threshold line
                {
                    "type": "line",
                    "x0": min(log2fc, default=-3),
                    "x1": max(log2fc, default=3),
                    "y0": 1.3,
                    "y1": 1.3,
                    "line": {"color": "rgba(148,163,184,0.25)", "dash": "dot", "width": 1},
                }
            ],
            "height": 280,
        },
        "config": {"displayModeBar": False, "responsive": True},
    }
    return json.dumps(figure)
