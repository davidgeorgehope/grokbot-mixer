"""CONSONANCE diagnostic (2026-11-19): does mid-band cross-roughness line up with what pros chose at all?
For each of the 33 protrans pairs, compare the roughness of (a) the pro's actual overlap (replica/protrans_decisions.json,
entry bars + overlap), (b) our default pick (checkpoint of a baseline variant), against every 4-bar-aligned window of the
same length in the two tracks (percentile: 0 = most consonant window available, 1 = roughest).
Usage: python3 protrans/consonance_diag.py [baseline_variant]   -> results/consonance_diag.json"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, run_admitted_tune as T
sys.path.insert(0, paths.SRC2)
import consonance as C
from scipy import stats

def pct(r, pool):
    pool = np.array([p for p in pool if p is not None]); return float(np.mean(pool < r) + 0.5 * np.mean(pool == r)) if len(pool) and r is not None else None

def main(base='d1118_base'):
    recs = T.load_recs(); dec = json.load(open(os.path.join(HERE, 'replica', 'protrans_decisions.json')))
    ck = T.load_ckpt(base); rows = []
    for rec in recs:
        a, b = rec['a']['yt'], rec['b']['yt']; PA, PB = C.track_peaks(a), C.track_peaks(b)
        d = dec.get(rec['id']) or {}; row = ck.get(rec['id']) or {}
        out = dict(id=rec['id'], split=rec['split'])
        X = 16
        pool = [C.window_roughness(PA, PB, list(range(ea, ea + X)), list(range(ib, ib + X)))
                for ea in range(0, len(PA) - X, 4) for ib in range(0, len(PB) - X, 4)]
        if d.get('out_bar_at_entry') is not None:
            ea, ib = int(round(d['out_bar_at_entry'])), int(round(d['in_bar_at_entry']))
            out['pro_r'] = C.window_roughness(PA, PB, list(range(ea, ea + X)), list(range(ib, ib + X)))
            out['pro_pct'] = pct(out['pro_r'], pool)
        w = (row.get('pick') or {}).get('win')
        if w:
            wa, wb = C.window_bars(w); wa, wb = wa[-X:] if w[4] > X else wa, wb[-X:] if w[4] > X else wb
            # default 32-bar windows: the last 16 bars are the audible overlap after TAIL_EXIT/FADE=long; also report full
            out['def_r'] = C.window_roughness(PA, PB, wa, wb); out['def_pct'] = pct(out['def_r'], pool)
            out['def_r_full'] = C.win_roughness(a, b, w)
        out['score'] = (row.get('score') or {}).get('score'); out['pool_med'] = float(np.median([p for p in pool if p is not None]))
        rows.append(out); print(json.dumps(out), flush=True)
    pp = [r['pro_pct'] for r in rows if r.get('pro_pct') is not None]; dp = [r['def_pct'] for r in rows if r.get('def_pct') is not None]
    both = [(r['pro_r'], r['def_r']) for r in rows if r.get('pro_r') is not None and r.get('def_r') is not None]
    sc = [(r['def_r'], r['score']) for r in rows if r.get('def_r') is not None and r.get('score') is not None]
    summ = dict(n=len(rows), pro_pct_median=float(np.median(pp)), pro_pct_mean=float(np.mean(pp)),
                pro_pct_wilcoxon_vs_half_p=float(stats.wilcoxon(np.array(pp) - 0.5).pvalue),
                def_pct_median=float(np.median(dp)), def_pct_mean=float(np.mean(dp)),
                pro_lower_than_default=sum(1 for p, q in both if p < q), n_pairs_both=len(both),
                pro_vs_def_wilcoxon_p=float(stats.wilcoxon([p - q for p, q in both]).pvalue),
                spearman_def_r_vs_score=list(map(float, stats.spearmanr(*zip(*sc)))))
    json.dump(dict(rows=rows, summary=summ), open(os.path.join(paths.RESULTS, 'consonance_diag.json' if C.FMIN == 150.0 else f'consonance_diag_f{int(C.FMIN)}.json'), 'w'), indent=1)
    print('SUMMARY ' + json.dumps(summ), flush=True)

if __name__ == '__main__':
    main(*(sys.argv[1:] or []))
