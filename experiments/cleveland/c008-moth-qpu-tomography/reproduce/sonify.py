"""Sonify measured two-qubit edge correlations.

Each graph edge plays one note; pitch is the measured |correlation| mapped
onto an A-minor-pentatonic span (A3-A6). Timing is fixed by edge order, so
the emulator and QPU tracks are the same 50 edges through two backends —
the melodies differ exactly where the measurements differ.

Usage: python sonify.py  (writes metrics/audio/*_{emu,qpu}.wav)
"""

import json
import wave
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1]
PAULIS = ["XX", "XY", "XZ", "YX", "YY", "YZ", "ZX", "ZY", "ZZ"]
SR = 22050
NOTE_S = 0.30
FADE_S = 0.012
# A minor pentatonic, A3..A6 (MIDI 57..93)
SCALE = [57, 60, 62, 64, 67, 69, 72, 74, 76, 79, 81, 84, 86, 88, 91, 93]


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def edge_mags(path: Path) -> dict:
    out = json.loads(path.read_text())["result"]["output"]["tomography"]["relationships"]
    mags = {}
    for k, v in out.items():
        mags[k] = float(sum(float(v.get(p, 0.0)) ** 2 for p in PAULIS) ** 0.5)
    return mags


def synth_track(mags: dict, edges: list, lo: float, hi: float) -> np.ndarray:
    n = int(NOTE_S * len(edges) * SR) + SR // 2
    buf = np.zeros(n)
    for idx, (i, j) in enumerate(edges):
        key = f"{min(i, j)},{max(i, j)}"
        mag = mags.get(key, 0.0)
        if hi > lo:
            deg = int(round((mag - lo) / (hi - lo) * (len(SCALE) - 1)))
        else:
            deg = 0
        f = midi_hz(SCALE[max(0, min(deg, len(SCALE) - 1))])
        t = np.arange(int(NOTE_S * SR)) / SR
        env = np.exp(-t / 0.09)
        env[: int(FADE_S * SR)] *= np.linspace(0, 1, int(FADE_S * SR))
        tone = (
            np.sin(2 * np.pi * f * t)
            + 0.35 * np.sin(2 * np.pi * f * 2 * t)
            + 0.15 * np.sin(2 * np.pi * f * 3 * t)
        ) * env
        vel = 0.25 + 0.75 * mag
        start = int(idx * NOTE_S * SR)
        buf[start : start + len(tone)] += vel * tone
    buf /= max(1.0, np.abs(buf).max() * 1.05)
    return buf


def write_wav(buf: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (buf * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def main() -> None:
    all_edges = set()
    tracks = {}
    for mode in ("emu", "qpu"):
        mags = edge_mags(EXP / "metrics" / "results" / f"kras_{mode}.json")
        tracks[mode] = mags
        all_edges.update(tuple(int(x) for x in k.split(",")) for k in mags)
    edges = sorted(all_edges)
    lo = min(min(m.values()) for m in tracks.values())
    hi = max(max(m.values()) for m in tracks.values())
    for mode in ("emu", "qpu"):
        buf = synth_track(tracks[mode], edges, lo, hi)
        out = EXP / "metrics" / "audio" / f"kras_{mode}.wav"
        write_wav(buf, out)
        print(f"wrote {out} ({len(buf) / SR:.1f}s)")


if __name__ == "__main__":
    main()
