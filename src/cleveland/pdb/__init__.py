"""PDB fetch + catalytic-domain CA/CB coordinate extraction."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from Bio.PDB import PDBParser, is_aa

from cleveland.targets import TargetStructure

RCSB_DOWNLOAD = "https://files.rcsb.org/download/{pdb_id}.pdb"


@dataclass
class ResidueNode:
    """One polymer residue kept in the contact graph."""

    chain: str
    resseq: int
    resname: str
    coord: np.ndarray  # (3,) Å
    index: int = -1


def pdb_path(raw_dir: Path, pdb_id: str) -> Path:
    return raw_dir / f"{pdb_id.upper()}.pdb"


def fetch_pdb(pdb_id: str, raw_dir: Path, *, force: bool = False) -> Path:
    """Download a PDB file from RCSB into `raw_dir` if missing."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = pdb_path(raw_dir, pdb_id)
    if out.exists() and not force:
        return out
    url = RCSB_DOWNLOAD.format(pdb_id=pdb_id.upper())
    with urllib.request.urlopen(url, timeout=60) as resp:
        out.write_bytes(resp.read())
    return out


def _in_ranges(resseq: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    if not ranges:
        return True
    return any(lo <= resseq <= hi for lo, hi in ranges)


def _atom_coord(residue, atom_mode: str) -> np.ndarray | None:
    if atom_mode.upper() == "CB":
        if "CB" in residue:
            return residue["CB"].coord.copy()
        if "CA" in residue:  # glycine fallback
            return residue["CA"].coord.copy()
        return None
    if "CA" in residue:
        return residue["CA"].coord.copy()
    return None


def load_residue_nodes(
    structure: TargetStructure,
    raw_dir: Path,
    *,
    atom_mode: str = "CA",
    fetch: bool = True,
) -> list[ResidueNode]:
    """Parse polymer residues on the target chain (std. AA only)."""
    path = fetch_pdb(structure.pdb_id, raw_dir) if fetch else pdb_path(raw_dir, structure.pdb_id)
    if not path.exists():
        raise FileNotFoundError(path)

    parser = PDBParser(QUIET=True)
    model = parser.get_structure(structure.pdb_id, path)[0]
    if structure.chain not in model:
        available = [c.id for c in model]
        raise KeyError(f"{structure.pdb_id}: chain {structure.chain!r} not in {available}")

    nodes: list[ResidueNode] = []
    for res in model[structure.chain]:
        het, resseq, _ic = res.id
        if het != " ":
            continue
        if not is_aa(res, standard=True):
            continue
        if not _in_ranges(int(resseq), structure.residue_ranges):
            continue
        coord = _atom_coord(res, atom_mode)
        if coord is None:
            continue
        nodes.append(
            ResidueNode(
                chain=structure.chain,
                resseq=int(resseq),
                resname=res.get_resname(),
                coord=np.asarray(coord, dtype=np.float64),
            )
        )

    for i, n in enumerate(nodes):
        n.index = i
    if not nodes:
        raise ValueError(f"{structure.pdb_id}: no residues after domain filter")
    return nodes


def coords_matrix(nodes: list[ResidueNode]) -> np.ndarray:
    return np.stack([n.coord for n in nodes], axis=0)
