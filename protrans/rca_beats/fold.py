"""16th-note onset fold (snare band 150-2k, kick <150) of a track's source bars, phase relative to the grid."""
import json, sys, numpy as np, librosa
sys.path.insert(0, '.'); import gridcheck as G
def fold(yid, b0, b1, lo, hi, nb=64):
    g = json.load(open(f'/workspace/mixes/src2/st/{yid}.json')); per = g['per']
    y, sr = librosa.load(f'/workspace/mixes/src2/st/{yid}.wav', sr=22050); o, dt = G.onset_env(y, sr, lo, hi)
    H = np.zeros(nb)
    for k in range(b0, b1):
        t0 = g['downs'][k]; i0 = int(t0 / dt); n = int(4 * per / dt); w = o[i0:i0 + n]
        ph = (np.arange(len(w)) * dt) / (4 * per) * nb
        np.add.at(H, np.clip(ph.astype(int), 0, nb - 1), w)
    return H / (H.max() + 1e-9)
def show(lbl, H):
    s = ''.join(' .:-=+*#%@'[min(9, int(v * 9.99))] for v in H); print(f'{lbl:28s}|{s}|')
if __name__ == '__main__':
    print(' ' * 29 + ''.join(('1' if i == 0 else str(i // 16 + 1)) if i % 16 == 0 else ('|' if i % 4 == 0 else ' ') for i in range(64)))
    for yid, b0, b1, lbl in [('J3oTRY7AdE4', 192, 208, 'Listen A 192-207 (drop2)'), ('ksVDZt9_0J4', 48, 64, 'Optimist B 48-63 (intro)'), ('ksVDZt9_0J4', 64, 80, 'Optimist B 64-79 (drop1)')]:
        show(lbl + ' snare', fold(yid, b0, b1, 150, 2000)); show(lbl + ' kick', fold(yid, b0, b1, 20, 150))
