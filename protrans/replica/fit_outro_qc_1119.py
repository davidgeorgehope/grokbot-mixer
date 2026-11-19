#!/usr/bin/env python3
"""2026-11-19 OUTRO_QC: fit the outro deductions from pro data on dev and report how often pros blend over the outgoing's final outro block.
Unit: one dev transition (outgoing track profiled). Block = the engine's outro-over-intro exit area: [es-16, es), es = music_end floored
to 8 bars. Label = the pro's outgoing blend window reaches into that block (pro blend end > es-16). Model: L2 logistic of label on the six yes/no
outro features; deduction(f) = clip(1 - p(f)/p(clean), 0, 1). Leave-one-DJ-out: each outgoing track gets weights fitted without every DJ
that played it, so dev scoring never sees its own pros. -> halftime/outro_qc_w.json, outro_qc_fit_1119.json"""
import os, sys, json, collections
import numpy as np
from sklearn.linear_model import LogisticRegression
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, 'halftime'))
import safeplace_1119 as S, outro_qc as Q
ST = '/workspace/mixes/src2/st/'; rng = np.random.default_rng(20261119)

def fit(rows):
    X = np.array([[r['f'][k] for k in Q.FEATS] for r in rows], float); y = np.array([r['y'] for r in rows])
    m = LogisticRegression(C=1.0).fit(X, y); return dict(coef=dict(zip(Q.FEATS, map(float, m.coef_[0]))), b=float(m.intercept_[0]))

rows = []
for r in S.dev_rows():
    ya = r['ya']
    if not (os.path.exists(ST + ya + '.json') and os.path.exists(ST + ya + '.slowdown.json')): continue
    sec = json.load(open(ST + ya + '.sections.json')); n = len(json.load(open(ST + ya + '.json'))['bar']['all'])
    es = min(n, (sec['music_end'] // 8) * 8); f = Q.feats(ya, es - 16, es)
    if f is None or r.get('pro_out') is None: continue
    # pro A window = [pro_out-1, pro_out-1+overlap) (pro_out is the 1-based outgoing bar where the pro's blend starts; slow_scan_1119 convention)
    po = int(round(float(r['pro_out']))) - 1; ov = int(round(float(r.get('pro_ov') or 16))); dw = S.default_win(r)
    rows.append(dict(id=r['id'], dj=r['dj'], mix=r['mix'], ya=ya, es=es, f=f, y=int(po + ov > es - 16), pro_win=[po, po + ov],
                     in_outro=int(po >= sec.get('outro_start', 1e9)), def_win=[dw[1] - dw[4], dw[1]], def_y=int(dw[1] > es - 16),
                     pro_end_vs_es=po + ov - es, def_end_vs_es=dw[1] - es))
print('n', len(rows), 'djs', len({r['dj'] for r in rows}), 'mixes', len({r['mix'] for r in rows}))

def mixboot(vals_by_row, B=4000):
    mixes = sorted({r['mix'] for r in rows}); by = collections.defaultdict(list)
    for r, v in zip(rows, vals_by_row): by[r['mix']].append(v)
    out = []
    for _ in range(B):
        s = rng.choice(mixes, len(mixes)); v = [x for m in s for x in by[m]]; out.append(np.mean(v))
    return [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)]

rep = dict(n=len(rows), pro_final_block=round(np.mean([r['y'] for r in rows]), 3), pro_final_block_ci=mixboot([r['y'] for r in rows]),
           default_final_block=round(np.mean([r['def_y'] for r in rows]), 3), default_final_block_ci=mixboot([r['def_y'] for r in rows]),
           pro_starts_in_outro=round(np.mean([r['in_outro'] for r in rows]), 3), per_feature={})
for k in Q.FEATS:
    yes = [r['y'] for r in rows if r['f'][k]]; no = [r['y'] for r in rows if not r['f'][k]]
    rep['per_feature'][k] = dict(n_yes=len(yes), pro_rate_yes=round((sum(yes) + 1) / (len(yes) + 2), 3), pro_rate_no=round((sum(no) + 1) / (len(no) + 2), 3),
                                 ratio=round(((sum(yes) + 1) / (len(yes) + 2)) / ((sum(no) + 1) / (len(no) + 2)), 3))
W_all = fit(rows); rep['fit_all'] = W_all
djs_of = collections.defaultdict(set)
for r in rows: djs_of[r['ya']].add(r['dj'])
# also tracks of the 33-pair cohort / future pairs use fit_all; dev tracks get leave-their-DJs-out fits
per_track = {}
for ya, djs in djs_of.items():
    tr = [r for r in rows if r['dj'] not in djs]
    per_track[ya] = fit(tr) if len({r['y'] for r in tr}) > 1 else W_all
json.dump(dict(model='logit', feats=list(Q.FEATS), all=W_all, per_track=per_track, ref='fit_outro_qc_1119 v1'), open(Q.W_PATH, 'w'), indent=1)
# in-sample check: mean deduction where pros do / don't use the final block
for r in rows:
    r['ded'] = Q.ded_from(per_track.get(r['ya'], W_all), r['f'])
rep['mean_deduction_pro_used_block'] = round(np.mean([r['ded'] for r in rows if r['y']]), 3)
rep['mean_deduction_pro_left_earlier'] = round(np.mean([r['ded'] for r in rows if not r['y']]), 3)
json.dump(dict(rep=rep, rows=rows), open(os.path.join(H, 'outro_qc_fit_1119.json'), 'w'), indent=1, default=str)
print(json.dumps(rep, indent=1))
