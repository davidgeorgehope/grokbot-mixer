"""pulse-term calibration (2026-11-20): per-bar pulse_gap (|1-beat autocorr of deck A's percussive onsets - deck B's| on
drum-on-drum bars) on the 31 locatable pro clips -> PULSE_BAR = pro p95 per bar; PULSE_FLAG = pro p95 of pair confidence.
Positives: the 4 label renders (calib3 metas). Pro decks reconstructed exactly as drumclash_calib3.pro()."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [HERE]
import drumclash_calib3 as C3
from drumclash_calib3 import DC, S, CC, DG, paths, librosa, T

def pro(rec, r_min=0.15):
    y = S._load(rec['pro_clip']); Fm, em = CC.bandpow(y), S._fine_env(y); al = []; lines = {}
    for nm in ('a', 'b'):
        st = f"{paths.SRC2}/st/{rec[nm]['yt']}.wav"; ln = S._deck_line(y, Fm, em, st)
        if not ln or ln['r'] < r_min: return dict(error=f'deck {nm} not located')
        src = S._load(st); t = (np.arange(len(y)) / S.SR - ln['a']) / ln['s']
        al.append(np.interp(t, np.arange(len(src)) / S.SR, src, left=0, right=0).astype(np.float32)); lines[nm] = ln
    gains, _, times, hop = DG.band_gains(y, *al); tt = np.arange(len(y)) / S.SR
    ya, yb = (librosa.resample(x * np.interp(tt, times, gains['all'][nm]), orig_sr=S.SR, target_sr=DC.SR_E) for x, nm in zip(al, ('a', 'b')))
    per = 60 / 174 * float(np.mean([lines['a']['s'], lines['b']['s']]))
    return dict(rows=DC._pulse_rows(ya, yb, per, 0, 0, 10 ** 6))

if __name__ == '__main__':
    cp = os.path.join(HERE, 'calib4_progress.json'); res = json.load(open(cp)) if os.path.exists(cp) else dict(pro={}, labels={})
    for rec in T.load_recs():
        if rec['id'] in res['pro']: continue
        try: r = pro(rec)
        except Exception as e: r = dict(error=f'{type(e).__name__}: {str(e)[-200:]}')
        res['pro'][rec['id']] = r; print('PRO', rec['id'], r.get('error') or DC.pulse_summary(r['rows'], 0.5, 0.0), flush=True); json.dump(res, open(cp, 'w'), default=float)
    os.chdir(paths.SRC2); import blend_diag as BD
    for lab, pid, win, lk in C3.LABELS:
        M = json.load(open(C3.label_meta(pid, win, lk))); s0, A, B = BD.crop_decks(M, 0); t = M['trans'][0]
        res['labels'][lab] = DC.rendered_pulse(A, B, s0, float(t['start_bar']), float(t['end_bar']))
    bars = [r['pulse_gap'] for v in res['pro'].values() for r in v.get('rows', []) if 'pulse_gap' in r]
    pb = float(np.percentile(bars, 95))
    pc = {k: DC.pulse_summary(v['rows'], pb, 0.0) for k, v in res['pro'].items() if 'rows' in v}
    pv = [x['confidence'] for x in pc.values() if x['n_dd'] >= DC.MIN_BARS]; pf = float(np.percentile(pv, 95))
    summ = dict(n_pro=len(pc), n_pro_bars=len(bars), PULSE_BAR=round(pb, 3), PULSE_FLAG=round(pf, 3), pro_max=max(pv),
                pro_above_flag={k: x['confidence'] for k, x in pc.items() if x['confidence'] > pf},
                pro_above_high=[k for k, x in pc.items() if x['confidence'] > DC.HIGH],
                labels={k: DC.pulse_summary(v['rows'], pb, pf) for k, v in res['labels'].items()})
    res['summary'] = summ; json.dump(res, open(os.path.join(HERE, 'detector_calibration_pulse.json'), 'w'), indent=1, default=float)
    print('SUMMARY', json.dumps(summ, default=float), flush=True)
