#!/usr/bin/env python3
"""online_style.py policies re-counted with hardcheck v2 flags (hc2_cache/rows_<variant>.json); lists pairs that newly fail
vs default for online_rule (K=3 and K=all). Same choices as online_style.py. Writes online_style_hc2.json."""
import json, os, sys, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import policy as PO, online_style as OS
F = {v: json.load(open(os.path.join(H, 'hc2_cache', f'rows2_{v}.json'))) for v in ('default', 'on', 'gated')}
_load = PO.load_all
def load_v2(final):
    rs = _load(final)
    for r in rs:
        for k, v in (('D', 'default'), ('O', 'on'), ('G', 'gated')):
            x = dict(r[k]); x['hard_v1'] = x['hard']; x['hard'] = dict(F[v][r['id']]); r[k] = x
    return rs
PO.load_all = load_v2
out = {}
for K in (3, 0):
    rs = PO.load_all(False); H_ = OS.history(); style, prior = OS.make_style(H_, K)
    pick = {r['id']: ('O' if (len(prior(r)) >= 2 and style(r) > 0.5) else 'D') for r in rs}
    new = [dict(id=r['id'], dj=r['dj'], win=r['O']['win'], default_win=r['D']['win'], v2=r['O']['hard'], v1=r['O']['hard_v1'].get('hard_fail'))
           for r in rs if pick[r['id']] == 'O' and r['O']['hard']['hard_fail'] and not r['D']['hard']['hard_fail']]
    fixed = [r['id'] for r in rs if pick[r['id']] == 'O' and not r['O']['hard']['hard_fail'] and r['D']['hard']['hard_fail']]
    full = OS.run(K)
    out[f'K{K or "all"}'] = dict(hard_fail_v2={k: v['hard_fail'] for k, v in full['results'].items()}, online_rule_new_fails=new, online_rule_fixed=fixed)
json.dump(out, open(os.path.join(H, 'online_style_hc2.json'), 'w'), indent=1, default=bool)
print(json.dumps(out, indent=1, default=bool)[:6000])
