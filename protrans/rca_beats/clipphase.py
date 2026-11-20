"""Per-bar snare-band phase and 'flam' (energy in the beat-fold more than 25 ms away from the main peak) of a delivered clip,
on the engine grid implied by its offset (clip t=0 -> mix bar b0 + off_s/BAR)."""
import sys, json, numpy as np, librosa
sys.path.insert(0, '.'); import gridcheck as G
BEAT = 60 / 174; BAR = 4 * BEAT
def run(path, grid0_s, b0):
    y, sr = librosa.load(path, sr=22050); o, dt = G.onset_env(y, sr, 150, 2000); rows = []
    k = 0
    while grid0_s + (k + 1) * BAR <= len(y) / sr:
        t0 = grid0_s + k * BAR
        if t0 >= 0:
            ph, r = G.bar_phase(o, dt, t0, BEAT); rows.append((b0 + k, round(ph, 1), round(r, 2)))
        k += 1
    return rows
if __name__ == '__main__':
    path, grid0, b0 = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    for r in run(path, grid0, b0): print(r)
