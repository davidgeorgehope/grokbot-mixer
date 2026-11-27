"""Listener preference labels for the learned picker (2026-11-27).

A listener verdict that prefers OUR rendered placement over the pro's becomes a labeled
training row: same built features, but exit/cue relevance labels and the ride label are
computed against the preferred placement instead of the pro's. No placement rule, no
per-pair pin at render time: the pair only enters training, like any pro row.

Data: listener_prefs.jsonl (one JSON per verdict). Used only when a pack is trained with
prefs=True (train_pack_with_prefs); the default pack is untouched.
"""
from __future__ import annotations
import copy, json, os, sys
import numpy as np
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
PREFS = os.path.join(H, 'listener_prefs.jsonl')


def load():
    if not os.path.exists(PREFS):
        return []
    return [json.loads(l) for l in open(PREFS) if l.strip()]


def pref_rows(built_by_id, prefs=None):
    import picker_1119 as P, picker_1119b as B
    out = []
    for p in (prefs if prefs is not None else load()):
        if p.get('preferred') != 'ours':
            continue
        r0 = built_by_id.get(p['id'])
        if r0 is None:
            continue
        r = {k: v for k, v in r0.items() if not k.startswith('X')}
        r = copy.deepcopy(r)
        r['id'] = p['id'] + '#pref'
        r['pro_out'], r['pro_in'], r['pro_ov'] = float(p['exit']), float(p['cue']), float(p['X'])
        r['Erel'] = np.array([B.rel(P.acc_err(c['v'], r['pro_out'], P.bnd_a(r['sa']))) for c in r['E']])
        r['Crel'] = np.array([B.rel(P.acc_err(c['v'], r['pro_in'], P.bnd_b(r['sb']))) for c in r['C']])
        r['set'] = 'pref'
        out.append(r)
    return out
