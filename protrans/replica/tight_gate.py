#!/usr/bin/env python3
"""Tightened confident-breakdown gate, chosen by nested leave-one-DJ-out CV on DEV only (fresh + locked holdout untouched for
selection). Grid: min breakdown dip (dB), min breakdown length (bars), min breakdown position (fraction of the outgoing).
Inner objective: mean exit+cue bar error vs pro, subject to hard checks non-inferior (new hard-fail pairs <= pairs fixed);
if no setting qualifies the gate abstains everywhere (= default). Writes replica/tight_gate.json."""
import json, os, sys, itertools, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import policy as PO, analyze as A
GRID = list(itertools.product((6, 9, 12, 15, 18), (16, 24, 32), (0.0, 0.3, 0.4, 0.5)))

def passes(r, p):
    f = r['f']; dip, L, pos = p
    return bool(f['gate']) and f['a_dip'] >= dip and f['a_bd_len'] >= L and f['a_bd_pos'] >= pos

def pick(rs, p): return [r['O'] if passes(r, p) else r['D'] for r in rs]

def obj(rs, p):
    ch = pick(rs, p); e = np.mean([A.metric(x, 'exit_cue') for x in ch])
    new = sum(1 for x, r in zip(ch, rs) if x['hard']['hard_fail'] and not r['D']['hard']['hard_fail'])
    fixed = sum(1 for x, r in zip(ch, rs) if not x['hard']['hard_fail'] and r['D']['hard']['hard_fail'])
    return e, new, fixed

def select(rs):
    best = None
    for p in GRID:
        e, new, fixed = obj(rs, p)
        if new > fixed: continue
        if best is None or e < best[0]: best = (e, p)
    return best[1] if best else None

def summarize(rs, ch, ref):
    ids = [r['id'] for r in rs]; groups = {r['id']: r['mix'] for r in rs}
    R = {r['id']: x for r, x in zip(rs, ref)}; B = {r['id']: x for r, x in zip(rs, ch)}
    s = dict(n=len(rs), used=sum(1 for x, r in zip(ch, rs) if x is r['O']), hard_fail=sum(x['hard']['hard_fail'] for x in ch),
             new_fail=sum(1 for x, r in zip(ch, rs) if x['hard']['hard_fail'] and not r['D']['hard']['hard_fail']),
             fixed=sum(1 for x, r in zip(ch, rs) if not x['hard']['hard_fail'] and r['D']['hard']['hard_fail']),
             exit_cue_mean=round(float(np.mean([A.metric(x, 'exit_cue') for x in ch])), 1),
             exit_median=round(float(np.median([x['err']['exit'] for x in ch])), 1))
    for t in (4, 8, 16): s[f'exit_hit{t}'] = round(float(np.mean([x['err']['exit'] <= t for x in ch])), 3)
    s['delta_exit_cue'] = A.boot_delta(ids, R, B, 'exit_cue', groups); s['delta_exit'] = A.boot_delta(ids, R, B, 'exit', groups)
    s['delta_exit_hit16'] = PO.hit_delta(ids, R, B, groups, 16)
    return s

if __name__ == '__main__':
    rs = PO.load_all(False); djs = sorted({r['dj'] for r in rs}); ch = {}; chosen = {}
    for d in djs:
        tr = [r for r in rs if r['dj'] != d]; p = select(tr); chosen[d] = p
        for r in rs:
            if r['dj'] == d: ch[r['id']] = (r['O'] if (p and passes(r, p)) else r['D'])
    order = rs; out = dict(grid=len(GRID), outer_folds={d: p for d, p in chosen.items()},
                           dev_outer=summarize(order, [ch[r['id']] for r in order], [r['D'] for r in order]),
                           dev_gate_apriori=summarize(order, [r['G'] for r in order], [r['D'] for r in order]))
    pall = select(rs); out['final_params_all_dev'] = pall
    json.dump(out, open(os.path.join(H, 'tight_gate.json'), 'w'), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))
