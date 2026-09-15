"""CTQW circuit packaging — same metric as exact eigh, NISQ-shaped wrapper.

Uses Qiskit ``HamiltonianGate`` on a zero-padded Hilbert space (next power of
two). Braket / Classiq entry points are optional stubs that export the same
Hamiltonian + times for challenge hardware later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from cleveland.graph import adjacency_matrix
from cleveland.walk.ctqw import graph_hamiltonian


@dataclass
class CircuitPackage:
    """Serializable package for hardware backends."""

    n_nodes: int
    n_qubits: int
    hamiltonian_form: str
    t_max: float
    n_times: int
    pad_dim: int
    backend: str
    depth_note: str
    fidelity_vs_exact: float | None = None


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def padded_hamiltonian(h: np.ndarray) -> tuple[np.ndarray, int]:
    """Zero-pad H to 2^k × 2^k for qubit encoding."""
    n = h.shape[0]
    dim = _next_pow2(n)
    if dim == n:
        return h.astype(np.complex128), dim
    hp = np.zeros((dim, dim), dtype=np.complex128)
    hp[:n, :n] = h
    return hp, dim


def ctqw_scores_qiskit(
    h: np.ndarray,
    source_dense_idx: list[int],
    t_max: float,
    *,
    n_times: int = 32,
) -> tuple[np.ndarray, CircuitPackage]:
    """Statevector CTQW via Qiskit HamiltonianGate; metric matches exact eigh.

    Sources are an *incoherent* mixture (average of |s⟩ evolutions), matching
    ``time_averaged_transition_probs`` — not a coherent superposition.
    """
    from qiskit.circuit.library import HamiltonianGate
    from qiskit.quantum_info import Operator, Statevector

    n = h.shape[0]
    hp, dim = padded_hamiltonian(h)
    n_qubits = int(np.log2(dim))
    times = np.linspace(0.0, t_max, n_times)

    from cleveland.walk.ctqw import time_averaged_transition_probs

    exact_scores, _ = time_averaged_transition_probs(h, source_dense_idx, t_max, n_times=n_times)

    sources = [i for i in source_dense_idx if 0 <= i < n]
    if not sources:
        raise ValueError("no valid sources")

    acc = np.zeros(n, dtype=np.float64)
    for t in times:
        if t > 0:
            op = Operator(HamiltonianGate(hp, t))
        else:
            op = None
        batch = np.zeros(n, dtype=np.float64)
        for s in sources:
            psi0 = np.zeros(dim, dtype=np.complex128)
            psi0[s] = 1.0
            sv = Statevector(psi0)
            if op is not None:
                sv = sv.evolve(op)
            batch += np.abs(np.asarray(sv.data)[:n]) ** 2
        acc += batch / len(sources)
    acc /= n_times

    fid = float(np.corrcoef(acc, exact_scores)[0, 1]) if n > 1 else 1.0
    if not np.isfinite(fid):
        fid = float(1.0 - np.linalg.norm(acc - exact_scores))
    pkg = CircuitPackage(
        n_nodes=n,
        n_qubits=n_qubits,
        hamiltonian_form="from_input_H",
        t_max=t_max,
        n_times=n_times,
        pad_dim=dim,
        backend="qiskit_statevector_hamiltonian_gate",
        depth_note=(
            "Incoherent average over source basis states (matches exact metric). "
            "HamiltonianGate is the ideal unitary; NISQ must Trotterize under "
            "Braket/Classiq depth budgets without changing the metric."
        ),
        fidelity_vs_exact=fid,
    )
    return acc, pkg


def package_graph_ctqw(
    g,
    source_graph_nodes: list[int],
    t_max: float,
    *,
    hamiltonian: str = "laplacian",
    n_times: int = 32,
) -> dict[str, Any]:
    """Build H from graph, run Qiskit packaging, return scores + package dict."""
    a, node_order = adjacency_matrix(g)
    idx = {n: i for i, n in enumerate(node_order)}
    sources = [idx[n] for n in source_graph_nodes if n in idx]
    h = graph_hamiltonian(a, form=hamiltonian)
    scores, pkg = ctqw_scores_qiskit(h, sources, t_max, n_times=n_times)
    return {
        "scores": scores,
        "node_order": node_order,
        "package": asdict(pkg),
        "hamiltonian": hamiltonian,
    }


def braket_export_payload(
    h: np.ndarray, times: list[float], *, include_matrix: bool = False
) -> dict[str, Any]:
    """JSON-serializable payload for AWS Braket Hamiltonian simulation jobs."""
    hp, dim = padded_hamiltonian(h)
    out: dict[str, Any] = {
        "backend": "aws_braket",
        "status": "export_only",
        "n_qubits": int(np.log2(dim)),
        "n_nodes": int(h.shape[0]),
        "pad_dim": int(dim),
        "evolution_times": times,
        "note": (
            "Submit via amazon-braket-sdk when challenge credentials are active; "
            "metric target is time-averaged |U_ij|^2 matching exact eigh. "
            "Hamiltonian matrix stored alongside as .npy."
        ),
    }
    if include_matrix:
        out["hamiltonian_real"] = hp.real.tolist()
        out["hamiltonian_imag"] = hp.imag.tolist()
    return out


def classiq_export_payload(n_qubits: int, t_max: float) -> dict[str, Any]:
    """Placeholder for Classiq model generation (SDK optional)."""
    return {
        "backend": "classiq",
        "status": "export_only",
        "n_qubits": n_qubits,
        "t_max": t_max,
        "note": (
            "Classiq synthesis should target Hamiltonian evolution of the padded "
            "ENM Laplacian under challenge depth limits; install classiq in "
            ".venv-cleveland when ready."
        ),
    }
