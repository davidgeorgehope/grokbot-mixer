#!/usr/bin/env python3
"""2026-11-19 nightly: MIX-ONLY beat-clash statistic ("flam"), so the pro reference needs no source placement at all.
Diagnosis carried over from 11-18: deck-to-deck lag on pro clips (sources placed once on the pro clip) is noise-dominated
(median 60-75 ms), so pro p95 sat near a 110 ms fault. Here each statistic is computed on the summed mix only:
per bar, autocorrelation of the flattened onset envelope at 35-140 ms lags, minus the same curve's median over the clip's
own non-overlap (one-deck) bars; a clash adds a cross-term peak at the deck offset that one-deck bars do not have.
Stat = median (or 75th pct) over overlap bars of the max excess. Threshold = pro p95 (33 pro clips, LOO FA). Injected set =
same as calib_v2 (default renders: clean / incoming +60 ms / +110 ms), split md5(pair) % 3; design picked on DEV only.
Writes hc2_cache/flam_{pro,cases}.pkl and clash_flam_1119.json."""
import json, os, sys, pickle, hashlib, numpy as np
from scipy.signal import resample_poly
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
SR = 22050; HOP = 64; NFFT = 512; BAR = 240.0 / 174.0
def split_of(pid): return 'heldout' if int(hashlib.md5(pid.encode()).hexdigest(), 16) % 3 == 0 else 'dev'
def env(y):
    fr = np.lib.stride_tricks.sliding_window_view(y, NFFT)[::HOP] * np.hanning(NFFT)
    S = np.abs(np.fft.rfft(fr, axis=1)); f = np.fft.rfftfreq(NFFT, 1/SR); L = np.log1p(100*S); d = np.maximum(0, np.diff(L, axis=0))
    k = d[:, (f >= 30) & (f < 150)].sum(1); s = d[:, (f >= 150) & (f < 8000)].sum(1)
    e = k / (k.mean() + 1e-9) + s / (s.mean() + 1e-9)
    w = int(BAR / 4 * SR / HOP); e = np.maximum(0, e - np.convolve(e, np.ones(w)/w, 'same')); return e
LAGS_MS = np.arange(0, 150, HOP / SR * 1000)
def bar_ac(e, nbars):
    fpb = BAR * SR / HOP; L = len(LAGS_MS); out = np.full((nbars, L), np.nan)
    for k in range(nbars):
        i0, i1 = int(k*fpb), int((k+1)*fpb)
        if i1 + L > len(e): break
        a = e[i0:i1] - e[i0:i1].mean(); n0 = a @ a
        if n0 <= 0: continue
        out[k] = [a @ (e[i0+l:i1+l] - e[i0+l:i1+l].mean()) / n0 for l in range(L)]
    return out
def feats(y, s, e):
    n = int(len(y) / SR / BAR); ac = bar_ac(env(y), n); return dict(ac=ac, s=s, e=min(e, n), n=n)
def stat(f, lo_ms=35, hi_ms=140, form='median'):
    ac = f['ac']; m = np.isfinite(ac[:, 0]); ov = np.zeros(len(ac), bool); ov[f['s']:f['e']] = True
    ref = ac[m & ~ov]
    if len(ref) < 2 or (m & ov).sum() < 2: return 0.0
    base = np.median(ref, 0); band = (LAGS_MS >= lo_ms) & (LAGS_MS <= hi_ms)
    x = np.max((ac[m & ov] - base)[:, band], 1)
    return float(np.median(x) if form == 'median' else np.percentile(x, 75))
def pro_all():
    p = os.path.join(H, 'hc2_cache', 'flam_pro.pkl')
    if os.path.exists(p): return pickle.load(open(p, 'rb'))
    import run_admitted_tune as T, score
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); out = {}
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        if d.get('in_entry_clip_bar') is None or d.get('out_gone_clip_bar') is None: continue
        y = score._load(rec['pro_clip'], sr=SR); out[rec['id']] = feats(y, int(d['in_entry_clip_bar']), int(d['out_gone_clip_bar']))
        print('pro', rec['id'], flush=True)
    pickle.dump(out, open(p, 'wb')); return out
def cases_all():
    p = os.path.join(H, 'hc2_cache', 'flam_cases.pkl'); cases = pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
    os.chdir(SRC2); import blend_diag as BD
    from engine import BS
    for l in open(os.path.join(H, 'gate_ckpt', 'default.jsonl')):
        r = json.loads(l); pid = r['id']
        if r.get('error') or f'{pid}|clean' in cases: continue
        M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
        s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
        for kind, ms in (('clean', 0), ('clash60', 60), ('clash110', 110)):
            k = int(ms/1000*44100); BB = B if not k else np.concatenate([np.zeros((k, 2), np.float32), B[:-k]])
            y = resample_poly((A + BB).mean(1), 1, 2); f = feats(y, s, e); f.update(kind=kind, split=split_of(pid)); cases[f'{pid}|{kind}'] = f
        pickle.dump(cases, open(p, 'wb')); print('case', pid, flush=True)
    return cases
if __name__ == '__main__':
    pros = pro_all(); cases = cases_all(); rows = []
    def p95(v): return float(np.percentile(v, 95))
    for lo, hi in ((35, 140), (45, 130), (50, 125), (35, 100), (90, 140)):
        for form in ('median', 'p75'):
            ps = [stat(f, lo, hi, form) for f in pros.values()]; th = p95(ps)
            fa = float(np.mean([ps[j] > p95([x for i, x in enumerate(ps) if i != j]) for j in range(len(ps))]))
            r = dict(lo=lo, hi=hi, form=form, thr=round(th, 4), pro_fa_loo=round(fa, 3))
            for sp in ('dev', 'heldout'):
                for kind in ('clean', 'clash60', 'clash110'):
                    v = [stat(f, lo, hi, form) > th for f in cases.values() if f['split'] == sp and f['kind'] == kind]; r[f'{sp}_{kind}'] = round(float(np.mean(v)), 3)
            rows.append(r)
    ok = [r for r in rows if r['dev_clean'] <= 0.05] or rows
    best = max(ok, key=lambda r: (r['dev_clash60'] + r['dev_clash110']) / 2 - r['dev_clean'])
    json.dump(dict(rows=rows, chosen_on_dev=best, rule=__doc__), open(os.path.join(H, 'clash_flam_1119.json'), 'w'), indent=1)
    for r in rows: print(r)
    print('CHOSEN', best)
