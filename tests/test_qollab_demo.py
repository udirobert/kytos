"""Tests for the Qollab 4-node KRAS CTQW slice demo (qollab/main.py)."""

import importlib.util
import runpy
from pathlib import Path

import numpy as np
import pytest
from qiskit import QuantumCircuit
from scipy.linalg import expm

QOLLAB_MAIN = Path(__file__).resolve().parent.parent / "qollab" / "main.py"

NODE_ORDER = [0, 3, 11, 8]
EXPECTED_CLASSICAL_T2 = (0.07991, 0.05758)
EXPECTED_IDEAL_T2 = (0.19051, 0.40502)


def load_module():
    spec = importlib.util.spec_from_file_location("qollab_main", QOLLAB_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def module():
    return load_module()


def test_edges_times_and_slice(module):
    assert module.RECORDED_EDGES == [(0, 1), (0, 2), (1, 2), (2, 3)]
    assert module.ALTERED_EDGES == [(0, 1), (1, 2), (2, 3)]
    assert module.TIMES == [0.5, 1.0, 1.5, 2.0, 3.0]
    assert module.MEASURED_TIME == 2.0
    assert module.SOURCE == 0 and module.SITE == 3

    import json

    graph_path = (
        QOLLAB_MAIN.parent.parent
        / "experiments/cleveland/c008-moth-qpu-tomography"
        / "metrics/graphs/kras_core.json"
    )
    g = json.loads(graph_path.read_text())
    for orig in NODE_ORDER:
        assert str(orig) in g["node_map"]
    orig_edges = {tuple(sorted(e)) for e in g["edges"]}
    for i, j in module.RECORDED_EDGES:
        assert tuple(sorted((NODE_ORDER[i], NODE_ORDER[j]))) in orig_edges


def test_t2_reference_values(module):
    for edges, c_exp, q_exp in zip(
        (module.RECORDED_EDGES, module.ALTERED_EDGES),
        EXPECTED_CLASSICAL_T2,
        EXPECTED_IDEAL_T2,
    ):
        assert module.classical_site_probability(edges, 2.0) == pytest.approx(c_exp, abs=1e-4)
        assert module.ideal_site_probability(edges, 2.0) == pytest.approx(q_exp, abs=1e-4)


def test_single_4q_circuit(module):
    qc = module.build_circuit()
    assert isinstance(qc, QuantumCircuit)
    assert qc.num_qubits == 4 and qc.num_clbits == 4
    ops = [inst.operation.name for inst in qc.data]
    assert ops == ["hamiltonian", "hamiltonian"] + ["measure"] * 4


def test_each_half_evolves_its_graph(module):
    # the two HamiltonianGate blocks act on disjoint qubit pairs and
    # match the per-graph exp(-iLt) unitaries
    qc = module.build_circuit()
    for inst, edges in zip(qc.data[:2], (module.RECORDED_EDGES, module.ALTERED_EDGES)):
        expected = expm(-1j * module.laplacian(edges) * 2.0)
        assert np.allclose(inst.operation.to_matrix(), expected)
    assert [qc.find_bit(q).index for q in qc.data[0].qubits] == [0, 1]
    assert [qc.find_bit(q).index for q in qc.data[1].qubits] == [2, 3]


def test_site_marginals_orientation(module):
    # '0011' -> only recorded pair at site; '1100' -> only altered pair
    rec, alt = module.site_marginals({"0011": 2048}, 2048)
    assert rec == 1.0 and alt == 0.0
    rec, alt = module.site_marginals({"1100": 2048}, 2048)
    assert rec == 0.0 and alt == 1.0
    rec, alt = module.site_marginals({"1111": 100, "0011": 50, "0000": 854}, 1004)
    assert rec == pytest.approx(150 / 1004)
    assert alt == pytest.approx(100 / 1004)


def test_qollab_injection_single_job_measured_t2(capsys):
    from qiskit.providers.basic_provider import BasicSimulator

    backend = BasicSimulator()
    calls = []
    orig_run = backend.run

    def counting_run(circuit, **kwargs):
        calls.append(circuit)
        return orig_run(circuit, **kwargs)

    backend.run = counting_run
    namespace = runpy.run_path(str(QOLLAB_MAIN), init_globals={"backend": backend})
    meas_rec, meas_alt = namespace["main"](shots=4096)

    assert len(calls) == 1
    qc = calls[0]
    assert isinstance(qc, QuantumCircuit)
    assert qc.num_qubits == 4

    assert meas_rec == pytest.approx(EXPECTED_IDEAL_T2[0], abs=0.05)
    assert meas_alt == pytest.approx(EXPECTED_IDEAL_T2[1], abs=0.05)

    out = capsys.readouterr().out
    assert "not measurements" in out
    assert "no quantum advantage" in out
    assert "not allosteric site recovery" in out
    assert "removing edge (0,2)" in out
    for t in ("0.5", "1.0", "1.5", "2.0", "3.0"):
        assert f"{float(t):>4.1f}" in out
