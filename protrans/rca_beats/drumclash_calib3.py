"""v3 lattice calibration (2026-11-20). Negatives: the 33 pro clips (decks = their stretched st audio placed by score._deck_line,
r >= 0.15, NNLS gains). Two-stage pro-p95 calibration only: BAR_OFF = pro p95 of per-bar off share; FLAG3 = pro p95 of pair
confidence at that BAR_OFF. HIGH stays 0.5 (majority of bars). Positives: the listener's calls, rendered as delivered."""
import os, sys, json, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.dirname(HERE)
sys.path[:0] = [PT, '/workspace/mixes/src2', '/workspace/mixes/src/eval', HERE]
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True)
import drumclash as DC, score as S, diagnose_gap as DG, control_curves as CC, paths, librosa
import run_admitted_tune as T

def pro(rec, r_min=0.15):
    y = S._load(rec['pro_clip']); Fm, em = CC.bandpow(y), S._fine_env(y); al = []; lines = {}
    for nm in ('a', 'b'):
        st = f"{paths.SRC2}/st/{rec[nm]['yt']}.wav"; ln = S._deck_line(y, Fm, em, st)
        if not ln or ln['r'] < r_min: return dict(error=f'deck {nm} not located', r=None if not ln else ln['r'])
        src = S._load(st); t = (np.arange(len(y)) / S.SR - ln['a']) / ln['s']
        al.append(np.interp(t, np.arange(len(src)) / S.SR, src, left=0, right=0).astype(np.float32)); lines[nm] = ln
    gains, _, times, hop = DG.band_gains(y, *al); tt = np.arange(len(y)) / S.SR
    ya, yb = (librosa.resample(x * np.interp(tt, times, gains['all'][nm]), orig_sr=S.SR, target_sr=DC.SR_E) for x, nm in zip(al, ('a', 'b')))
    per = 60 / 174 * float(np.mean([lines['a']['s'], lines['b']['s']]))
    out = DC.lattice_eval(ya, yb, per); out['r'] = {k: round(v['r'], 3) for k, v in lines.items()}; return out

def rendered(meta):
    os.chdir(paths.SRC2); import blend_diag as BD
    M = json.load(open(meta)); s0, A, B = BD.crop_decks(M, 0); t = M['trans'][0]
    return DC.rendered_lattice(A, B, s0, float(t['start_bar']), float(t['end_bar']))

# (pid, window, lock_ms) rendered exactly as delivered (hm09 B: the lock did not engage, 'inconsistent / too few agreeing bars')
LABELS = [('11-20 hm09 B (delivered)', 'hybrid_minds_ukf__09', ['n', 208, None, 48, 16], 0),
          ('11-20 JS12 default A', 'joe_syntax_hospital__12', ['n', 224, None, 48, 16], -66.8),
          ('11-17 WAO->GB B (no lock)', 'joe_syntax_hospital__11', ['n', 240, None, 24, 16], 0),
          ('11-18 hm13 B', 'hybrid_minds_ukf__13', ['n', 192, None, 32, 16], 0)]

def label_meta(pid, win, lock_ms):
    p = f'/tmp/protrans_bench/lab_{pid}_meta.json'
    if not os.path.exists(p):
        import blend_bench as BB, recreate
        rec = {r['id']: r for r in T.load_recs()}[pid]; created = []
        for x in ('a', 'b'): recreate._prep_track(rec[x]['yt'], os.path.join(paths.LIB, rec[x]['yt'] + '.m4a'), created)
        rules = json.load(open(paths.RULES)); rules['BLEND_LOCK'] = 0; env = recreate.apply_rules(rules); os.environ.update(env); os.chdir(paths.SRC2)
        dk, M = BB.render(dict(fam='label', win=win, env=env), rec['a']['yt'], rec['b']['yt'], 'lab' + pid[-2:])
        if lock_ms: M['decks'][1]['blend_lock_ms'] = lock_ms
        json.dump(M, open(p, 'w'), default=str)
    return p

def conf(rows, bar_off):
    off = [r['off_share'] for r in rows if 'off_share' in r]
    return None if len(off) < DC.MIN_BARS else sum(1 for x in off if x > bar_off) / len(off)

if __name__ == '__main__':
    cp = os.path.join(HERE, 'calib3_progress.json'); res = json.load(open(cp)) if os.path.exists(cp) else dict(pro={}, ours={}, labels={})
    for rec in T.load_recs():
        if rec['id'] in res['pro']: continue
        try: r = pro(rec)
        except Exception as e: r = dict(error=f'{type(e).__name__}: {str(e)[-200:]}')
        res['pro'][rec['id']] = r; print('PRO', rec['id'], {k: v for k, v in r.items() if k != 'rows'}, flush=True); json.dump(res, open(cp, 'w'), default=float)
    for f in sorted(glob.glob(os.path.join(HERE, 'cal_v1', 'cal_*.json'))):
        c = json.load(open(f)); m = (c.get('ours') or {}).get('meta')
        if not m or not os.path.exists(m) or c['id'] in res['ours']: continue
        r = rendered(m); res['ours'][c['id']] = r; print('OURS', c['id'], {k: v for k, v in r.items() if k != 'rows'}, flush=True)
    json.dump(res, open(cp, 'w'), default=float)
    for lab, pid, win, lk in LABELS:
        r = rendered(label_meta(pid, win, lk)); res['labels'][lab] = r; print('LABEL', lab, {k: v for k, v in r.items() if k != 'rows'}, flush=True)
    bars = [r['off_share'] for v in res['pro'].values() for r in v.get('rows', []) if 'off_share' in r]
    bar_off = float(np.percentile(bars, 95))
    pc = {k: conf(v.get('rows', []), bar_off) for k, v in res['pro'].items() if 'error' not in v}
    pv = [x for x in pc.values() if x is not None]; flag3 = float(np.percentile(pv, 95)) if pv else 0.0
    lvl = lambda c: 'clean' if c is None or c <= flag3 else ('clash' if c > DC.HIGH else 'gray')
    summ = dict(n_pro=len(pc), n_pro_scored=len(pv), pro_not_located={k: v.get('r') for k, v in res['pro'].items() if 'error' in v},
                n_pro_bars=len(bars), BAR_OFF=round(bar_off, 3), FLAG3=round(flag3, 3), pro_max=max(pv) if pv else None,
                pro_above_flag={k: round(c, 3) for k, c in pc.items() if c is not None and c > flag3},
                pro_above_high=[k for k, c in pc.items() if c is not None and c > DC.HIGH],
                ours_levels={k: (round(c, 3), lvl(c)) for k, c in ((k, conf(v.get('rows', []), bar_off)) for k, v in res['ours'].items()) if lvl(c) != 'clean'},
                labels={k: (None if conf(v.get('rows', []), bar_off) is None else round(conf(v.get('rows', []), bar_off), 3), lvl(conf(v.get('rows', []), bar_off)), v.get('why')) for k, v in res['labels'].items()})
    res['summary'] = summ; json.dump(res, open(os.path.join(HERE, 'detector_calibration_v3.json'), 'w'), indent=1, default=float)
    print('SUMMARY', json.dumps(summ, default=float), flush=True)
