#!/usr/bin/env python3
"""2026-11-19 PLACE=safe evaluation on dev pairs with local audio (LODO plans from safeplace_1119.py plan).
Arms (same pairs): default; raw = the planner's rank-1 pick with no render check; final = rank-1 if it passes HC_A and HC_B, else
rank-2 if it passes, else the default. Fail-rate differences vs default with mix-grouped bootstrap 95% CIs. usage: safeplace_eval.py TAG"""
import json, os, sys, pickle, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import final_eval as FE, picker_1119 as P
T = sys.argv[1]; WK = os.path.join(H, 'safeplace_work'); L = json.load(open(os.path.join(WK, f'plan_{T}.json')))
def load(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'); return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
DEF = {}
for v in ([os.environ['THINDEF']] if os.environ.get('THINDEF') else []) + ['default', 'ndef1119']:  # THINDEF: thin-flag default renders override (2026-11-19)
    for k, a in load(v).items(): DEF.setdefault(k, a)
R1, R2 = load(f'sp1119{T}1'), load(f'sp1119{T}2'); R = {r['id']: r for r in P.rows_all()}
def ok(a, w): return a is not None and list(a['win']) == list(w)
def ec(p, w): return (abs((w[1] - w[4] + 1) - p['pro_out']) + abs((w[3] + 1) - p['pro_in'])) / 2
def offp(w): return ((w[1] - w[4]) % 16) not in (0, 15, 1)
def offs(r, w): e = w[1] - w[4] + 1; return min((abs(e - v) for v in P.bnd_a(r['sa'])), default=99) > 4
rows = []; cnt = collections.Counter()
for p in L:
    d = DEF[p['id']]; fd = FE.flags(d); rec = dict(id=p['id'], dj=p['dj'], mix=p['mix'], def_A=fd['HC_A'], def_B=fd['HC_B'], def_win=p['default_win'])
    raw = final = (fd, p['default_win'], 'default'); why = 'planner_kept_default'
    if not p['keep_default']:
        w1 = p['top'][0]['win']; a1 = R1.get(p['id'])
        if not ok(a1, w1): why = 'r1_missing_or_not_applied'; cnt[why] += 1
        else:
            f1 = FE.flags(a1); raw = (f1, w1, 'r1')
            if not (f1['HC_A'] or f1['HC_B']): final = raw; why = 'r1_pass'
            else:
                w2 = p['top'][1]['win'] if len(p['top']) > 1 else None; a2 = R2.get(p['id'])
                if w2 and ok(a2, w2):
                    f2 = FE.flags(a2)
                    if not (f2['HC_A'] or f2['HC_B']): final = (f2, w2, 'r2'); why = 'r2_pass'
                    else: why = 'both_fail_default'
                else: why = 'r1_fail_no_r2_default'
    cnt[why] += 1
    for nm, (f, w, src) in (('raw', raw), ('final', final)):
        rec[f'{nm}_A'] = f['HC_A']; rec[f'{nm}_B'] = f['HC_B']; rec[f'{nm}_src'] = src; rec[f'{nm}_win'] = w
        rec[f'{nm}_fired'] = [k for k in ('hole_v2', 'clash_v1', 'clash_v2', 'pump', 'halfbeat') if f[k]]
    rec['why'] = why; rows.append(rec)
g = [x['mix'] for x in rows]; out = dict(n=len(rows), n_mixes=len(set(g)), outcomes=dict(cnt))
for k in ('A', 'B'):
    D = [float(x[f'def_{k}']) for x in rows]
    out[f'default_HC_{k}'] = round(float(np.mean(D)), 3)
    for nm in ('raw', 'final'):
        V = [float(x[f'{nm}_{k}']) for x in rows]; out[f'{nm}_HC_{k}'] = round(float(np.mean(V)), 3); out[f'{nm}_minus_default_HC_{k}'] = P.boot(g, D, V)
D = [float(x['def_A'] or x['def_B']) for x in rows]
for nm in ('raw', 'final'):
    V = [float(x[f'{nm}_A'] or x[f'{nm}_B']) for x in rows]; out[f'{nm}_any'] = round(float(np.mean(V)), 3); out[f'{nm}_minus_default_any'] = P.boot(g, D, V)
out['default_any'] = round(float(np.mean(D)), 3)
for nm in ('def', 'raw', 'final'):
    W = [x[f'{nm}_win'] for x in rows]
    out[f'{nm}_off_phrase'] = round(float(np.mean([offp(w) for w in W])), 3); out[f'{nm}_off_section'] = round(float(np.mean([offs(R[x['id']], w) for x, w in zip(rows, W)])), 3)
    out[f'{nm}_pro_err'] = round(float(np.mean([ec(p, w) for p, w in zip(L, W)])), 2)
    out[f'{nm}_mid_share'] = round(float(np.mean([P.sa_na if False else (int(R[x['id']]['sa'].get('music_end') or R[x['id']]['sa']['n_bars']) - (w[1] - w[4] + 1) >= 32) for x, w in zip(rows, W)])), 3)
out['final_pro_err_minus_default'] = P.boot(g, [ec(p, x['def_win']) for p, x in zip(L, rows)], [ec(p, x['final_win']) for p, x in zip(L, rows)])
out['changed_final'] = int(sum(x['final_src'] != 'default' for x in rows))
fired = collections.Counter(k for x in rows if x['raw_src'] == 'r1' and (x['raw_A'] or x['raw_B']) for k in x['raw_fired']); out['raw_fired'] = dict(fired)
out['per_dj'] = {d: dict(n=sum(1 for x in rows if x['dj'] == d), def_any=int(sum((x['def_A'] or x['def_B']) for x in rows if x['dj'] == d)),
                     raw_any=int(sum((x['raw_A'] or x['raw_B']) for x in rows if x['dj'] == d)), final_any=int(sum((x['final_A'] or x['final_B']) for x in rows if x['dj'] == d)),
                     changed=int(sum(x['final_src'] != 'default' for x in rows if x['dj'] == d))) for d in sorted({x['dj'] for x in rows})}
out['pairs'] = rows
json.dump(out, open(os.path.join(H, f'safeplace_{T}_eval.json'), 'w'), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ('pairs',)}, default=str))
