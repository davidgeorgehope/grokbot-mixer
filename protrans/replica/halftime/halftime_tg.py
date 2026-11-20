#!/usr/bin/env python3
"""2026-11-20 midnight research (flag HALFTIME_TG, off by default): phase-free half-time detector.

Gap it fills: slowdown.py flags a section when strong snare hits fall under 0.35 x the drop mean. A real half-time
section (snare moves from beats 2+4 to beat 3) keeps ~1 strong snare per bar (~0.7 x a DnB drop), so it is NOT caught;
only near snare-less stretches are. Here, per bar, we take the snare-band (180-2500 Hz) and kick-band (30-150 Hz) onset
strength on the stretched grid at 16th resolution, over a 4-bar context, and compare its periodicity at one bar (16
slots) with its periodicity at half a bar (8 slots):
    ht = ac(16) - ac(8)     (normalised autocorrelation of the mean-removed onset curve)
Full-time DnB (backbeat every half bar) has ac(8) ~ ac(16) -> ht ~ 0; half-time (one backbeat per bar) has ac(8) low
and ac(16) high -> ht large. Phase-free: does not depend on where the grid puts beat 1 (cf. tempogram / metrical-level
work: Grosche & Mueller PLP / cyclic tempogram; Hockman, Davies & Fujinaga 2012 on DnB drum patterns).
A half-time section = >= 8 consecutive bars (gaps of up to 2 bridged) where the snare ht exceeds the track's drop median
by HT_D (0.35) and the snare band is still active (not a drums-out bar, which slowdown.py already handles) and the
track is not fading (level within 30 dB of its body). Cached in src2/st/<yt>.halftime_tg.json."""
import os, sys, json, numpy as np, soundfile as sf, scipy.signal as ss
SRC2 = '/workspace/mixes/src2'
REF = 'ht16-8 v1'
HT_D = float(os.environ.get('HALFTIME_TG_D', 0.35))

def _flux(x, sr, lo, hi, hop=256):
    sos = ss.butter(4, [lo / (sr / 2), min(hi / (sr / 2), 0.99)], 'band', output='sos'); y = ss.sosfiltfilt(sos, x)
    n = len(y) // hop; le = np.log(np.sqrt(np.mean(y[:n * hop].reshape(n, hop) ** 2, 1) + 1e-12)); return np.maximum(np.diff(le, prepend=le[0]), 0)

def _ac(c, L):
    z = c - c.mean(); d = float((z * z).sum())
    return float((z[:-L] * z[L:]).sum() / d) if d > 1e-9 else 0.0

def raw(yt):
    cp = os.path.join(SRC2, 'st', yt + '.halftime_tg.json')
    if os.path.exists(cp):
        P = json.load(open(cp))
        if P.get('ref') == REF: return P
    g = json.load(open(os.path.join(SRC2, 'st', yt + '.json'))); bar = 4 * g['per']; w = os.path.join(SRC2, 'st', yt + '.wav')
    if not os.path.exists(w): return None
    y, sr = sf.read(w, dtype='float32'); y = y.mean(1) if y.ndim > 1 else y; fr = sr / 256
    nb = int(len(y) / sr / bar); P = dict(ref=REF)
    for nm, lo, hi in (('snare', 180, 2500), ('kick', 30, 150)):
        f = _flux(y, sr, lo, hi)
        S = np.array([[c.max() if len(c) else 0 for c in np.array_split(f[int(k * bar * fr):int((k + 1) * bar * fr)], 16)] for k in range(nb)])
        ht, act = [], []
        for k in range(nb):
            c = S[max(0, k - 1):min(nb, k + 3)].ravel()
            ht.append(round(_ac(c, 16) - _ac(c, 8), 3) if len(c) >= 48 else 0.0)
            act.append(round(float(np.sort(S[k])[-2:].mean()), 3))
        P[nm + '_ht'] = ht; P[nm + '_act'] = act
    json.dump(P, open(cp, 'w')); return P

def find(P, sec, level, d=HT_D):
    ht = np.array(P['snare_ht'], float); act = np.array(P['snare_act'], float); n = len(ht)
    lv = np.array(level, float)[:n]; lv = np.pad(lv, (0, n - len(lv)), constant_values=-120)
    dm = np.zeros(n, bool)
    for a, b in ((sec or {}).get('drops') or []): dm[max(0, a):min(n, b)] = True
    if dm.sum() < 8: dm[:] = True
    base = float(np.median(ht[dm])); aref = float(np.median(act[dm])); body = np.percentile(lv, 75)
    on = (ht > base + d) & (act > 0.5 * aref) & (lv > body - 30)
    on2 = on.copy()
    for k in range(1, n - 1):
        if not on[k] and on[max(0, k - 2):k].any() and on[k + 1:k + 3].any(): on2[k] = True
    out, k = [], 0
    while k < n:
        if on2[k]:
            j = k
            while j < n and on2[j]: j += 1
            if j - k >= 8: out.append([k, j])
            k = j
        else: k += 1
    return out, base

def sections(yt, d=HT_D):
    P = raw(yt)
    if not P: return []
    sp = os.path.join(SRC2, 'st', yt + '.sections.json'); sec = json.load(open(sp)) if os.path.exists(sp) else None
    lv = json.load(open(os.path.join(SRC2, 'st', yt + '.json')))['bar']['all']
    return find(P, sec, lv, d)[0]

if __name__ == '__main__':
    for yt in sys.argv[1:]:
        P = raw(yt); s = sections(yt); print(yt, 'halftime sections', s)
