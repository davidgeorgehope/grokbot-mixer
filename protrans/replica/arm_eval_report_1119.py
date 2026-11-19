#!/usr/bin/env python3
"""2026-11-19 generic flag-arm report (OUTRO_QC / SLOWDOWN / STRUCTB / EXITPOS). usage:
  arm_eval_report_1119.py OUT.json CHANGED.json BASEVAR ARM:gatevariant:cohorttag [...]   (gatevariant '-' = held-out only)
Dev (pairs whose engine windows change under that arm; the rest are identical by construction): HC_A|HC_B fail of the arm's rendered default
vs the base re-render, paired, mix-grouped bootstrap CI (4000, seed 20261119), leave-one-DJ-out range; "+ gated d" = arm default unless it
fails HC, then PLACE=safe d's final pick if that passes. Track play: outgoing bars left unplayed after it is gone (music end - exit) and
incoming bars skipped at entry, base vs arm on the same pairs. Cohort: held-out test/train vs floor cb1119_base 34.07 / 32.40; "+ d" = d's
cohort score (sfdcoh1119) on pairs whose default render fails HC."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, H)
import final_eval as FE
rng = np.random.default_rng(20261119); ST = '/workspace/mixes/src2/st/'
OUT, CH, BASEV = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]; ARMS = [a.split(':') for a in sys.argv[4:]]
def ck(v):
    p = os.path.join(H, 'gate_ckpt', v + '.jsonl'); return {json.loads(l)['id']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}
def fail(F, i): return bool(F[i]['HC_A'] or F[i]['HC_B']) if i in F else None
def sec(yt):
    p = ST + yt + '.sections.json'; return json.load(open(p)) if os.path.exists(p) else None
D = {p['id']: p for p in json.load(open(os.path.join(H, 'safeplace_d_eval.json')))['pairs']}
import eval_gate as EG
AB = {p['id']: (p['a'], p['b']) for p in EG.pairs()}
def play(i, w):
    a, b = AB.get(i, (None, None)); sa = sec(a) if a else None
    if not sa or not w: return None, None
    return sa['music_end'] - w[1], w[3]
def ci(rows, vals):
    by = {}
    for r, v in zip(rows, vals): by.setdefault(r['mix'], []).append(v)
    if not by: return None
    G = [np.array(v, float) for v in by.values()]; bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(4000)]
    lo, hi = np.percentile(bs, [2.5, 97.5]); return dict(delta=round(float(np.mean(vals)), 3), ci=[round(float(lo), 3), round(float(hi), 3)])
FB, CB = FE.arr(BASEV), ck(BASEV); out = dict(changed={k: len(v) for k, v in CH.items()}, dev={}, cohort={})
def sc(tag):
    p = os.path.join(P, 'results', 'score_ckpt', tag + '.jsonl'); return {json.loads(l)['id']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}
B = sc('cb1119_base'); Dc = sc('sfdcoh1119'); FN = FE.arr('ndef1119')
for arm, gv, ctag in [('base', '-', 'cb1119_base')] + [tuple(a) for a in ARMS]:
    if gv != '-' and arm in CH:
        FA, CA = FE.arr(gv), ck(gv); rows = []
        for i in sorted(CH[arm]):
            if not all(i in X for X in (CA, CB, FA, FB)): continue
            fb, fa = fail(FB, i), fail(FA, i); d = D.get(i); dpass = d is not None and not (d['final_A'] or d['final_B'])
            lb, sb_ = play(i, CB[i]['win']); la, sa_ = play(i, CA[i]['win'])
            rows.append(dict(id=i, mix=CA[i]['mix'], dj=CA[i]['dj'], src=CA[i]['src'], base_win=CB[i]['win'], arm_win=CA[i]['win'], base_fail=fb, arm_fail=fa,
                             base_gd=bool(fb and not dpass), arm_gd=bool(fa and not dpass), base_left=lb, arm_left=la, base_skip=sb_, arm_skip=sa_))
        if rows:
            dv = [int(r['arm_fail']) - int(r['base_fail']) for r in rows]; dg = [int(r['arm_gd']) - int(r['base_gd']) for r in rows]; djs = {r['dj'] for r in rows}
            pl = [r for r in rows if r['base_left'] is not None and r['arm_left'] is not None]
            out['dev'][arm] = dict(n=len(rows), n_window_changed=sum(r['base_win'] != r['arm_win'] for r in rows), base_fail=sum(r['base_fail'] for r in rows), arm_fail=sum(r['arm_fail'] for r in rows),
                                   diff=ci(rows, dv), with_gated_d=dict(base=sum(r['base_gd'] for r in rows), arm=sum(r['arm_gd'] for r in rows), diff=ci(rows, dg)),
                                   lodo_range=[round(min(np.mean([x for r, x in zip(rows, dv) if r['dj'] != j] or [0]) for j in djs), 3), round(max(np.mean([x for r, x in zip(rows, dv) if r['dj'] != j] or [0]) for j in djs), 3)],
                                   play=dict(n=len(pl), out_bars_left_base_median=float(np.median([r['base_left'] for r in pl])) if pl else None, out_bars_left_arm_median=float(np.median([r['arm_left'] for r in pl])) if pl else None,
                                             out_bars_left_diff=ci(pl, [r['arm_left'] - r['base_left'] for r in pl]), in_skip_diff=ci(pl, [r['arm_skip'] - r['base_skip'] for r in pl]),
                                             cut_16plus_more=sum(r['arm_left'] - r['base_left'] >= 16 for r in pl)), rows=rows)
    S = sc(ctag)
    if len(S) < 33: out['cohort'][arm] = dict(missing=True, n=len(S)); continue
    res = {}; FA = FE.arr(gv) if gv != '-' else {}
    for split in ('test', 'train'):
        ids = [i for i in S if S[i]['split'] == split]
        res[split] = round(float(np.mean([S[i]['score']['score'] for i in ids])), 2)
        res[split + '_with_d'] = round(float(np.mean([Dc[i]['score']['score'] if (fail(FA, i) if i in FA else fail(FN, i)) and i in Dc else S[i]['score']['score'] for i in ids])), 2)
        res[split + '_pairs_vs_floor'] = sorted([(i, round(S[i]['score']['score'] - B[i]['score']['score'], 2)) for i in ids if i in B and abs(S[i]['score']['score'] - B[i]['score']['score']) > 0.5], key=lambda t: t[1])
    lefts = [(play(i, B[i]['pick']['win'])[0], play(i, S[i]['pick']['win'])[0]) for i in S if i in B]
    lefts = [x for x in lefts if None not in x]
    if lefts: res['out_bars_left_median_floor_vs_arm'] = [float(np.median([x[0] for x in lefts])), float(np.median([x[1] for x in lefts]))]
    out['cohort'][arm] = res
json.dump(out, open(OUT, 'w'), indent=1, default=str)
print(json.dumps({k: ({a: {kk: vv for kk, vv in x.items() if kk != 'rows'} for a, x in v.items()} if isinstance(v, dict) and k != 'changed' else v) for k, v in out.items()}, indent=1, default=str))
