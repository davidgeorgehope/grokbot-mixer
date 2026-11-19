#!/usr/bin/env python3
"""2026-11-19: half-time / slowdown section detector (research, flag HALFTIME). Per bar of a track's stretched grid wav (src2/st/<yt>.wav,
uniform bars at the mix tempo) it measures onset flux in three bands (kick 30-150 Hz, snare 180-2500 Hz, hats 6-14 kHz) at 16th-note
resolution, then:
  backbeat = mean snare onset strength on beats 3 and 4 of the bar's grid (the slots where this corpus's drum grid puts the backbeat),
  hats     = number of 16th slots with a hat onset.
A slowdown section = >= 8 consecutive bars (gaps of up to 2 bars bridged) where the 2-bar mean count of strong snare hits
(onsets >= 60% of the track's p99 snare onset) is < 0.35 x its mean over the drops (drum-and-bass drops: ~1.3-1.5 per bar), while the
track is not near-silent (not a fade-out: per-bar level within 30 dB of its body). Cached in st/<yt>.slowdown.json."""
import os, sys, json, numpy as np, soundfile as sf, scipy.signal as ss
SRC2 = '/workspace/mixes/src2'
def _flux(x, sr, lo, hi, hop=256):
    sos = ss.butter(4, [lo / (sr / 2), min(hi / (sr / 2), 0.99)], 'band', output='sos'); y = ss.sosfiltfilt(sos, x)
    n = len(y) // hop; le = np.log(np.sqrt(np.mean(y[:n * hop].reshape(n, hop) ** 2, 1) + 1e-12)); return np.maximum(np.diff(le, prepend=le[0]), 0)
def profile(yt):
    cp = os.path.join(SRC2, 'st', yt + '.slowdown.json')
    if os.path.exists(cp):
        P = json.load(open(cp))
        if P.get('ref') == 'snare_strong2 < 0.35 x drop mean v3': return P
        sec = json.load(open(os.path.join(SRC2, 'st', yt + '.sections.json'))) if os.path.exists(os.path.join(SRC2, 'st', yt + '.sections.json')) else None
        P['sections'] = find(P, sec, json.load(open(os.path.join(SRC2, 'st', yt + '.json')))['bar']['all']); P['ref'] = 'snare_strong2 < 0.35 x drop mean v3'; json.dump(P, open(cp, 'w')); return P
    g = json.load(open(os.path.join(SRC2, 'st', yt + '.json'))); bar = 4 * g['per']; w = os.path.join(SRC2, 'st', yt + '.wav')
    if not os.path.exists(w): return None
    y, sr = sf.read(w, dtype='float32'); y = y.mean(1) if y.ndim > 1 else y; fr = sr / 256
    F = {nm: _flux(y, sr, lo, hi) for nm, lo, hi in (('kick', 30, 150), ('snare', 180, 2500), ('hat', 6000, 14000))}
    nb = int(len(y) / sr / bar); thr = {k: max(0.25, float(np.percentile(v, 90))) for k, v in F.items()}; P = dict(backbeat=[], hats=[], kicks=[], snare_strong=[])
    S16 = {nm: np.array([[c.max() if len(c) else 0 for c in np.array_split(f[int(k * bar * fr):int((k + 1) * bar * fr)], 16)] for k in range(nb)]) for nm, f in F.items()}
    sthr = 0.6 * float(np.percentile(S16['snare'], 99))  # a "strong" snare hit: >= 60% of the track's loudest snare onsets
    for k in range(nb):
        P['backbeat'].append(round(float((S16['snare'][k][8] + S16['snare'][k][12]) / 2), 3)); P['hats'].append(int((S16['hat'][k] > thr['hat']).sum()))
        P['kicks'].append(int((S16['kick'][k] > thr['kick']).sum())); P['snare_strong'].append(int((S16['snare'][k] > sthr).sum()))
    sec = json.load(open(os.path.join(SRC2, 'st', yt + '.sections.json'))) if os.path.exists(os.path.join(SRC2, 'st', yt + '.sections.json')) else None
    P['sections'] = find(P, sec, g['bar']['all']); P['ref'] = 'snare_strong2 < 0.35 x drop mean v3'; json.dump(P, open(cp, 'w')); return P
def find(P, sec, level):
    bb, ht, lv = np.array(P['backbeat'], float), np.array(P['hats'], float), np.array(level, float)[:len(P['backbeat'])]
    drops = (sec or {}).get('drops') or []
    dm = np.zeros(len(bb), bool)
    for a, b in drops: dm[max(0, a):min(len(bb), b)] = True
    if dm.sum() < 8: dm[:] = True
    sn = np.array(P['snare_strong'], float); sn2 = np.convolve(sn, np.ones(2) / 2, 'same')  # strong snare hits per bar, 2-bar mean
    body = np.percentile(lv, 75); ref = max(np.mean(sn[dm]), 0.5)
    on = (sn2 < 0.35 * ref) & (lv > body - 30)
    on2 = on.copy()
    for k in range(1, len(on) - 1):
        if not on[k] and on[max(0, k - 2):k].any() and on[k + 1:k + 3].any(): on2[k] = True  # bridge gaps of up to 2 bars
    out, k = [], 0
    while k < len(on2):
        if on2[k]:
            j = k
            while j < len(on2) and on2[j]: j += 1
            if j - k >= 8: out.append([k, j])
            k = j
        else: k += 1
    return out
def overlap_frac(secs, a, b):
    if b <= a: return 0.0
    return sum(max(0, min(b, y) - max(a, x)) for x, y in secs) / (b - a)
if __name__ == '__main__':
    for yt in sys.argv[1:]: P = profile(yt); print(yt, 'slowdown sections', P and P['sections'])
