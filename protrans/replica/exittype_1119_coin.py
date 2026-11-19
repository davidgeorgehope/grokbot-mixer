#!/usr/bin/env python3
"""2026-11-19 wrap-up: EXITTYPE=structcoin policy (diagnostic, behind a flag; never in rules.json). Exit type is a seeded coin flip,
weighted by what the outgoing track's structure supports; the bar inside the type comes from picker_1119b's style-free exit ranker
(LODO picks from exittype_1119_cv_r5.json: knob_nostyle_mid / knob_nostyle_late). Scored on audible faults: hard checks on
already-rendered windows (pick1119, et1119c, et1119k) vs the rendered default, plus 'odd spot' checks (exit not within 4 bars of a
section boundary or 16-bar phrase; outgoing/incoming vocal overlap in the window from st per-bar voc). Pro bar error is reported
for reference only. Dev only."""
import json, os, sys, pickle, hashlib, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1119 as P, final_eval as FE, exittype_1119 as T
J = json.load(open(os.path.join(H, 'exittype_1119_cv_r5.json'))); R = {r['id']: r for r in P.rows_all()}
def load(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'); return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
DEF = {}
for v in ('default', 'ndef1119'):
    for k, a in load(v).items(): DEF.setdefault(k, a)
REN = collections.defaultdict(dict)
for v in ('pick1119', 'et1119c', 'et1119k'):
    for k, a in load(v).items(): REN[k][tuple(a['win'])] = a
fm = {}
for l in open(os.path.join(H, 'nightly_1119_work', 'accepted_snapshot.jsonl')):
    a = json.loads(l); f = json.load(open(os.path.join(os.path.dirname(H), 'corpus_v2', 'features', a['id'] + '.json'))); fm[a['id']] = (f['track_a']['yt'], f['track_b']['yt'])
def p_struct(r):
    """structure prior for a mid exit: needs a drop-1 end with >= 48 bars left; a breakdown after it supports mid; a long outro (>= 32) supports late"""
    sa = r['sa']; na = T.NA(sa); dr = sa.get('drops') or []
    if not dr or na - dr[0][1] < 48: return 0.0
    p = 0.5
    if sa.get('breakdown') and sa['breakdown'] >= dr[0][1] - 4: p += 0.15
    if na - (sa.get('outro_start') or na) >= 32: p -= 0.15
    return p
def coin(i, p): return int(hashlib.md5(('structcoin1119|' + i).encode()).hexdigest()[:8], 16) / 0xffffffff < p
def odd(r, x, d):
    if x['is_default'] or not x['win']: x = dict(exit=d['exit'], cue=d['cue'], X=d['X'], win=['n', int(round((d['exit'] + d['X'] - 1) / 8) * 8), None, int(d['cue'] - 1), int(d['X'])])
    e = x['exit']; b = P.bnd_a(r['sa']); sec = min((abs(e - v) for v in b), default=99) <= 4; phr = abs(((e - 1) % 16) - 0) <= 1 or abs(((e - 1) % 16) - 16) <= 1
    ya, yb = fm[r['id']]; A = T.st(ya); B = T.st(yb); voc = None
    if A and B and 'voc' in A and 'voc' in B:
        w = x['win']; X = int(w[4]); ea = int(w[1]); ib = int(w[3])
        va = np.array(A['voc'][max(0, ea - X):ea], float); vb = np.array(B['voc'][ib:ib + X], float); n = min(len(va), len(vb))
        if n: voc = float(np.mean((va[:n] > -25) & (vb[:n] > -25)))  # both decks vocal-active (dB > -25) share of window bars
    return dict(off_section=not sec, off_phrase=not phr, voc_overlap=voc)
def hc(i, x):
    if x['is_default'] or not x['win']: a = DEF.get(i)
    else: a = REN.get(i, {}).get(tuple(x['win']))
    return FE.flags(a) if a is not None else None
arms = {'default': [], 'structcoin': [], 'fixed_mid': [], 'fixed_late': [], 'b1119_style_gated': []}
for p in J['per_pair']:
    r = R[p['id']]; ps = p_struct(r)
    arms['structcoin'].append(p['knob_nostyle_mid'] if coin(p['id'], ps) else p['knob_nostyle_late'])
    arms['fixed_mid'].append(p['knob_nostyle_mid']); arms['fixed_late'].append(p['knob_nostyle_late']); arms['default'].append(dict(p['default'], is_default=True, win=None))
    arms['b1119_style_gated'].append(p['b1119_style_gated'])
g = [p['mix'] for p in J['per_pair']]; out = {}
def ec(p, x): return (abs(x['exit'] - p['pro_out']) + abs(x['cue'] - p['pro_in'])) / 2
D0 = [ec(p, x) for p, x in zip(J['per_pair'], arms['default'])]
for n, L in arms.items():
    E = [ec(p, x) for p, x in zip(J['per_pair'], L)]; O = [odd(R[p['id']], x, p['default']) for p, x in zip(J['per_pair'], L)]
    F = [(hc(p['id'], x), hc(p['id'], d)) for p, x, d in zip(J['per_pair'], L, arms['default'])]; both = [(a, b) for a, b in F if a is not None and b is not None]
    vo = [o['voc_overlap'] for o in O if o['voc_overlap'] is not None]
    out[n] = dict(ec=round(float(np.mean(E)), 2), d_vs_default=P.boot(g, D0, E) if n != 'default' else None,
                  chose_mid=round(float(np.mean([not x.get('is_default') and x.get('win') and T.NA(R[p['id']]['sa']) - x['exit'] >= 32 for p, x in zip(J['per_pair'], L)])), 3),
                  off_section=round(float(np.mean([o['off_section'] for o in O])), 3), off_phrase=round(float(np.mean([o['off_phrase'] for o in O])), 3),
                  voc_overlap_mean=round(float(np.mean(vo)), 3) if vo else None, voc_overlap_ge25=round(float(np.mean([v >= 0.25 for v in vo])), 3) if vo else None, n_voc=len(vo),
                  hc_checked=len(both), **{f'{k}_pick': int(sum(a[k] for a, b in both)) for k in ('HC_A', 'HC_B')}, **{f'{k}_default_same': int(sum(b[k] for a, b in both)) for k in ('HC_A', 'HC_B')},
                  fired={k: int(sum(a[k] and not b['HC_A'] for a, b in both)) for k in ('hole_v2', 'clash_v1', 'clash_v2', 'pump', 'halfbeat')})
    print(n, json.dumps(out[n]))
json.dump(out, open(os.path.join(H, 'exittype_1119_coin.json'), 'w'), indent=1, default=str)
