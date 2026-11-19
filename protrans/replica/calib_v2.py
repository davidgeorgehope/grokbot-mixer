#!/usr/bin/env python3
"""Calibrate + validate hardcheck_v2 on (a) pro p95 (33 protrans pro clips) and (b) an injected-fault set built from the
103 default renders: per pair clean, clash (incoming delayed 60 ms and 110 ms), hole (both decks' lows cut 50 dB for 4 and
for 8 bars, placed mid-blend), pump (1 bar -10 dB). Split by md5(pair) like the judge pilot (1/3 held out).
Design grid chosen on DEV injected cases only; thresholds always = pro p95 (leave-one-pro-out for the FA estimate).
Writes replica/hardcheck_v2_calib.json and caches per-case features in replica/hc2_cache/."""
import json, os, sys, hashlib, pickle, itertools, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
import hardcheck_v2 as V
C = os.path.join(H, 'hc2_cache'); os.makedirs(C, exist_ok=True)
T0S = (6, 12, 18, 24, 30); FORMS = ('area', 'run'); DS = (20, 30, 45, 60); CMINS = (0.1, 0.2, 0.3, 0.4)

def split_of(pid): return 'heldout' if int(hashlib.md5(pid.encode()).hexdigest(), 16) % 3 == 0 else 'dev'

def lows_cut(y, db=50.0, fc=150.0):
    Y = np.fft.rfft(y, axis=0); f = np.fft.rfftfreq(len(y), 1/V.SR); g = np.ones_like(f); g[f < fc] = 10**(-db/20)
    return np.fft.irfft(Y * g[:, None], n=len(y), axis=0).astype(np.float32)

