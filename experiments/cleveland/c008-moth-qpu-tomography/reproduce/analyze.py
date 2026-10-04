"""Hardware-vs-emulator tomography comparison for one c008 target.

Usage: python analyze.py <core.json> <emu_result.json> <qpu_result.json>
"""

import json
import sys

import numpy as np

emu = json.load(open(sys.argv[2]))["result"]["output"]
qpu = json.load(open(sys.argv[3]))["result"]["output"]
core = json.load(open(sys.argv[1]))

# --- per-edge correlation comparison (the 9 two-qubit Paulis) ---
rels_e = emu["tomography"]["relationships"]
rels_q = qpu["tomography"]["relationships"]
paulis = ["XX", "XY", "XZ", "YX", "YY", "YZ", "ZX", "ZY", "ZZ"]

rows = []
for edge, vals in rels_e.items():
    qv = rels_q.get(edge, {})
    ev = [vals.get(p, 0) for p in paulis]
    hv = [qv.get(p, 0) for p in paulis]
    rows.append((edge, np.array(ev), np.array(hv)))

ideal_mag = np.array([np.linalg.norm(r[1]) for r in rows])
hw_mag = np.array([np.linalg.norm(r[2]) for r in rows])
cos = np.array(
    [np.dot(r[1], r[2]) / (np.linalg.norm(r[1]) * np.linalg.norm(r[2]) + 1e-12) for r in rows]
)

print(f"edges: {len(rows)}")
print(f"ideal |corr| : mean {ideal_mag.mean():.3f}  max {ideal_mag.max():.3f}")
print(f"hardware |corr|: mean {hw_mag.mean():.3f}  max {hw_mag.max():.3f}")
print(
    f"correlation-vector cosine (hw vs ideal): mean {cos.mean():.3f}  median {np.median(cos):.3f}"
)
print(
    f"edge_agreement emu {emu.get('edge_agreement_score')} vs qpu {qpu.get('edge_agreement_score')}"
)

# --- strongest-surviving edges on hardware ---
idx = np.argsort(-hw_mag)
print("\ntop hardware correlations (edge, |corr| hw vs ideal):")
for i in idx[:8]:
    print(f"  {rows[i][0]:8}  {hw_mag[i]:.3f} vs {ideal_mag[i]:.3f}")

# --- decoherence by node role ---
node_mag = {}
for edge, ev, hv in rows:
    a, b = map(int, edge.split(","))
    for n in (a, b):
        node_mag.setdefault(n, []).append(np.linalg.norm(hv))
roles = core["node_map"]
agg = {}
for n, ms in node_mag.items():
    role = roles[str(n)]["role"] or "connector"
    agg.setdefault(role, []).extend(ms)
print("\nhw |corr| by node role:")
for role, ms in agg.items():
    print(f"  {role:12} mean {np.mean(ms):.3f}  n={len(ms)}")

# bloch magnitudes: decoherence per qubit
be = emu["tomography"]["bloch"]
bq = qpu["tomography"]["bloch"]
bm_e = np.array([np.linalg.norm([v["X"], v["Y"], v["Z"]]) for v in be.values()])
bm_q = np.array([np.linalg.norm([v["X"], v["Y"], v["Z"]]) for v in bq.values()])
print(f"\nbloch |r|: ideal mean {bm_e.mean():.3f}  hw mean {bm_q.mean():.3f}  (purity decay)")
print(
    f"ibm_job_id: {qpu.get('ibm_job_id')}  backend: {qpu.get('backend')}  shots: {qpu.get('shots')}"
)
