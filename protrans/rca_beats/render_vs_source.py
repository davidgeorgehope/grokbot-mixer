"""Sample-level check that the engine puts source bar k of each deck exactly on its mix bar (lag of rendered deck vs st wav at downs[k])."""
import json, sys, os
import numpy as np, soundfile as sf
sys.path.insert(0, '/workspace/mixes/src2')
def run(meta, i=0, maxlag_ms=60):
    os.chdir('/workspace/mixes/src2')
    import blend_diag as D, engine as E
    M = json.load(open(meta)); s0, A, B = D.crop_decks(M, i); out = {}
    for nm, y, d in (('A', A, M['decks'][i]), ('B', B, M['decks'][i + 1])):
        g = json.load(open(f"st/{d['id']}.json")); st, sr = sf.read(f"st/{d['id']}.wav", dtype='float32')
        L = int(maxlag_ms / 1000 * sr); rows = []
        for k in range(int(round(len(y) / E.BS))):
            j = int(s0 + k - d['start_bar'])
            if not (0 <= j < len(d['full_map'])): continue
            src = d['full_map'][j][0]; a0 = int(round(k * E.BS)); seg = y[a0:a0 + int(E.BS), 0]
            if np.sqrt(np.mean(seg ** 2)) < 1e-3: continue
            s = int(round(g['downs'][src] * sr)); ref = st[max(0, s - L):s + int(E.BS) + L, 0]
            if len(ref) < int(E.BS) + 2 * L: continue
            seg = seg[L:-L] if len(seg) > 2 * L else seg
            xc = np.correlate(ref, seg, 'valid'); lag = (int(np.argmax(np.abs(xc))) - 2 * L) / sr * 1000  # 0 = source bar lands exactly on its mix bar
            rows.append((s0 + k, src, round(lag, 2)))
        out[nm] = rows
    return out
if __name__ == '__main__':
    o = run(sys.argv[1])
    for nm, rows in o.items():
        lags = [r[2] for r in rows]; print(nm, 'bars', len(rows), 'lag ms min/max', min(lags), max(lags)); print(' ', rows[:6], '...', rows[-4:])
