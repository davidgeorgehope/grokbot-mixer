#!/usr/bin/env python3
"""2026-11-19 nightly: hard checks on rendered picker windows vs the rendered default, then the veto (hard checks only veto:
a pick that fails while the default passes falls back to the default). Decision metrics recomputed after the veto.
usage: hc_veto_1119.py <picker json (picker_1119b_*.json)> <pick variant>[,<pick variant>...] [default variants...]"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import hc3_count_1119 as HC3, analyze as A, picker_1119 as P
def main(pj, pick_vs, def_vs):
    J = json.load(open(os.path.join(H, pj))); rows = {r['id']: r for r in P.rows_all()}
    PF = {}; PR = {}
    for v in pick_vs:
        F = HC3.arr3(v); R = A.load(v)
        for k in F: PF[k] = F[k]; PR[k] = R[k]
    DF = {}; DR = {}
    for v in def_vs:
        F = HC3.arr3(v); R = A.load(v)
        for k in F: DF.setdefault(k, F[k]); DR.setdefault(k, R[k])
    out = dict(pairs=[]); cnt = collections.Counter()
    for p in J['per_pair']:
        i = p['id']; sg = p['style_gated']
        if sg.get('is_default') or not sg.get('win'): continue
        rec = dict(id=i, want=sg['win'])
        if i not in PR: rec['status'] = 'not_rendered'; cnt['not_rendered'] += 1; out['pairs'].append(rec); continue
        rr = PR[i]; rec['got'] = rr.get('win'); rec['applied'] = bool(rr.get('win') and list(rr['win']) == list(sg['win']))
        if not rec['applied']: cnt['not_applied'] += 1
        f = PF.get(i); d = DF.get(i)
        if f is None or d is None: rec['status'] = 'no_arrays'; cnt['no_arrays'] += 1; out['pairs'].append(rec); continue
        for hc in ('HC_A', 'HC_C'):
            rec[f'pick_{hc}'] = f[hc]; rec[f'def_{hc}'] = d[hc]; rec[f'new_{hc}'] = bool(f[hc] and not d[hc]); rec[f'fixed_{hc}'] = bool(d[hc] and not f[hc])
            cnt[f'pick_fail_{hc}'] += f[hc]; cnt[f'def_fail_{hc}'] += d[hc]; cnt[f'new_{hc}'] += rec[f'new_{hc}']; cnt[f'fixed_{hc}'] += rec[f'fixed_{hc}']
        rec['flags'] = {k: f[k] for k in ('hole_v2', 'hole_v3', 'hole_v3_score', 'clash_v1', 'halfbeat', 'pump', 'med_lag')}
        rec['veto'] = bool(rec['new_HC_C'] or rec['new_HC_A'] or not rec['applied']); cnt['veto'] += rec['veto']; cnt['checked'] += 1
        out['pairs'].append(rec)
    out['counts'] = dict(cnt)
    # decision metrics after the veto (vetoed pairs revert to the default exit / cue)
    V = {r['id']: r['veto'] for r in out['pairs'] if 'veto' in r}
    ids = [p['id'] for p in J['per_pair']]; g = [rows[i]['mix'] for i in ids]
    def ec(p, use):
        x = p['style_gated'] if use else dict(exit=p['dex'], cue=p['dcue'])
        return (abs(x['exit'] - p['pro_out']) + abs(x['cue'] - p['pro_in'])) / 2
    D_ = [ec(p, False) for p in J['per_pair']]; M_ = [ec(p, not V.get(p['id'], False)) for p in J['per_pair']]
    out['after_veto'] = dict(n=len(ids), default_ec=round(float(np.mean(D_)), 2), model_ec=round(float(np.mean(M_)), 2), delta=P.boot(g, D_, M_),
                             exit_hit16=round(float(np.mean([abs((p['style_gated'] if not V.get(p['id'], False) else dict(exit=p['dex']))['exit'] - p['pro_out']) <= 16 for p in J['per_pair']])), 3),
                             cue_hit16=round(float(np.mean([abs((p['style_gated'] if not V.get(p['id'], False) else dict(cue=p['dcue']))['cue'] - p['pro_in']) <= 16 for p in J['per_pair']])), 3))
    return out
if __name__ == '__main__':
    pj = sys.argv[1]; pv = sys.argv[2].split(','); dv = sys.argv[3].split(',') if len(sys.argv) > 3 else ['default', 'ndef1119']
    o = main(pj, pv, dv); name = os.environ.get('OUT') or f"hc_veto_{pj.replace('.json', '')}.json"
    json.dump(o, open(os.path.join(H, name), 'w'), indent=1, default=str); print(json.dumps(o['counts']), json.dumps(o['after_veto']))
