#!/usr/bin/env python3
"""DROPCAND (drop-exit / drop-cue) dev evaluation, same protocol as policy.py: DEV 91 pairs, grouped bootstrap by mix (4000,
seed 20261118), tolerance hits, acceptable-set hits, hard fails (v1 and the chosen v2 = hc2_cache/rows2_*). Arms: default (D),
gated (G), REPLICA=1 (O), drop-exit (X), drop-cue (C). Plus a leave-one-DJ-out selector: per fold, the arm with the lowest
TRAIN mean exit+cue error among arms whose TRAIN v2 hard-fail rate is within 5 points of default's (margin set a priori).
--fresh scores KushSessions #303 (kush_* checkpoints) once with the arms and the selector fit on all DEV."""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import policy as PO, analyze as A
ARMS = dict(D='default', G='gated', O='on', X='dropx', C='dropc')

def v2flags(v):
    p = os.path.join(H, 'hc2_cache', f'rows2_{v}.json'); return json.load(open(p)) if os.path.exists(p) else {}

def attach(rs, pref=''):
    for k, v in ARMS.items():
        rows = A.load(pref + v) if pref else A.load(v); F = v2flags(pref + v)
        for r in rs:
            x = rows.get(r['id'])
            if x is None or x.get('error'): r[k] = None; continue
            x = dict(x); x['hard_v1'] = x['hard']
            if r['id'] in F: x['hard'] = dict(F[r['id']])
            else: x['hard'] = dict(x['hard'], v2_missing=True)
            r[k] = x
    return [r for r in rs if all(r.get(k) for k in ARMS)]

def tr_err(tr, k): return float(np.mean([A.metric(r[k], 'exit_cue') for r in tr]))
def tr_hf(tr, k): return float(np.mean([r[k]['hard']['hard_fail'] for r in tr]))

def select(tr):
    base = tr_hf(tr, 'D'); ok = [k for k in ARMS if tr_hf(tr, k) <= base + 0.05]
    return min(ok, key=lambda k: tr_err(tr, k))

def report(order, chosen):
    res = PO.evaluate(order, chosen)
    for name, rows in chosen.items():
        res[name]['hard_fail_v1'] = sum(1 for x in rows if x['hard_v1']['hard_fail'])
        res[name]['v2_missing'] = sum(1 for x in rows if x['hard'].get('v2_missing'))
    return res

def run_dev():
    rs = attach(PO.load_all(False)); chosen = collections.defaultdict(list); order = []; picks = {}
    for d in sorted({r['dj'] for r in rs}):
        tr = [r for r in rs if r['dj'] != d]; te = [r for r in rs if r['dj'] == d]; k = select(tr); picks[d] = k
        for a in ARMS: chosen[ARMS[a]] += [r[a] for r in te]
        chosen['lodo_select'] += [r[k] for r in te]; order += te
    return dict(n=len(rs), fold_picks=picks, results=report(order, chosen))

if __name__ == '__main__':
    out = dict(dev=run_dev())
    json.dump(out, open(os.path.join(H, 'dropcand_dev.json'), 'w'), indent=1, default=str)
    for n, s in out['dev']['results'].items():
        d = s.get('delta_vs_default', {})
        print(n, 'exit_cue', s['exit_cue_mean'], 'd', d.get('exit_cue'), 'exit', d.get('exit', {}).get('delta') if d else None, 'cue', d.get('cue', {}).get('delta') if d else None,
              'hit16', s['exit_hit16'], 'cue16', s['cue_hit16'], 'hardv2', s['hard_fail'], 'hardv1', s['hard_fail_v1'], 'v2miss', s['v2_missing'])
    print(out['dev']['fold_picks'])
