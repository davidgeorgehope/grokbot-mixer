#!/usr/bin/env python3
"""2026-11-19 dev-wide "pro pick vs ours" pattern scan (structure only, no style matching). Every dev transition: the pro's window vs our
engine default (dex/dcue/dX) in each track's own bars. Per window: where the blend starts in the outgoing (intro/drop/breakdown/outro), where
the incoming enters, overlap length, whether the outgoing's last drop is cut / partly overlapped / fully played, where the incoming's next drop
lands vs the blend end, whether the blend reaches the outgoing's final 16-bar block, and (profiled tracks) whether it touches an outgoing
slowdown. Pro minus default with mix-grouped bootstrap CIs (4000, seed 20261119). -> pattern_scan_1119.json"""
import os, sys, json, collections
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import safeplace_1119 as S
ST = '/workspace/mixes/src2/st/'; rng = np.random.default_rng(20261119)
def kind(sec, bar):
    dr = sec.get('drops') or []
    if not dr or bar < dr[0][0]: return 'intro'
    for x, y in dr:
        if x <= bar < y: return 'drop'
    return 'outro' if bar >= dr[-1][1] else 'breakdown'
def slows(yt):
    p = ST + yt + '.slowdown.json'
    return [tuple(x) for x in json.load(open(p)).get('sections', [])] if os.path.exists(p) else None
def feats(sa, sb, a0, a1, b0, b1, sl):
    dr = sa.get('drops') or [[0, 0]]; lde = dr[-1][1]; es = (sa['music_end'] // 8) * 8
    nd = [x for x, y in (sb.get('drops') or []) if x >= b0 - 0.5]
    f = dict(ov=a1 - a0, A_start=kind(sa, a0), B_start=kind(sb, b0), final_block=int(a1 > es - 16),
             last_drop_cut=int(a1 <= lde), last_drop_overlapped=int(a0 < lde < a1 or (a0 < lde and a1 > lde)), last_drop_full=int(a0 >= lde - 0.5),
             B_drop_in_blend=int(bool(nd) and nd[0] < b1 - 0.5), B_drop_at_end=int(bool(nd) and abs(nd[0] - b1) <= 2),
             B_drop_vs_end=(nd[0] - b1) if nd else None, A_end_vs_music_end=a1 - sa['music_end'])
    if sl is not None: f['touch_A_slow'] = int(any(x < a1 and a0 < y for x, y in sl)); f['start_in_A_slow'] = int(any(x <= a0 < y for x, y in sl))
    return f
rows = []
for r in S.dev_rows():
    if r.get('pro_out') is None or not isinstance(r.get('sa'), dict) or not isinstance(r.get('sb'), dict): continue
    po = int(round(float(r['pro_out']))) - 1; pi = int(round(float(r['pro_in']))) - 1; ov = int(round(float(r.get('pro_ov') or 16)))
    dw = S.default_win(r); sl = slows(r['ya']) if r.get('ya') else None
    rows.append(dict(id=r['id'], mix=r['mix'], dj=r['dj'], pro=feats(r['sa'], r['sb'], po, po + ov, pi, pi + ov, sl),
                     default=feats(r['sa'], r['sb'], dw[1] - dw[4], dw[1], dw[3], dw[3] + dw[4], sl)))
def ci(vals, mixes):
    by = collections.defaultdict(list)
    for v, m in zip(vals, mixes): by[m].append(v)
    G = [np.array(v, float) for v in by.values()]; bs = [np.concatenate([G[j] for j in rng.integers(0, len(G), len(G))]).mean() for _ in range(4000)]
    lo, hi = np.percentile(bs, [2.5, 97.5]); return [round(float(lo), 3), round(float(hi), 3)]
res = dict(n=len(rows), n_mixes=len({r['mix'] for r in rows}), n_djs=len({r['dj'] for r in rows}), metrics={})
num = ['ov', 'final_block', 'last_drop_cut', 'last_drop_overlapped', 'last_drop_full', 'B_drop_in_blend', 'B_drop_at_end', 'B_drop_vs_end', 'A_end_vs_music_end', 'touch_A_slow', 'start_in_A_slow']
for k in num:
    sel = [r for r in rows if r['pro'].get(k) is not None and r['default'].get(k) is not None]
    if not sel: continue
    p = [r['pro'][k] for r in sel]; d = [r['default'][k] for r in sel]; m = [r['mix'] for r in sel]
    diff = [a - b for a, b in zip(p, d)]; c = ci(diff, m)
    res['metrics'][k] = dict(n=len(sel), pro=round(float(np.mean(p)), 3), default=round(float(np.mean(d)), 3), pro_minus_default=round(float(np.mean(diff)), 3), ci=c, clear=bool(c[0] > 0 or c[1] < 0))
for k in ('A_start', 'B_start'):
    res['metrics'][k] = {}
    for lab in ('intro', 'drop', 'breakdown', 'outro'):
        p = [int(r['pro'][k] == lab) for r in rows]; d = [int(r['default'][k] == lab) for r in rows]; c = ci([a - b for a, b in zip(p, d)], [r['mix'] for r in rows])
        res['metrics'][k][lab] = dict(pro=round(float(np.mean(p)), 3), default=round(float(np.mean(d)), 3), ci=c, clear=bool(c[0] > 0 or c[1] < 0))
# leave-one-DJ-out: does each clear difference keep its sign with any one DJ removed?
for k, v in res['metrics'].items():
    if isinstance(v, dict) and 'pro_minus_default' in v and v['clear']:
        sg = np.sign(v['pro_minus_default'])
        v['lodo_same_sign'] = all(np.sign(np.mean([r['pro'][k] - r['default'][k] for r in rows if r['dj'] != dj and r['pro'].get(k) is not None and r['default'].get(k) is not None])) == sg for dj in {r['dj'] for r in rows})
json.dump(dict(res=res, rows=rows), open(os.path.join(H, 'pattern_scan_1119.json'), 'w'), indent=1, default=str)
print(json.dumps(res, indent=1))
