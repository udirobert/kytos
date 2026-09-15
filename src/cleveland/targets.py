"""Benchmark target definitions for Phase 1 (topology-only).

Active-site residue sets are the CTRW/CTQW *source* nodes (catalytic /
nucleotide / ATP pocket), not the known allosteric sites. Known allosteric
residues are recorded for post-hoc scoring only — never used as model input.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetStructure:
    """One PDB entry in the blind benchmark table."""

    pdb_id: str
    role: str  # apo | holo | exploratory
    chain: str
    # Inclusive auth residue ranges kept after catalytic-domain filter.
    # Empty tuple = keep all polymer residues on `chain`.
    residue_ranges: tuple[tuple[int, int], ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkTarget:
    """One disease target with apo input (+ optional holo for later scoring)."""

    target_id: str
    name: str
    apo: TargetStructure
    holo: TargetStructure | None
    # Source nodes for the walk (active / orthosteric pocket), auth seq ids.
    active_site_residues: tuple[int, ...]
    # Blind labels — for audit after prediction only.
    known_allosteric_residues: tuple[int, ...] = ()
    known_allosteric_label: str = ""
    atom_mode: str = "CA"  # CA default; CB near pocket if needed later


# Residue lists are literature-standard pocket anchors for these structures.
# They are starting points; refine in meta.json notes if domain masks change.

TARGETS: dict[str, BenchmarkTarget] = {
    "kras_g12c": BenchmarkTarget(
        target_id="kras_g12c",
        name="KRAS G12C",
        apo=TargetStructure("4OBE", "apo", "A", (), "G domain"),
        holo=TargetStructure("6OIM", "holo", "A", (), "Sotorasib-bound"),
        # Nucleotide / Switch region orthosteric neighborhood (GTP site).
        active_site_residues=(12, 13, 14, 15, 16, 17, 18, 29, 30, 32, 34, 35, 116, 119, 120),
        known_allosteric_residues=(12, 96, 99, 117),  # Switch-II / Sotorasib contacts (approx)
        known_allosteric_label="Switch-II pocket (Sotorasib)",
    ),
    "bcr_abl1": BenchmarkTarget(
        target_id="bcr_abl1",
        name="BCR-ABL1",
        apo=TargetStructure(
            "1OPL",
            "apo",
            "A",
            ((229, 515),),
            "Abl kinase domain (approx SH1)",
        ),
        holo=TargetStructure(
            "5MO4",
            "holo",
            "A",
            ((229, 515),),
            "Asciminib-bound",
        ),
        # ATP-site hinge / catalytic residues (Abl numbering).
        active_site_residues=(248, 253, 269, 270, 271, 286, 289, 290, 317, 359, 361, 381),
        known_allosteric_residues=(298, 317, 334, 370, 379),  # myristoyl pocket anchors
        known_allosteric_label="Myristoyl pocket (Asciminib)",
    ),
    "cardiac_myosin": BenchmarkTarget(
        target_id="cardiac_myosin",
        name="Cardiac myosin",
        apo=TargetStructure(
            "5TBY",
            "apo",
            "A",
            ((1, 800),),
            "Motor domain (truncated if full heavy chain present)",
        ),
        holo=TargetStructure(
            "6C1H",
            "holo",
            "P",
            ((1, 800),),
            "Mavacamten-bound myosin motor (chain P in 6C1H)",
        ),
        # ATP-binding / active site neighborhood in myosin motor.
        active_site_residues=(179, 180, 181, 182, 233, 240, 242, 461, 462, 468, 655),
        known_allosteric_residues=(403, 406, 407, 412, 639),  # SRX / mavacamten site approx
        known_allosteric_label="Super-relaxed-state site (Mavacamten)",
    ),
    "cmyc_max": BenchmarkTarget(
        target_id="cmyc_max",
        name="c-Myc/Max",
        apo=TargetStructure("1NKP", "exploratory", "A", (), "Myc chain"),
        holo=None,
        # DNA-contact / basic region as functional "source" for exploratory walk.
        active_site_residues=(914, 915, 916, 917, 918, 919, 920, 921, 922),
        known_allosteric_residues=(),
        known_allosteric_label="exploratory — no validated site",
    ),
}


# All PDBs to ingest in Phase 1 (apo + holo + exploratory).
PHASE1_PDB_JOBS: list[TargetStructure] = []
for _t in TARGETS.values():
    PHASE1_PDB_JOBS.append(_t.apo)
    if _t.holo is not None:
        PHASE1_PDB_JOBS.append(_t.holo)


@dataclass
class GraphConfig:
    cutoff_angstrom: float = 9.0
    weight: str = "inverse"  # inverse | gaussian
    gaussian_sigma: float = 4.0
    n_clusters_min: int = 32
    n_clusters_max: int = 56  # myosin ranking fidelity peaks near 56 within budget

    spearman_threshold: float = 0.8
    walk_time: float = 10.0
    atom_mode: str = "CA"
    seed: int = 0


DEFAULT_GRAPH = GraphConfig()
