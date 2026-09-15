"""Tests for Qiskit CTQW packaging fidelity."""

from __future__ import annotations

import numpy as np
import pytest

from cleveland.circuit import ctqw_scores_qiskit, padded_hamiltonian
from cleveland.walk.ctqw import graph_hamiltonian, time_averaged_transition_probs

qiskit = pytest.importorskip("qiskit")


def test_pad_pow2():
    h = np.eye(3)
    hp, dim = padded_hamiltonian(h)
    assert dim == 4
    assert hp.shape == (4, 4)
    assert np.allclose(hp[:3, :3], h)


def test_qiskit_matches_exact_on_path():
    a = np.array(
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    h = graph_hamiltonian(a, form="laplacian")
    exact, _ = time_averaged_transition_probs(h, [0], t_max=2.0, n_times=12)
    q_scores, pkg = ctqw_scores_qiskit(h, [0], t_max=2.0, n_times=12)
    assert pkg.n_qubits == 2
    assert pkg.fidelity_vs_exact == pytest.approx(1.0, abs=1e-6)
    assert np.allclose(q_scores, exact, atol=1e-6)
