"""Grid-free clip metric: fit one global 174-BPM beat phase to a clip (max snare-band beat-phase concentration), then per-bar r.
Two decks out of phase (or clashing grooves) smear the hits -> r drops in the overlap. Prints ours vs pro for each daily."""
import json, sys, glob, os, numpy as np, librosa
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import gridcheck as G
BEAT = 60 / 174; BAR = 4 * BEAT
def per_bar(path):
    y, sr = librosa.load(path, sr=22050); o, dt = G.onset_env(y, sr, 150, 2000); t = np.arange(len(o)) * dt
    z = np.sum(o * np.exp(-2j * np.pi * t / BEAT)); ph = (-np.angle(z) / (2 * np.pi)) * BEAT  # global phase (s)
    rows = []; k = 0
    while ph + (k + 1) * BAR <= t[-1]:
        p, r = G.bar_phase(o, dt, ph + k * BAR, BEAT); rows.append((round(ph + k * BAR, 2), None if np.isnan(p) else round(p, 1), round(r, 2))); k += 1
    return round(float(abs(z) / o.sum()), 3), rows
if __name__ == '__main__':
    out = {}
    for kf in sorted(glob.glob('/workspace/private/daily_2026-11-*_key.json')):
        d = json.load(open(kf)); day = d.get('date') or os.path.basename(kf)[6:16]
        bs = d.get('blend_start_s'); res = {}
        for who in ('pro', 'ours'):
            p = f"/workspace/mixes/deliver/protrans/daily_{day}_{d[who]}.mp3"
            if not os.path.exists(p): continue
            R, rows = per_bar(p)
            ov = [r for (t0, _, r) in rows if bs is not None and bs <= t0 < bs + 16 * BAR]
            pre = [r for (t0, _, r) in rows if bs is not None and t0 < bs]
            res[who] = dict(global_r=R, overlap_r=None if not ov else round(float(np.median(ov)), 2), pre_r=None if not pre else round(float(np.median(pre)), 2),
                            overlap_phase_sd=round(float(np.nanstd([p for (t0, p, r) in rows if bs is not None and bs <= t0 < bs + 16 * BAR and p is not None])), 1) if bs is not None else None)
        out[day] = dict(pick=d.get('pick_id'), blend_start_s=bs, **res); print(day, d.get('pick_id'), json.dumps(res), flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clipflam.json'), 'w'), indent=1)
