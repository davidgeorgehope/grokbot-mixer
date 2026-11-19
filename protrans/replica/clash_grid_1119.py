#!/usr/bin/env python3
"""2026-11-19 nightly, second mix-only beat-clash statistic ("off-grid onset share"). The 'flam' autocorrelation statistic
(clash_flam_1119.py) did not separate injected clashes from clean blends at all, so it is not used.
Here: per bar, fit a 16th-note grid to the MIX's own onset envelope (period searched +-3% around 1/16 bar, any phase) and take the
share of onset energy within +-TOL ms of a grid line. A deck offset that is not a multiple of a 16th (60 or 110 ms at 174 BPM)
puts the second deck's onsets off that grid. Clip statistic = median on-grid share over one-deck bars minus median over overlap
bars (drop during the blend). Needs no source placement, so the pro reference is not limited by placement noise.
Threshold = pro p95 over the 33 pro clips (LOO FA); design (TOL, form) picked on DEV injected cases only; md5 % 3 held-out.
Caches hc2_cache/grid_{pro,cases}.pkl (onset envelopes), writes clash_grid_1119.json."""
import json, os, sys, pickle, numpy as np
from scipy.signal import resample_poly
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import clash_flam_1119 as F
SR, HOP, BAR = F.SR, F.HOP, F.BAR
FPS = SR / HOP
def bar_share(seg, tol_ms):
    t = np.arange(len(seg)) / FPS * 1000.0; w = seg.sum()
    if w <= 0: return np.nan
    best = 0.0; base = BAR * 1000 / 16
    for per in base * np.linspace(0.97, 1.03, 13):
        for ph in np.arange(0, per, 3.0):
            d = np.abs(((t - ph + per / 2) % per) - per / 2); s = seg[d <= tol_ms].sum() / w
            if s > best: best = s
    return best
def clip_stat(e, s, ee, tol, form):
    n = int(len(e) / (BAR * FPS)); fpb = BAR * FPS
    sh = np.array([bar_share(e[int(k*fpb):int((k+1)*fpb)], tol) for k in range(n)])
    ov = np.zeros(n, bool); ov[s:min(ee, n)] = True; m = np.isfinite(sh)
    if (m & ~ov).sum() < 2 or (m & ov).sum() < 2: return 0.0
    a = sh[m & ~ov]; b = sh[m & ov]
    return float(np.median(a) - (np.median(b) if form == 'median' else np.percentile(b, 25)))
def envs():
    p = os.path.join(H, 'hc2_cache', 'grid_env.pkl')
    if os.path.exists(p): return pickle.load(open(p, 'rb'))
    import run_admitted_tune as T, score
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); pro = {}
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        if d.get('in_entry_clip_bar') is None or d.get('out_gone_clip_bar') is None: continue
        pro[rec['id']] = dict(e=F.env(score._load(rec['pro_clip'], sr=SR)), s=int(d['in_entry_clip_bar']), ee=int(d['out_gone_clip_bar']))
    os.chdir(F.SRC2); import blend_diag as BD; cases = {}
    for l in open(os.path.join(H, 'gate_ckpt', 'default.jsonl')):
        r = json.loads(l); pid = r['id']
        if r.get('error'): continue
        M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
        s, ee = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
        for kind, ms in (('clean', 0), ('clash60', 60), ('clash110', 110)):
            k = int(ms/1000*44100); BB = B if not k else np.concatenate([np.zeros((k, 2), np.float32), B[:-k]])
            cases[f'{pid}|{kind}'] = dict(e=F.env(resample_poly((A + BB).mean(1), 1, 2)), s=s, ee=ee, kind=kind, split=F.split_of(pid))
        print('case', pid, flush=True)
    out = dict(pro=pro, cases=cases); pickle.dump(out, open(p, 'wb')); return out
if __name__ == '__main__':
    E = envs(); rows = []
    def p95(v): return float(np.percentile(v, 95))
    for tol in (12, 18, 25):
        for form in ('median', 'p25'):
            ps = [clip_stat(f['e'], f['s'], f['ee'], tol, form) for f in E['pro'].values()]; th = p95(ps)
            fa = float(np.mean([ps[j] > p95([x for i, x in enumerate(ps) if i != j]) for j in range(len(ps))]))
            r = dict(tol=tol, form=form, thr=round(th, 4), pro_fa_loo=round(fa, 3))
            cs = {k: clip_stat(f['e'], f['s'], f['ee'], tol, form) for k, f in E['cases'].items()}
            for sp in ('dev', 'heldout'):
                for kind in ('clean', 'clash60', 'clash110'):
                    v = [cs[k] > th for k, f in E['cases'].items() if f['split'] == sp and f['kind'] == kind]; r[f'{sp}_{kind}'] = round(float(np.mean(v)), 3)
            for kind in ('clean', 'clash60', 'clash110'): r[f'median_{kind}'] = round(float(np.median([cs[k] for k, f in E['cases'].items() if f['kind'] == kind])), 4)
            r['median_pro'] = round(float(np.median(ps)), 4); rows.append(r); print(r, flush=True)
    ok = [r for r in rows if r['dev_clean'] <= 0.05] or rows
    best = max(ok, key=lambda r: (r['dev_clash60'] + r['dev_clash110']) / 2 - r['dev_clean'])
    json.dump(dict(rows=rows, chosen_on_dev=best, rule=__doc__), open(os.path.join(H, 'clash_grid_1119.json'), 'w'), indent=1)
    print('CHOSEN', best)
