#!/usr/bin/env python3
"""2026-11-19 exit-type picker: hard checks (HC_A / HC_B v2, plus HC_C) on rendered changed dev picks vs the rendered default,
then the veto (a pick that newly fails reverts to the default). Dev only. usage: exittype_1119_hc.py"""
import json, os, sys, pickle, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import final_eval as FE, hc3_count_1119 as HC3, picker_1119 as P, analyze as A
J = json.load(open(os.path.join(H, 'exittype_1119_cv_r4.json')))
def load(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'); return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
DEF = {}
for v in ('default', 'ndef1119'):
    for k, a in load(v).items(): DEF.setdefault(k, a)
PK = load('pick1119'); OUT = {}
def fl(a): f = FE.flags(a); f.update({k: v for k, v in HC3.flags3(a).items() if k in ('HC_C', 'hole_v3', 'hole_v3_score')}); return f
g = [p['mix'] for p in J['per_pair']]
def ec(p, x): return (abs(x['exit'] - p['pro_out']) + abs(x['cue'] - p['pro_in'])) / 2
for arm, v in (('two_style_cost', 'et1119c'), ('knob_nostyle_bestpermix', 'et1119k'), ('b1119_style_gated', None)):
    NEW = load(v) if v else {}; R = {r['id']: r for r in A.load(v).values()} if v else {}
    cnt = collections.Counter(); veto = {}; recs = []
    for p in J['per_pair']:
        x = p[arm]
        if x['is_default'] or not x['win']: continue
        a = None
        if p['id'] in NEW and list(NEW[p['id']]['win']) == list(x['win']): a = NEW[p['id']]
        elif p['id'] in PK and list(PK[p['id']]['win']) == list(x['win']): a = PK[p['id']]
        if a is None:
            cnt['unchecked' if not (v and p['id'] in R) else 'not_applied'] += 1
            if v and p['id'] in R: veto[p['id']] = True  # engine could not play the wanted window -> keep the default
            continue
        d = DEF.get(p['id'])
        if d is None: cnt['no_default_ref'] += 1; continue
        f, fd = fl(a), fl(d); cnt['checked'] += 1; rec = dict(id=p['id'], win=x['win'])
        for hc in ('HC_A', 'HC_B', 'HC_C'):
            cnt[f'pick_{hc}'] += f[hc]; cnt[f'def_{hc}'] += fd[hc]; n = f[hc] and not fd[hc]; cnt[f'new_{hc}'] += n; cnt[f'fixed_{hc}'] += (fd[hc] and not f[hc]); rec[f'new_{hc}'] = bool(n)
        veto[p['id']] = bool(rec['new_HC_A'] or rec['new_HC_B']); rec['flags'] = {k: f[k] for k in ('hole_score', 'hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump', 'med_lag')}
        if veto[p['id']]: recs.append(rec)
    D_ = [ec(p, dict(exit=p['dex'] if 'dex' in p else p['default']['exit'], cue=p['default']['cue'])) for p in J['per_pair']]
    M_ = [ec(p, p['default'] if veto.get(p['id']) else p[arm]) for p in J['per_pair']]
    S_ = [ec(p, p['b1119_style_gated']) for p in J['per_pair']]
    OUT[arm] = dict(counts=dict(cnt), vetoed=recs, n_veto=sum(veto.values()), after_veto=dict(mean=round(float(np.mean(M_)), 2), default=round(float(np.mean(D_)), 2),
                    vs_default=P.boot(g, D_, M_), vs_b1119_style_gated_raw=P.boot(g, S_, M_)))
    print(arm, json.dumps(OUT[arm]['counts']), 'veto', OUT[arm]['n_veto'], json.dumps(OUT[arm]['after_veto']))
json.dump(OUT, open(os.path.join(H, 'exittype_1119_hc.json'), 'w'), indent=1, default=str)
