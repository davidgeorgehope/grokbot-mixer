#!/usr/bin/env python3
"""2026-11-19: does PLACE=safe cut tracks short? For each dev pair and arm (default / b / c, raw and final windows) measure how much of
the outgoing track A plays (exit bar / music end), whether A's last drop (its main payoff, usually drop 2) gets heard in full before
the blend starts or is reached at all, and on the incoming side whether the cue skips B's first drop. Pro exits (pro_out) for reference.
Mix-grouped bootstrap CIs (4000 draws, seed 20261119). usage: placequal_1119.py [variant ...]"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import safeplace_1119 as S
VS = sys.argv[1:] or ['b', 'c']
R = {r['id']: r for r in S.dev_rows()}
EV = {v: {p['id']: p for p in json.load(open(os.path.join(H, f'safeplace_{v}_eval.json')))['pairs']} for v in VS}
ids = sorted(set.intersection(*[set(e) for e in EV.values()]) & set(R))
def q(r, w):
    sa, sb = r['sa'], r['sb']; na = S.NA(sa); e, ib, X = int(w[1]), int(w[3]), int(w[4]); s = e - X
    dr = sa.get('drops') or []; ld = dr[-1] if dr else None; d1b = sb.get('drop1')
    heard = (min(s, ld[1]) - ld[0]) / max(1, ld[1] - ld[0]) if ld else np.nan
    return dict(played=min(1.0, e / na), solo_end=min(1.0, s / na), bars_cut=max(0, na - e),
                last_drop_full=float(s >= ld[1] - 2) if ld else np.nan, last_drop_reached=float(e > ld[0] + 4) if ld else np.nan,
                last_drop_heard_solo=float(np.clip(heard, 0, 1)) if ld else np.nan, n_dropsA=len(dr),
                skips_B_drop1=float(d1b is not None and ib > int(d1b) + 2) if d1b else np.nan)
rows = []
for i in ids:
    r = R[i]; p0 = EV[VS[0]][i]; row = dict(id=i, mix=r['mix'], dj=r['dj'], na=S.NA(r['sa']), drops=r['sa'].get('drops'))
    row['default'] = q(r, p0['def_win'])
    for v in VS:
        for arm in ('raw', 'final'): row[f'{v}_{arm}'] = q(r, EV[v][i][f'{arm}_win'])
    po = r.get('pro_out')
    if po: row['pro'] = q(r, ['n', int(round(po)), None, int(r.get('pro_in') or 0), 16])  # pro: exit bar only (X nominal 16)
    rows.append(row)
mixes = sorted({x['mix'] for x in rows}); rng = np.random.default_rng(20261119)
def agg(arm, k):
    v = [(x['mix'], x[arm][k]) for x in rows if arm in x and np.isfinite(x[arm][k])]; return float(np.mean([b for _, b in v])) if v else np.nan
def dci(arm, k, base='default'):
    by = {}
    for x in rows:
        if arm in x and base in x and np.isfinite(x[arm][k]) and np.isfinite(x[base][k]): by.setdefault(x['mix'], []).append(x[arm][k] - x[base][k])
    G = [np.array(by[m]) for m in by]; d = float(np.mean(np.concatenate(G))); bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(4000)]
    lo, hi = np.percentile(bs, [2.5, 97.5]); return dict(delta=round(d, 3), ci=[round(float(lo), 3), round(float(hi), 3)])
K = ['played', 'solo_end', 'bars_cut', 'last_drop_full', 'last_drop_reached', 'last_drop_heard_solo', 'skips_B_drop1']
ARMS = ['default'] + [f'{v}_{a}' for v in VS for a in ('raw', 'final')] + ['pro']
out = dict(n=len(rows), n_mixes=len(mixes), share_two_plus_drops=round(float(np.mean([x['default']['n_dropsA'] >= 2 for x in rows])), 3),
           means={a: {k: round(agg(a, k), 3) for k in K} for a in ARMS},
           vs_default={a: {k: dci(a, k) for k in ('played', 'last_drop_full', 'last_drop_heard_solo', 'skips_B_drop1')} for a in ARMS[1:]},
           p10_played={a: round(float(np.percentile([x[a]['played'] for x in rows if a in x], 10)), 3) for a in ARMS})
json.dump(dict(out, rows=rows), open(os.path.join(H, 'placequal_1119.json'), 'w'), indent=1, default=float); print(json.dumps(out, indent=1))