def pro_feats():
    p = os.path.join(C, 'pro_b.pkl')
    if os.path.exists(p): return pickle.load(open(p, 'rb'))
    import run_admitted_tune as T, score, paths, diagnose_gap as D
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); out = {}
    bar = score.BAR_SEC; bs = bar * V.SR
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        if d.get('in_entry_clip_bar') is None or d.get('out_gone_clip_bar') is None: continue
        pro = score._load(rec['pro_clip']); y = np.stack([pro, pro], 1)
        dk = []
        for side, yt in (('a', rec['a']['yt']), ('b', rec['b']['yt'])):
            lc = d['loc'][side]; z = D.place_source(os.path.join(paths.LIB, yt + '.m4a'), lc['track_t'], lc['mix_t'], len(pro)); z, _ = D.refine_lag(pro, z)
            dk.append(np.stack([z, z], 1).astype(np.float32))
        n = int(len(pro) // bs); lows = V.bar_db(y, n, bs, 30, 150)
        eA, hop = V.onset_env(dk[0]); eB, _ = V.onset_env(dk[1])
        pA, cA = V.bar_phase(eA, hop, n, bs, bar/4); pB, cB = V.bar_phase(eB, hop, n, bs, bar/4)
        lag, xr = V.bar_lag(V.flat_env(eA, hop, bar/4), V.flat_env(eB, hop, bar/4), hop, n, bs)
        ca, cb = np.array(d['curves']['all_a'], float), np.array(d['curves']['all_b'], float); m = min(n, len(ca), len(cb))
        aud = np.zeros(n, bool); aud[:m] = (ca[:m] > -12) & (cb[:m] > -12)
        out[rec['id']] = dict(n=n, lows=lows, s=int(d['in_entry_clip_bar']), e=int(min(n, d['out_gone_clip_bar'])), pA=pA, cA=cA, pB=pB, cB=cB, lag=lag, xr=xr, aud=aud, beat_ms=bar/4*1000)
        print('pro', rec['id'], flush=True)
    pickle.dump(out, open(p, 'wb')); return out

def case_feats():
    p = os.path.join(C, 'cases_b.pkl')
    cases = pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
    os.chdir(SRC2); import blend_diag as BD
    from engine import BS, BAR
    rows = [json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', 'default.jsonl'))]
    for r in rows:
        pid = r['id']
        if any(k.startswith(pid + '|') for k in cases): continue
        M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
        s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0); mid = (s + e) // 2
        inj = {'clean': (A, B)}
        for ms in (60, 110):
            k = int(ms/1000*V.SR); inj[f'clash{ms}'] = (A, np.concatenate([np.zeros((k, 2), np.float32), B[:-k]]))
        for L in (4, 8):
            i0, i1 = int((mid - L//2)*BS), int((mid + L - L//2)*BS); AA, BB = A.copy(), B.copy(); AA[i0:i1] = lows_cut(A[i0:i1]); BB[i0:i1] = lows_cut(B[i0:i1]); inj[f'hole{L}'] = (AA, BB)
        i0, i1 = int(mid*BS), int((mid+1)*BS); AA, BB = A.copy(), B.copy(); AA[i0:i1] *= 10**(-0.5); BB[i0:i1] *= 10**(-0.5); inj['pump'] = (AA, BB)
        for kind, (a, b) in inj.items():
            f = V.deck_feats_b(a, b, BS, BAR/4); f.update(s=s, e=e, pid=pid, kind=kind, split=split_of(pid), aud=V.audible_mask(f['allA'], f['allB']), beat_ms=BAR/4*1000)
            for kk in ('allA', 'allB'): f.pop(kk)
            cases[f'{pid}|{kind}'] = f
        pickle.dump(cases, open(p, 'wb')); print('case', pid, flush=True)
    return cases

FORM = ['area']
def scores(f, T0, D, cmin):
    h = V.hole_score(f['lows'], f['s'], f['e'], T0) if FORM[0] == 'area' else V.hole_run(f['lows'], f['s'], f['e'], T0)
    return (h, V.clash_score_b(f['lag'], f['xr'], f['aud'], D, cmin))

def p95(v): return float(np.percentile(v, 95))

def evaluate(cases, pros, T0, D, cmin, split):
    ps = [scores(f, T0, D, cmin) for f in pros.values()]; th = (p95([x[0] for x in ps]), p95([x[1] for x in ps]))
    # leave-one-pro-out false-alarm rate
    fa_h = fa_c = 0
    for j in range(len(ps)):
        rest = [x for i, x in enumerate(ps) if i != j]
        fa_h += ps[j][0] > p95([x[0] for x in rest]); fa_c += ps[j][1] > p95([x[1] for x in rest])
    cs = [f for f in cases.values() if f['split'] == split]; det = {}; flag_clean = dict(hole=0, clash=0); n_clean = 0
    for f in cs:
        h, c = scores(f, T0, D, cmin); fh, fc = h > th[0], c > th[1]
        if f['kind'] == 'clean': n_clean += 1; flag_clean['hole'] += fh; flag_clean['clash'] += fc
        else:
            k = f['kind']; det.setdefault(k, [0, 0, 0, 0]); det[k][0] += 1; det[k][1] += fh; det[k][2] += fc; det[k][3] += (fh or fc)
    return dict(T0=T0, D=D, cmin=cmin, thr_hole=round(th[0], 1), thr_clash=th[1],
                pro_fa_loo=dict(hole=round(fa_h/len(ps), 3), clash=round(fa_c/len(ps), 3), n=len(ps)),
                clean_flag_rate=dict(hole=round(flag_clean['hole']/max(1, n_clean), 3), clash=round(flag_clean['clash']/max(1, n_clean), 3), n=n_clean),
                detect={k: dict(n=v[0], hole=round(v[1]/v[0], 3), clash=round(v[2]/v[0], 3)) for k, v in sorted(det.items())})

if __name__ == '__main__':
    pros = pro_feats(); cases = case_feats()
    # choose hole T0 on DEV: maximise mean hole detection on hole4/hole8; tie -> lower clean flag rate
    best_h = best_c = None
    for form, T0 in itertools.product(FORMS, T0S):
        FORM[0] = form; r = evaluate(cases, pros, T0, 30, 0.25, 'dev'); dh = np.mean([r['detect'][k]['hole'] for k in ('hole4', 'hole8')])
        key = (dh, -r['clean_flag_rate']['hole'])
        if best_h is None or key > best_h[0]: best_h = (key, T0, form)
    FORM[0] = best_h[2]
    for D, cmin in itertools.product(DS, CMINS):
        r = evaluate(cases, pros, best_h[1], D, cmin, 'dev'); dc = np.mean([r['detect'][k]['clash'] for k in ('clash60', 'clash110')])
        key = (dc, -r['clean_flag_rate']['clash'])
        if best_c is None or key > best_c[0]: best_c = (key, D, cmin)
    T0, D, cmin = best_h[1], best_c[1], best_c[2]
    out = dict(chosen=dict(T0=T0, D=D, cmin=cmin, hole_form=FORM[0], clash='v2b_xcorr'), dev=evaluate(cases, pros, T0, D, cmin, 'dev'), heldout=evaluate(cases, pros, T0, D, cmin, 'heldout'),
               n_pros=len(pros), n_pairs=len({f['pid'] for f in cases.values()}))
    out['thresholds'] = dict(hole=out['dev']['thr_hole'], clash=out['dev']['thr_clash'])
    json.dump(out, open(os.path.join(H, 'hardcheck_v2_calib.json'), 'w'), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))
