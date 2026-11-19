#!/usr/bin/env python3
"""2026-11-19 day: re-measure the deckdrift cases on RAW decks: same bar map (full_map), but crossfader gain flat and the low/high EQ
lanes, drum swap and graph-cut removed, so the kick band is not muted by the bass swap during the overlap. Timing is identical
(the lanes are gains only). Per-bar offset of each deck vs its own solo template; overlap = the plan's transition window. -> deckdrift_raw_1119.json"""
import json, os, sys, copy, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckdrift_1119 as DD
def raw_decks(meta):
    os.chdir(D2.SRC2); import blend_diag as BD
    M = json.load(open(meta)); M2 = copy.deepcopy(M)
    for d in M2['decks'][:2]:
        d['auto'] = dict(gain=[[-1e6, 1.0], [1e6, 1.0]]); d.pop('dswap', None); d.pop('graphcut', None)
    t = M['trans'][0]; s0, A, B = BD.crop_decks(M2, 0); return int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0), A, B
def raw_measure(meta):
    s, e, A, B = raw_decks(meta); eA, eB = D1.kick_env(A), D1.kick_env(B); n = int(min(len(A), len(B)) // D1.BS)
    nA = int(np.max(np.nonzero(np.abs(A).sum(1) > 0)[0]) // D1.BS) if np.any(A) else 0; nB0 = int(np.min(np.nonzero(np.abs(B).sum(1) > 0)[0]) // D1.BS + 1) if np.any(B) else n
    ov = list(range(max(0, s), min(n, e))); soA = list(range(0, max(0, s))); soB = list(range(min(n, e), n))
    tA, tB = D1.fold_profile(eA, soA), D1.fold_profile(eB, soB)
    dA, rA = D1.xlag(tA, D1.fold_profile(eA, ov)); dB, rB = D1.xlag(tB, D1.fold_profile(eB, ov))
    return dict(s=s, e=e, eA=eA, eB=eB, ov=ov, soA=soA, soB=soB, tA=tA, tB=tB, drift=dB - dA, dA=dA, dB=dB, r=min(rA, rB))
if __name__ == '__main__':
    res = json.load(open(os.path.join(H, 'deckdrift_1119.json'))); out = []; G = {}
    for c in res['cases']:
        v, pid = c['key'].split(':', 1)
        if v not in G: G[v] = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl'))}
        m = raw_measure(G[v][pid]['meta']); ovs = set(m['ov'])
        pA = DD.per_bar(m['eA'], m['soA'] + m['ov'], m['tA']); pB = DD.per_bar(m['eB'], m['ov'] + m['soB'], m['tB'])
        rec = dict(key=c['key'], group=c['group'], eq_drift=c['drift'], raw_drift=round(m['drift'], 1), raw_dA=round(m['dA'], 1), raw_dB=round(m['dB'], 1), raw_r=round(m['r'], 2),
                   A_ov=DD.trend([p for p in pA if p[0] in ovs]), B_ov=DD.trend([p for p in pB if p[0] in ovs]), A_solo=DD.trend([p for p in pA if p[0] not in ovs]), B_solo=DD.trend([p for p in pB if p[0] not in ovs]),
                   A_bars=[(int(a), None if not np.isfinite(b) else round(b, 1), round(r, 2)) for a, b, r in pA], B_bars=[(int(a), None if not np.isfinite(b) else round(b, 1), round(r, 2)) for a, b, r in pB])
        out.append(rec); print(rec['group'], rec['key'], 'eq', rec['eq_drift'], 'raw', rec['raw_drift'], 'r', rec['raw_r'], 'A_ov', rec['A_ov'], 'B_ov', rec['B_ov'], flush=True)
    json.dump(out, open(os.path.join(H, 'deckdrift_raw_1119.json'), 'w'), indent=1, default=float)
