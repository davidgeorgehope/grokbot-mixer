#!/usr/bin/env python3
"""Compare the n1126 live RIDEGATE render (n1126_ridegate_live) to the map-based ridegate render.
Uses official v1 scores from the score checkpoint and official hardcheck results. Does not write rules.json.
usage: compare_ridegate_live_1126.py  -> writes nightly_1126_work/ridegate_live_vs_map_render.json; exit 0 iff match."""
from __future__ import annotations
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H)
sys.path.insert(0, H); sys.path.insert(0, P0)
import run_admitted_tune as T
W = os.path.join(H, 'nightly_1126_work')

def _score(row):
    sc = (row or {}).get('score')
    if isinstance(sc, dict):
        return sc.get('score')
    return sc

def _win(row):
    return list(((row or {}).get('pick') or {}).get('win') or [])

def _fam(row):
    return ((row or {}).get('pick') or {}).get('fam')

def main():
    live = T.load_ckpt('n1126_ridegate_live')
    mapped = T.load_ckpt('n1126_ridegate')
    hc_live = json.load(open(os.path.join(W, 'hc_n1126_ridegate_live.json')))
    hc_map = json.load(open(os.path.join(W, 'hc_n1126_ridegate.json')))
    mp = json.load(open(os.path.join(W, 'map_ridegate.json')))
    moved = sorted(k for k, v in mp['by_id'].items() if v.get('win') and not v.get('abstain'))
    rows = []
    n_ok = 0
    for i in moved:
        a, b = live.get(i), mapped.get(i)
        ha, hb = hc_live.get(i) or {}, hc_map.get(i) or {}
        reasons = []
        if not a: reasons.append('live_missing')
        if not b: reasons.append('map_missing')
        if a and a.get('error'): reasons.append(f"live_error={a.get('error')}")
        if b and b.get('error'): reasons.append(f"map_error={b.get('error')}")
        if a and b and not a.get('error') and not b.get('error'):
            if _win(a) != _win(b):
                reasons.append(f"win live={_win(a)} map={_win(b)}")
            sa, sb = _score(a), _score(b)
            if sa is None or sb is None or abs(float(sa) - float(sb)) > 1e-6:
                reasons.append(f"v1 live={sa} map={sb}")
            for k in ('hard_fail', 'beat_clash', 'bass_hole', 'pumping'):
                if bool(ha.get(k)) != bool(hb.get(k)):
                    reasons.append(f"{k} live={ha.get(k)} map={hb.get(k)}")
            if ha.get('error') or hb.get('error'):
                reasons.append(f"hc_error live={ha.get('error')} map={hb.get('error')}")
        ok = not reasons
        n_ok += int(ok)
        rows.append(dict(id=i, ok=ok, why=('; '.join(reasons) or None),
                         live=dict(fam=_fam(a) if a else None, win=_win(a) if a else None, v1=_score(a) if a else None,
                                   hard_fail=ha.get('hard_fail'), beat_clash=ha.get('beat_clash'),
                                   bass_hole=ha.get('bass_hole'), pumping=ha.get('pumping')),
                         mapped=dict(fam=_fam(b) if b else None, win=_win(b) if b else None, v1=_score(b) if b else None,
                                     hard_fail=hb.get('hard_fail'), beat_clash=hb.get('beat_clash'),
                                     bass_hole=hb.get('bass_hole'), pumping=hb.get('pumping'))))
    out = dict(n=len(moved), agree=n_ok, rate=round(n_ok / len(moved), 4) if moved else None,
               match=n_ok == len(moved) and len(moved) == 25,
               disagree=[r for r in rows if not r['ok']])
    dest = os.path.join(W, 'ridegate_live_vs_map_render.json')
    json.dump(out, open(dest, 'w'), indent=1, default=str)
    print('RENDER_COMPARE', json.dumps({k: out[k] for k in ('n', 'agree', 'rate', 'match')}),
          'disagree', len(out['disagree']), flush=True)
    for r in out['disagree'][:20]:
        print('  DIS', r['id'], r['why'], flush=True)
    return 0 if out['match'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
