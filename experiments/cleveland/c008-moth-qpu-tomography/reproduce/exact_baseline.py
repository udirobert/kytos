"""Exact graph-state tomography baseline for a coupling_map graph.

|G> = prod_{(a,b) in edges} CZ_ab |+>^n — computed exactly in a 2^n statevector.
Two-qubit Pauli expectations per edge + single-qubit Bloch vectors, exact
(no shot noise) — the reference the Aer emu result only approximates.

Usage: python exact_baseline.py <core.json> <out.json>
"""

import json
import sys

import numpy as np

PAULI = {
    "I": np.eye(2, dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}
PAIRS = [(a + b) for a in "XYZ" for b in "XYZ"]


def graph_state(n: int, edges: list[list[int]]) -> np.ndarray:
    psi = np.full(2**n, 1.0 / np.sqrt(2**n), dtype=complex)
    psi_t = psi.reshape([2] * n)
    for a, b in edges:
        # CZ: flip sign of amplitudes where both qubits are |1>
        mask = np.ones([2] * n, dtype=complex)
        m = [slice(None)] * n
        m[a] = 1
        m[b] = 1
        mask[tuple(m)] = -1.0
        psi_t = psi_t * mask
    return psi_t.reshape(-1)


def apply_pauli(psi_t: np.ndarray, qubit: int, p: np.ndarray) -> np.ndarray:
    out = np.tensordot(p, psi_t, axes=([1], [qubit]))
    # tensordot puts the contracted axis first; move back
    out = np.moveaxis(out, 0, qubit)
    return out


def main() -> None:
    core = json.load(open(sys.argv[1]))
    edges = core["edges"]
    n = core["n_nodes"]
    psi = graph_state(n, edges)
    psi_t = psi.reshape([2] * n)
    norm = np.vdot(psi, psi)
    assert abs(norm - 1) < 1e-9, norm

    bloch = {}
    for q in range(n):
        vals = {}
        for p in "XYZ":
            phi = apply_pauli(psi_t, q, PAULI[p]).reshape(-1)
            vals[p] = float(np.vdot(psi, phi).real)
        bloch[str(q)] = vals

    relationships = {}
    for a, b in edges:
        vals = {}
        for pa, pb in PAIRS:
            phi = apply_pauli(psi_t, a, PAULI[pa])
            phi = apply_pauli(phi, b, PAULI[pb]).reshape(-1)
            vals[pa + pb] = float(np.vdot(psi, phi).real)
        relationships[f"{a},{b}"] = vals

    json.dump(
        {"n": n, "edges": edges, "bloch": bloch, "relationships": relationships},
        open(sys.argv[2], "w"),
        indent=1,
    )
    print(f"exact baseline: {n} qubits, {len(edges)} edges -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
