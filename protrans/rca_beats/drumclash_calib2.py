"""Confidence-gated drumclash calibration (v2: HPSS percussive, kick-vs-kick AND snare-vs-snare agreement).
Negatives: the 33 pro clips (decks placed from their stretched st audio via score._deck_line, r >= 0.15, gains by NNLS spectra).
Positives (the listener's 'off/flam/horrible' calls), rendered exactly as delivered: 11-20 hm09 B, 11-20 JS12 default A (lock -66.8),
11-17 WAO->GB B (rendered before the lock reached the dry path: lock 0), 11-18 hm13 B. Our 33 cohort picks: n1120_base metas."""
import os, sys, json, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.dirname(HERE)
sys.path[:0] = [PT, '/workspace/mixes/src2', '/workspace/mixes/src/eval', HERE]
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
import drumclash as DC, score as S, diagnose_gap as DG, control_curves as CC, paths
import run_admitted_tune as T

def pro(rec, r_min=0.15):
    y = S._load(rec['pro_clip']); Fm, em = CC.bandpow(y), S._fine_env(y); al = []; lines = {}
    for nm in ('a', 'b'):
        st = f"{paths.SRC2}/st/{rec[nm]['yt']}.wav"; ln = S._deck_line(y, Fm, em, st)
        if not ln or ln['r'] < r_min: return dict(error=f'deck {nm} not located', r=None if not ln else ln['r'])
        src = S._load(st); t = (np.arange(len(y)) / S.SR - ln['a']) / ln['s']
        al.append(np.interp(t, np.arange(len(src)) / S.SR, src, left=0, right=0).astype(np.float32)); lines[nm] = ln
    gains, _, times, hop = DG.band_gains(y, *al); tt = np.arange(len(y)) / S.SR
    decks = [x * np.interp(tt, times, gains['all'][nm]) for x, nm in zip(al, ('a', 'b'))]
    out = DC.decks_eval(*decks); out['r'] = {k: v['r'] for k, v in lines.items()}; return out

def rendered(meta):
    os.chdir(paths.SRC2); import blend_diag as BD
    M = json.load(open(meta)); s0, A, B = BD.crop_decks(M, 0); t = M['trans'][0]
    return DC.rendered_eval(A, B, s0, float(t['start_bar']), float(t['end_bar']))

def positive(pid, win, lock_ms):
    import blend_bench as BB, recreate
    rec = {r['id']: r for r in T.load_recs()}[pid]; created = []
    for x in ('a', 'b'): recreate._prep_track(rec[x]['yt'], os.path.join(paths.LIB, rec[x]['yt'] + '.m4a'), created)
    rules = json.load(open(paths.RULES)); rules['BLEND_LOCK'] = 0; env = recreate.apply_rules(rules); os.environ.update(env); os.chdir(paths.SRC2)
    c = dict(fam='label', win=win, env=env); dk, M = BB.render(c, rec['a']['yt'], rec['b']['yt'], 'lab' + pid[-2:])
    if lock_ms: M['decks'][1]['blend_lock_ms'] = lock_ms
    p = f'/tmp/protrans_bench/lab_{pid}_meta.json'; json.dump(M, open(p, 'w'), default=str); return rendered(p)

LABELS = [('11-20 hm09 B (ours)', 'hybrid_minds_ukf__09', ['n', 208, None, 48, 16], 0),
          ('11-20 JS12 default A', 'joe_syntax_hospital__12', ['n', 224, None, 48, 16], -66.8),
          ('11-17 WAO->GB B (no lock)', 'joe_syntax_hospital__11', ['n', 240, None, 24, 16], 0),
          ('11-18 hm13 B', 'hybrid_minds_ukf__13', ['n', 192, None, 32, 16], 0)]

if __name__ == '__main__':
    res = dict(pro={}, ours={}, labels={})
    cp = os.path.join(HERE, 'calib2_progress.json')
    if os.path.exists(cp): res = json.load(open(cp))
    for rec in T.load_recs():
        if rec['id'] in res['pro']: continue
        try: r = pro(rec)
        except Exception as e: r = dict(error=f'{type(e).__name__}: {str(e)[-200:]}')
        r.pop('rows', None); res['pro'][rec['id']] = r; print('PRO', rec['id'], r, flush=True); json.dump(res, open(cp, 'w'), indent=1, default=float)
    for f in glob.glob('/workspace/mixes/protrans/rca_beats/cal_v1/cal_*.json'):
        c = json.load(open(f)); m = (c.get('ours') or {}).get('meta')
        if not m or not os.path.exists(m) or c['id'] in res['ours']: continue
        r = rendered(m); r.pop('rows', None); res['ours'][c['id']] = r; print('OURS', c['id'], r, flush=True)
    for lab, pid, win, lk in LABELS:
        r = positive(pid, win, lk); r.pop('rows', None); res['labels'][lab] = r; print('LABEL', lab, r, flush=True)
    pv = [v['confidence'] for v in res['pro'].values() if 'confidence' in v]
    res['summary'] = dict(n_pro=len(pv), pro_not_located=[k for k, v in res['pro'].items() if 'error' in v], pro_p95=float(np.percentile(pv, 95)),
                          pro_max=max(pv), pro_above_high=[k for k, v in res['pro'].items() if v.get('confidence', 0) > DC.HIGH],
                          ours_levels={k: v['level'] for k, v in res['ours'].items() if v['level'] != 'clean'},
                          labels={k: (v['confidence'], v['level'], v.get('cluster_lag_ms')) for k, v in res['labels'].items()})
    json.dump(res, open(os.path.join(HERE, 'detector_calibration_v2.json'), 'w'), indent=1, default=float)
    print('SUMMARY', json.dumps(res['summary'], default=float), flush=True)
