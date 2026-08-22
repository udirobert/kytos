"""Deterministic biological sanity rules (lemma-derived sidecar checks)."""

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


ALL_RULES = (rule_housekeeping_shift, rule_pathway_coherence)


def run_all_rules(context: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[AuditFlag] = []
    for rule in ALL_RULES:
        flags.extend(rule(context))
    return [flag.to_dict() for flag in flags]
