#!/usr/bin/env python3
"""Train the style-gated picker on all 762 dev mixes and write a window map
for the official 33 protrans pairs (held out of that train set).

PICKER_STYLE_GATED loads this map at pick time. Does not write rules.json.
Pro labels are training targets only; they are not pick-time inputs.
"""
from __future__ import annotations
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
sys.path.insert(0, os.path.dirname(H))
import picker_1124 as P24
import picker_1119 as P
import picker_1119b as B
import run_admitted_tune as T

def main():
    P.W = P24.W
    P.SPENT_FRESH = P24.FRESH_ALL
    B.W = P24.W
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    pt = [r for r in rows if r['set'] == 'protrans']
    print(f'train dev={len(dev)} apply protrans={len(pt)}', flush=True)
    if len(pt) != 33:
        print('WARN unexpected protrans count', len(pt), flush=True)
    B.XM(dev, 'E', True); B.XM(pt, 'E', True)
    B.XM(dev, 'C', True); B.XM(pt, 'C', True)
    o = B.run_part(dev, pt, True)
    decisions = [B.decide(r, je, jc, X) for r, je, jc, X in zip(pt, o['E']['g'], o['C']['g'], o['X'])]
    recs = {r['id']: r for r in T.load_recs()}
    by_yt, by_id = {}, {}
    for r, d in zip(pt, decisions):
        rec = recs.get(r['id'])
        win = d.get('win')
        if win is None and d.get('is_default'):
            # abstain: no map entry (engine keeps its first pick)
            entry = dict(id=r['id'], abstain=True, exit=d['exit'], cue=d['cue'], X=d['X'])
        else:
            entry = dict(id=r['id'], win=win, exit=d.get('exit'), cue=d.get('cue'), X=d.get('X'), abstain=bool(d.get('is_default')))
        by_id[r['id']] = entry
        if rec:
            key = f"{rec['a']['yt']}|{rec['b']['yt']}"
            if win and not entry['abstain']:
                by_yt[key] = win
            entry['yt_key'] = key
    n_win = sum(1 for v in by_id.values() if v.get('win') and not v.get('abstain'))
    out = dict(written='2026-11-24',
               model='picker_1124 style-gated, trained on 762 dev, applied to official 33',
               train_n=len(dev), apply_n=len(pt), n_windows=n_win, n_abstain=len(pt) - n_win,
               by_yt=by_yt, by_id=by_id,
               do_not='write rules.json or treat this map as a promotion')
    dest = os.path.join(H, 'picker_style_gated_windows.json')
    json.dump(out, open(dest, 'w'), indent=2, default=str)
    print(f'wrote {dest} windows={n_win} abstain={len(pt)-n_win}', flush=True)

if __name__ == '__main__':
    main()
