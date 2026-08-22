"""Biological sanity layer over predictions (lemma-derived).

Sidecar checks: housekeeping-gene stability, control-group sanity, gene-group
coherence, known dose/direction. Blocks impossible-in-vivo genes; never fits a
single biomarker to climb a metric.

Public API::

    from kytos.audit import run_all_rules, AuditFlag, ALL_RULES
"""

from kytos.audit.rules import ALL_RULES, AuditFlag, Severity, run_all_rules

__all__ = ["ALL_RULES", "AuditFlag", "Severity", "run_all_rules"]
