"""Synthesize the c002-style CTQW into OpenQASM 2 for tomography-api-v2.

Instead of handing the coupling map to graph-v1's black-box protocol, this
emits the actual Hamiltonian evolution our pipeline computes — H = D - A on
the 20-node allosteric core — as a first-order Trotter circuit:

  |psi(0)> = single excitation on the catalytic (P-loop) supernode
  U(t)    ~= prod_slices [ prod_j rz(-2 d_j dt) . prod_edges RXX(-dt) RYY(-dt) ]

verification: a numpy statevector executes the emitted gate list on all
2^20 amplitudes and the Z-basis probabilities are compared against the exact
scipy expm(-iHt) single-excitation sector. no qiskit required.

usage:
  python qasm_ctqw.py --target kras --t 2.0 --steps 1 --verify --emit out.qasm
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.linalg import expm

HERE = Path(__file__).resolve().parent
GRAPHS = HERE.parent / "metrics" / "graphs"


def load_core(target: str):
    g = json.loads((GRAPHS / f"{target}_core.json").read_text())
    edges = [tuple(e) for e in g["edges"]]
    n = g["n_nodes"]
    sources = [int(q) for q, m in g["node_map"].items() if "source" in (m.get("role") or "")]
    return n, edges, sources, g["node_map"]


def adjacency(n: int, edges: list[tuple[int, int]]) -> np.ndarray:
    a = np.zeros((n, n))
    for i, j in edges:
        a[i, j] = a[j, i] = 1.0
    return a


def choose_t(h: np.ndarray, source: int, t_max: float = 10.0, n_times: int = 64):
    """Pick the single-time snapshot whose Z-probabilities best track the
    published time-averaged CTQW scores (Pearson over nodes)."""
    w, v = np.linalg.eigh(h)
    times = np.linspace(0.0, t_max, n_times)
    avg = np.zeros(h.shape[0])
    for t in times:
        u = (v * np.exp(-1j * w * t)) @ v.T
        avg += np.abs(u[:, source]) ** 2
    avg /= n_times
    best = (0.0, -2.0)
    for t in np.linspace(0.25, 4.0, 60):
        u = (v * np.exp(-1j * w * t)) @ v.T
        p = np.abs(u[:, source]) ** 2
        r = np.corrcoef(avg, p)[0, 1]
        if r > best[1]:
            best = (t, r)
    return best


def emit_qasm(n, edges, degrees, source, t, steps, compact=None):
    dt = t / steps
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        f"qreg q[{n}];",
        f"creg c[{n}];",
        f"x q[{source}]; // single excitation at catalytic source supernode",
    ]
    ops = [("x", source, None, 0.0)]

    def rxx(a, b, g):
        lines.append(
            f"h q[{a}]; h q[{b}]; cx q[{a}],q[{b}]; "
            f"rz({g:.10f}) q[{b}]; cx q[{a}],q[{b}]; h q[{a}]; h q[{b}];"
        )
        ops.extend(
            [
                ("h", a, None, 0.0),
                ("h", b, None, 0.0),
                ("cx", a, b, 0.0),
                ("rz", b, None, g),
                ("cx", a, b, 0.0),
                ("h", a, None, 0.0),
                ("h", b, None, 0.0),
            ]
        )

    def ryy(a, b, g):
        hp = np.pi / 2
        lines.append(
            f"rx({hp:.10f}) q[{a}]; rx({hp:.10f}) q[{b}]; "
            f"cx q[{a}],q[{b}]; rz({g:.10f}) q[{b}]; cx q[{a}],q[{b}]; "
            f"rx({-hp:.10f}) q[{a}]; rx({-hp:.10f}) q[{b}];"
        )
        ops.extend(
            [
                ("rx", a, None, hp),
                ("rx", b, None, hp),
                ("cx", a, b, 0.0),
                ("rz", b, None, g),
                ("cx", a, b, 0.0),
                ("rx", a, None, -hp),
                ("rx", b, None, -hp),
            ]
        )

    for step in range(steps):
        lines.append(f"// trotter slice {step + 1}/{steps}, dt={dt:.6f}")
        for j in range(n):
            if degrees[j]:
                # exp(-i dt * d_j * (I-Z)/2): |1> picks e^{-i d_j dt}
                lam = -2.0 * degrees[j] * dt
                lines.append(f"rz({lam:.10f}) q[{j}];")
                ops.append(("rz", j, None, lam))
        for a, b in edges:
            if compact is not None:
                # 2-CX block solved once for this dt — application order:
                # (u3a1 x u3b1) -> cx -> (u3a2 x u3b2) -> cx -> (u3a3 x u3b3)
                g1a, g1b, g2a, g2b, g3a, g3b = compact
                for gs, q in ((g1a, a), (g1b, b)):
                    lines.append(f"u3({gs[0]:.10f},{gs[1]:.10f},{gs[2]:.10f}) q[{q}];")
                    ops.append(("u3", q, None, gs))
                lines.append(f"cx q[{a}],q[{b}];")
                ops.append(("cx", a, b, 0.0))
                for gs, q in ((g2a, a), (g2b, b)):
                    lines.append(f"u3({gs[0]:.10f},{gs[1]:.10f},{gs[2]:.10f}) q[{q}];")
                    ops.append(("u3", q, None, gs))
                lines.append(f"cx q[{a}],q[{b}];")
                ops.append(("cx", a, b, 0.0))
                for gs, q in ((g3a, a), (g3b, b)):
                    lines.append(f"u3({gs[0]:.10f},{gs[1]:.10f},{gs[2]:.10f}) q[{q}];")
                    ops.append(("u3", q, None, gs))
            else:
                # exp(+i dt/2 (XX+YY)) per edge (H_edge = -(XX+YY)/2)
                rxx(a, b, -dt)
                ryy(a, b, -dt)
    return "\n".join(lines) + "\n", ops


def solve_xy_block(dt: float):
    """2-CX decomposition of exp(+i dt/2 (XX+YY)) as
    (u3a1 x u3b1) . cx01 . (u3a2 x u3b2) . cx01 . (u3a3 x u3b3) — angles
    fitted numerically; all edges share one dt so one solve serves all."""
    from scipy.optimize import least_squares

    X = np.array([[0, 1], [1, 0]], complex)
    Y = np.array([[0, -1j], [1j, 0]], complex)
    CNOT = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], complex)

    def u3m(th, ph, la):
        return np.array(
            [
                [np.cos(th / 2), -np.exp(1j * la) * np.sin(th / 2)],
                [np.exp(1j * ph) * np.sin(th / 2), np.exp(1j * (ph + la)) * np.cos(th / 2)],
            ],
            complex,
        )

    T = expm(1j * dt / 2 * (np.kron(X, X) + np.kron(Y, Y)))

    def build(p):
        a1, b1, a2, b2, a3, b3 = [u3m(*p[k : k + 3]) for k in range(0, 18, 3)]
        return np.kron(a3, b3) @ CNOT @ np.kron(a2, b2) @ CNOT @ np.kron(a1, b1)

    def resid(p):
        u = build(p)
        k = np.argmax(np.abs(T))
        d = u - T * (u.flat[k] / T.flat[k])
        return np.abs(d).ravel()

    best = None
    rng = np.random.RandomState(7)
    for _ in range(6):
        r = least_squares(resid, rng.randn(18), max_nfev=40000)
        if best is None or np.abs(r.fun).max() < best[0]:
            best = (np.abs(r.fun).max(), r.x)
        if best[0] < 1e-6:
            break
    if best[0] > 1e-5:
        raise RuntimeError(f"xy-block solve failed, residual {best[0]:.2e}")
    p = best[1]
    # return gate order: first-applied a1,b1 then middle a2,b2 then final a3,b3
    return tuple(p[k : k + 3].tolist() for k in range(0, 18, 3))


# ── verification: tiny statevector interpreter for the emitted gates ──


def simulate(n: int, ops) -> np.ndarray:
    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0

    def apply1(q, m):
        step = 1 << q
        i0 = np.arange(1 << n)
        idx0 = i0[(i0 & step) == 0]
        idx1 = idx0 | step
        a = psi[idx0].copy()
        b = psi[idx1].copy()
        psi[idx0] = m[0, 0] * a + m[0, 1] * b
        psi[idx1] = m[1, 0] * a + m[1, 1] * b

    for op in ops:
        name, qa, qb, g = op
        if name == "x":
            apply1(qa, np.array([[0, 1], [1, 0]], complex))
        elif name == "h":
            apply1(qa, np.array([[1, 1], [1, -1]], complex) / np.sqrt(2))
        elif name == "rz":
            apply1(qa, np.diag([np.exp(-1j * g / 2), np.exp(1j * g / 2)]))
        elif name == "rx":
            c, s = np.cos(g / 2), np.sin(g / 2)
            apply1(qa, np.array([[c, -1j * s], [-1j * s, c]], complex))
        elif name == "u3":
            th, ph, la = g
            apply1(
                qa,
                np.array(
                    [
                        [np.cos(th / 2), -np.exp(1j * la) * np.sin(th / 2)],
                        [np.exp(1j * ph) * np.sin(th / 2), np.exp(1j * (ph + la)) * np.cos(th / 2)],
                    ],
                    complex,
                ),
            )
        elif name == "cx":
            step_a, step_b = 1 << qa, 1 << qb
            i0 = np.arange(1 << n)
            src = i0[((i0 & step_a) != 0) & ((i0 & step_b) == 0)]
            dst = src | step_b
            tmp = psi[src].copy()
            psi[src] = psi[dst]
            psi[dst] = tmp
    return psi


def verify(n, edges, source, t, steps, ops):
    a = adjacency(n, edges)
    h = np.diag(a.sum(axis=1)) - a
    # exact: single-excitation sector -> psi node amplitudes
    w, v = np.linalg.eigh(h)
    u = (v * np.exp(-1j * w * t)) @ v.T
    p_exact = np.abs(u[:, source]) ** 2
    psi = simulate(n, ops)
    probs = np.abs(psi) ** 2
    p_circ = np.zeros(n)
    for j in range(n):
        p_circ[j] = probs[np.arange(1 << n) & (1 << j) != 0].sum()
    l1 = np.abs(p_exact - p_circ).sum()
    r = np.corrcoef(p_exact, p_circ)[0, 1]
    return l1, r, p_exact, p_circ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="kras")
    ap.add_argument("--t", type=float, default=None)
    ap.add_argument("--steps", type=int, default=1)
    ap.add_argument("--source", type=int, default=0)
    ap.add_argument("--emit", type=str, default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument(
        "--compact",
        action="store_true",
        help="2-CX XY block per edge (numerically solved) instead of rxx+ryy (4 CX)",
    )
    args = ap.parse_args()

    n, edges, sources, node_map = load_core(args.target)
    a = adjacency(n, edges)
    degrees = a.sum(axis=1)
    h = np.diag(degrees) - a
    t = args.t
    if t is None:
        t, r = choose_t(h, args.source)
        print(f"chosen t={t:.2f} (single-time vs time-averaged Pearson {r:.3f})")
    compact = solve_xy_block(t / args.steps) if args.compact else None
    qasm, ops = emit_qasm(n, edges, degrees, args.source, t, args.steps, compact=compact)
    ncx = sum(1 for o in ops if o[0] == "cx")
    print(
        f"qubits={n} edges={len(edges)} t={t} steps={args.steps} "
        f"cx_gates={ncx} total_ops={len(ops)}"
    )
    if args.emit:
        Path(args.emit).write_text(qasm)
        print(f"wrote {args.emit} ({len(qasm)} bytes)")
    if args.verify:
        l1, r, pe, pc = verify(n, edges, args.source, t, args.steps, ops)
        print(f"verify: L1(p_exact, p_circuit)={l1:.4f}  Pearson={r:.4f}")
        print(
            f"  top exact: {np.argsort(-pe)[:5].tolist()}  top circ: {np.argsort(-pc)[:5].tolist()}"
        )


if __name__ == "__main__":
    main()
