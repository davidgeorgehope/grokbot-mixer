"""Blend-style census over built rows (decision level, no render)."""
import json, sys, os, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ridegate_live as R

def frac_in(drops, a, b):
    if b <= a: return 0.0
    n = sum(1 for x in range(int(a), int(b)) if any(d0 <= x < d1 for d0, d1 in drops))
    return n / (b - a)

def style(sa, sb, out0, in0, X):
    da = [tuple(map(int, d)) for d in (sa.get('drops') or [])]
    db = [tuple(map(int, d)) for d in (sb.get('drops') or [])]
    fa, fb = frac_in(da, out0, out0 + X), frac_in(db, in0, in0 + X)
    A = 'drop' if fa >= 0.75 else 'out'
    Bs = 'drop' if fb >= 0.75 else 'in'
    return f'{A}>{Bs}'

def win_style(r, d):
    if d.get('is_default') or not d.get('win'):
        out0, in0, X = r['dex'] - 1, r['dcue'] - 1, r['dX']
    else:
        w = d['win']; out0, in0, X = w[1] - w[4], w[3], w[4]
    return style(r['sa'], r['sb'], out0, in0, X), X

if __name__ == '__main__':
    rows = [r for r in R.load_all_built() if r['set'] not in ('excluded', 'holdout')]
    pack = R.load_pack(sys.argv[1] if len(sys.argv) > 1 else None)
    decs = R.predict_rows(pack, rows)
    out = collections.defaultdict(collections.Counter)
    for r, d in zip(rows, decs):
        s, X = win_style(r, d)
        out[r['set']][s] += 1
        if r.get('pro_ov'):
            out[r['set'] + '_PRO'][style(r['sa'], r['sb'], r['pro_out'] - 1, r['pro_in'] - 1, int(round(r['pro_ov'])))] += 1
        out[r['set'] + '_DEFAULT'][style(r['sa'], r['sb'], r['dex'] - 1, r['dcue'] - 1, r['dX'])] += 1
    for k in sorted(out):
        n = sum(out[k].values())
        print(k, n, {s: f'{c/n:.0%}' for s, c in sorted(out[k].items())})
