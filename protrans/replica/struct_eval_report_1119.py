#!/usr/bin/env python3
"""2026-11-19 OUTRO_QC / SLOWDOWN / STRUCTB report. Dev: HC_A|HC_B fail rate of each arm's rendered engine default vs the base re-render on
the pairs whose engine windows change (others are identical by construction), paired, mix-grouped bootstrap CI (4000, seed 20261119),
leave-one-DJ-out range; "+ gated d": the arm's default unless it fails HC, then PLACE=safe d's final pick if that passes (safeplace_d_eval).
Cohort: held-out test/train per arm vs floor cb1119_base 34.07 / 32.40; "+ d" = d's score (sfdcoh1119) on pairs whose default render fails HC.
-> struct_eval_1119.json"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, H)
import final_eval as FE
rng = np.random.default_rng(20261119)
ch = json.load(open(os.path.join(H, 'struct_changed_1119.json'))); IDS = set(ch['QC']) | set(ch['SLOW']) | set(ch['QCS'])
def ck(v): return {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl'))} if os.path.exists(os.path.join(H, 'gate_ckpt', v + '.jsonl')) else {}
def fail(F, i): return bool(F[i]['HC_A'] or F[i]['HC_B']) if i in F else None
D = {p['id']: p for p in json.load(open(os.path.join(H, 'safeplace_d_eval.json')))['pairs']}
def ci(rows, vals):
    by = {}
    for r, v in zip(rows, vals): by.setdefault(r['mix'], []).append(v)
    if not by: return None
    G = [np.array(v, float) for v in by.values()]; bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(4000)]
    lo, hi = np.percentile(bs, [2.5, 97.5]); return dict(delta=round(float(np.mean(vals)), 3), ci=[round(float(lo), 3), round(float(hi), 3)])
FB = FE.arr('sbase1119'); CB = ck('sbase1119'); out = dict(changed=dict((k, len(v)) for k, v in ch.items()), ids=len(IDS), dev={}, cohort={})
for arm, v in (('QC', 'sqc1119'), ('SLOW', 'sslow1119'), ('QCS', 'sqcs1119')):
    FA = FE.arr(v); CA = ck(v); rows = []
    for i in sorted(IDS):
        if i not in CA or i not in CB or i not in FA or i not in FB: continue
        fb, fa = fail(FB, i), fail(FA, i); d = D.get(i)
        dpass = d is not None and not (d['final_A'] or d['final_B'])
        rows.append(dict(id=i, mix=CA[i]['mix'], dj=CA[i]['dj'], src=CA[i]['src'], base_win=CB[i]['win'], arm_win=CA[i]['win'], base_fail=fb, arm_fail=fa,
                         same=CB[i]['win'] == CA[i]['win'], base_gd=(fb and not dpass), arm_gd=(fa and not dpass)))
    if not rows: continue
    dv = [int(r['arm_fail']) - int(r['base_fail']) for r in rows]; dg = [int(r['arm_gd']) - int(r['base_gd']) for r in rows]
    djs = {r['dj'] for r in rows}
    out['dev'][arm] = dict(n=len(rows), n_window_changed=sum(not r['same'] for r in rows), base_fail=sum(r['base_fail'] for r in rows), arm_fail=sum(r['arm_fail'] for r in rows),
                           diff=ci(rows, dv), with_gated_d=dict(base=sum(r['base_gd'] for r in rows), arm=sum(r['arm_gd'] for r in rows), diff=ci(rows, dg)),
                           lodo_range=[round(min(np.mean([x for r, x in zip(rows, dv) if r['dj'] != j] or [0]) for j in djs), 3), round(max(np.mean([x for r, x in zip(rows, dv) if r['dj'] != j] or [0]) for j in djs), 3)],
                           rows=rows)
# cohort
def sc(tag):
    p = os.path.join(P, 'results', 'score_ckpt', tag + '.jsonl')
    return {json.loads(l)['id']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}
B = sc('cb1119_base'); Dc = sc('sfdcoh1119'); FN = FE.arr('ndef1119')
for arm, tag in (('base', 'cb1119_base'), ('QC', 'cs_qc_1119'), ('SLOW', 'cs_slow_1119'), ('QCS', 'cs_qcs_1119'), ('B0', 'cs_b0_1119'), ('B100', 'cs_b100_1119')):
    S = sc(tag)
    if len(S) < 33: out['cohort'][arm] = dict(missing=True, n=len(S)); continue
    res = {}
    for split in ('test', 'train'):
        ids = [i for i in S if S[i]['split'] == split]
        a = [S[i]['score']['score'] for i in ids]
        # + d: if this pair's default render fails HC (ndef1119 / this arm's eval_gate render when its window changed), use d's cohort score
        FA = FE.arr({'QC': 'sqc1119', 'SLOW': 'sslow1119', 'QCS': 'sqcs1119'}.get(arm, 'ndef1119'))
        ad = [Dc[i]['score']['score'] if (fail(FA, i) if i in FA else fail(FN, i)) and i in Dc else S[i]['score']['score'] for i in ids]
        res[split] = round(float(np.mean(a)), 2); res[split + '_with_d'] = round(float(np.mean(ad)), 2)
        res[split + '_vs_floor_pairs'] = sorted([(i, round(S[i]['score']['score'] - B[i]['score']['score'], 2)) for i in ids if i in B and abs(S[i]['score']['score'] - B[i]['score']['score']) > 0.5], key=lambda t: t[1])
    out['cohort'][arm] = res
json.dump(out, open(os.path.join(H, 'struct_eval_1119.json'), 'w'), indent=1, default=str)
print(json.dumps({k: ({a: ({kk: vv for kk, vv in x.items() if kk != 'rows'} if isinstance(x, dict) else x) for a, x in v.items()} if isinstance(v, dict) else v) for k, v in out.items()}, indent=1, default=str))
