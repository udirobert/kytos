"""Deterministic biological sanity rules (lemma-derived sidecar checks).

Each rule takes a ``context`` dict (the structured audit input for a run) and
returns a list of :class:`AuditFlag`. Rules are pure functions — no I/O, no
network, no randomness. They run at build time and the results land in
``facts.json`` alongside the cell-eval metrics.

Implemented rules:
  - housekeeping_shift      : large shifts in housekeeping genes
  - pathway_coherence      : mixed-directionality or wrong-direction pathways
  - control_group_stability: control (non-targeting) group should not shift
  - dose_response          : knockdown magnitude should track gene-level effect
  - gene_group_coherence   : genes in the same functional group should move together
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class AuditFlag:
    id: str
    severity: Severity
    genes: list[str]
    rule: str
    message: str
    discuss_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "severity": self.severity,
            "genes": self.genes,
            "rule": self.rule,
            "message": self.message,
        }
        if self.discuss_url:
            out["discuss_url"] = self.discuss_url
        return out


# log2 fold-change vs basal above which housekeeping shift is flagged
HOUSEKEEPING_SHIFT_THRESHOLD = 1.0

HOUSEKEEPING_GENES = ("ACTB", "GAPDH", "B2M", "PPIA")


def rule_housekeeping_shift(context: dict[str, Any]) -> list[AuditFlag]:
    """Flag large shifts in housekeeping genes (metric-passing but biologically odd)."""
    shifts = context.get("housekeeping_shifts") or {}
    flagged: list[tuple[str, float]] = []
    for gene in HOUSEKEEPING_GENES:
        if gene not in shifts:
            continue
        value = float(shifts[gene])
        if abs(value) >= HOUSEKEEPING_SHIFT_THRESHOLD:
            flagged.append((gene, value))

    if not flagged:
        return []

    genes = [gene for gene, _ in flagged]
    max_gene, max_val = max(flagged, key=lambda item: abs(item[1]))
    return [
        AuditFlag(
            id="hk-stability",
            severity="warn",
            genes=genes,
            rule="housekeeping_shift",
            message=(
                f"Housekeeping genes shifted up to {max_val:+.2f} log2FC "
                f"(threshold ±{HOUSEKEEPING_SHIFT_THRESHOLD}); peak {max_gene}."
            ),
        )
    ]


def rule_pathway_coherence(context: dict[str, Any]) -> list[AuditFlag]:
    """Flag pathway gene sets with incoherent directionality after perturbation."""
    flags: list[AuditFlag] = []
    for pathway in context.get("pathways") or []:
        name = str(pathway.get("name", "pathway"))
        genes = list(pathway.get("genes") or [])
        shifts = pathway.get("gene_shifts") or {}
        if not genes or not shifts:
            continue

        values = [float(shifts[gene]) for gene in genes if gene in shifts]
        if len(values) < 2:
            continue

        positive = sum(1 for value in values if value > 0.25)
        negative = sum(1 for value in values if value < -0.25)
        if positive > 0 and negative > 0:
            flags.append(
                AuditFlag(
                    id=f"pathway-{name}",
                    severity="warn",
                    genes=genes,
                    rule="pathway_coherence",
                    message=(
                        f"Pathway {name!r} shows mixed directionality "
                        f"({positive} up, {negative} down among measured genes)."
                    ),
                )
            )
            continue

        expected = pathway.get("expected_direction")
        if expected in ("down", "up"):
            mean_shift = sum(values) / len(values)
            wrong = (expected == "down" and mean_shift > 0.5) or (
                expected == "up" and mean_shift < -0.5
            )
            if wrong:
                flags.append(
                    AuditFlag(
                        id=f"pathway-{name}",
                        severity="warn",
                        genes=genes,
                        rule="pathway_coherence",
                        message=(
                            f"Pathway {name!r} mean shift {mean_shift:+.2f} log2FC "
                            f"opposes expected {expected} direction after knockdown."
                        ),
                    )
                )
    return flags


def rule_control_group_stability(context: dict[str, Any]) -> list[AuditFlag]:
    """Flag when the non-targeting control group shifts off baseline.

    The control (non-targeting guides) should remain close to the unperturbed
    basal state. A systematic shift in the control group means the pipeline
    normalisation, batch effect, or guide-design is leaking into every cell —
    making the per-gene perturbation signals uninterpretable.
    """
    ctrl = context.get("control_group") or {}
    shifts = ctrl.get("gene_shifts") or {}
    threshold = float(ctrl.get("max_shift_threshold", 0.5))

    flagged = [(gene, float(val)) for gene, val in shifts.items() if abs(float(val)) >= threshold]
    if not flagged:
        return []

    genes = [g for g, _ in flagged]
    max_gene, max_val = max(flagged, key=lambda item: abs(item[1]))
    return [
        AuditFlag(
            id="ctrl-stability",
            severity="error",
            genes=genes,
            rule="control_group_stability",
            message=(
                f"Non-targeting control group shifted up to {max_val:+.2f} log2FC "
                f"(threshold ±{threshold}); peak {max_gene}. "
                f"Per-gene perturbation signals may be contaminated."
            ),
        )
    ]


def rule_dose_response(context: dict[str, Any]) -> list[AuditFlag]:
    """Flag knockdowns where the gene-level effect does not track knockdown strength.

    A strong CRISPRi knockdown (high % reduction at the guide level) should
    produce a proportionate expression shift at the target gene. If a gene
    shows high knockdown but near-zero shift (or vice-versa), the prediction is
    either saturating, leaking, or the guide is off-target — all biologically
    suspicious even if the metric passes.
    """
    flags: list[AuditFlag] = []
    for item in context.get("dose_response") or []:
        gene = str(item.get("gene", ""))
        knockdown = float(item.get("knockdown_pct", 0.0))  # 0–100
        shift = float(item.get("target_shift", 0.0))  # log2FC
        if not gene:
            continue

        # Strong knockdown (>70%) should produce a meaningful shift (>0.5 log2FC)
        strong_knockdown = knockdown >= 70.0
        weak_shift = abs(shift) < 0.5
        if strong_knockdown and weak_shift:
            flags.append(
                AuditFlag(
                    id=f"dose-{gene}",
                    severity="warn",
                    genes=[gene],
                    rule="dose_response",
                    message=(
                        f"Gene {gene} shows {knockdown:.0f}% knockdown but only "
                        f"{shift:+.2f} log2FC target shift — effect is not "
                        f"proportionate to knockdown strength."
                    ),
                )
            )
            continue

        # Low knockdown (<20%) should not produce a large shift (>2.0 log2FC)
        weak_knockdown = knockdown <= 20.0
        large_shift = abs(shift) > 2.0
        if weak_knockdown and large_shift:
            flags.append(
                AuditFlag(
                    id=f"dose-{gene}",
                    severity="warn",
                    genes=[gene],
                    rule="dose_response",
                    message=(
                        f"Gene {gene} shows only {knockdown:.0f}% knockdown but "
                        f"{shift:+.2f} log2FC shift — suspected off-target or "
                        f"leaky guide."
                    ),
                )
            )
    return flags


def rule_gene_group_coherence(context: dict[str, Any]) -> list[AuditFlag]:
    """Flag functional gene groups that should move coherently after perturbation.

    Genes annotated to the same functional group (e.g. ribosomal, proteasome,
    cell-cycle) are expected to shift in a coordinated direction after a
    perturbation that affects that group. High variance within a group — some
    genes up, others down strongly — suggests the prediction is producing
    biologically incoherent states even if individual gene scores pass.
    """
    flags: list[AuditFlag] = []
    for group in context.get("gene_groups") or []:
        name = str(group.get("name", "group"))
        genes = list(group.get("genes") or [])
        shifts = group.get("gene_shifts") or {}
        if len(genes) < 3:
            continue

        values = [float(shifts[g]) for g in genes if g in shifts]
        if len(values) < 3:
            continue

        mean_shift = sum(values) / len(values)
        pos_sum = sum(v for v in values if v > 0)
        neg_sum = sum(abs(v) for v in values if v < 0)
        if pos_sum >= neg_sum:
            opposing = [g for g in genes if g in shifts and float(shifts[g]) <= -0.5]
        else:
            opposing = [g for g in genes if g in shifts and float(shifts[g]) >= 0.5]

        if opposing:
            flags.append(
                AuditFlag(
                    id=f"group-{name}",
                    severity="info",
                    genes=opposing,
                    rule="gene_group_coherence",
                    message=(
                        f"Functional group {name!r} (mean shift {mean_shift:+.2f} log2FC) "
                        f"has {len(opposing)} gene(s) moving against the group "
                        f"direction — possible incoherent state."
                    ),
                )
            )
    return flags


def _opposes(value: float, mean: float, margin: float = 1.0) -> bool:
    """True when ``value`` moves opposite to ``mean`` by more than ``margin``."""
    if abs(mean) < 0.3:
        # Near-zero mean: any large individual shift is suspicious
        return abs(value) > margin
    if mean > 0:
        return value < mean - margin
    return value > mean + margin


ALL_RULES = (
    rule_housekeeping_shift,
    rule_pathway_coherence,
    rule_control_group_stability,
    rule_dose_response,
    rule_gene_group_coherence,
)


def run_all_rules(context: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[AuditFlag] = []
    for rule in ALL_RULES:
        flags.extend(rule(context))
    return [flag.to_dict() for flag in flags]
