"""Re-count hard fails per rendered arm with the 11-19 hole candidate (T0=38, thr = pro p95 from hole_t0_1119.json).
HC_C = v3 hole OR v1 clash OR half-beat OR v1 pumping. Also HC_A for reference. Arrays from hc2_cache only."""
import json, os, sys, pickle, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import hardcheck_v2 as V, final_eval as FE
HT = json.load(open(os.path.join(H, 'hole_t0_1119.json')))['chosen_on_dev']; T3, TH3 = HT['T0'], HT['thr']
def flags3(a):
    f = FE.flags(a); h3 = V.hole_score(a['lows'], a['s'], a['e'], T3); f['hole_v3_score'] = round(h3, 1); f['hole_v3'] = bool(h3 > TH3)
    f['HC_C'] = bool(f['hole_v3'] or f['clash_v1'] or f['halfbeat'] or f['pump']); return f
def arr3(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl')
    return {k: flags3(a) for k, a in pickle.load(open(p, 'rb')).items()} if os.path.exists(p) else {}
if __name__ == '__main__':
    out = {}
    for v in ('default', 'gated', 'on', 'dropx', 'dropc', 'kush_default', 'kush_dropx', 'kush_dropc'):
        F = arr3(v); out[v] = dict(n=len(F), **{k: sum(f[k] for f in F.values()) for k in ('HC_A', 'HC_C', 'hole_v2', 'hole_v3', 'clash_v1', 'halfbeat', 'pump')})
        print(v, out[v])
    json.dump(out, open(os.path.join(H, 'hc3_count_1119.json'), 'w'), indent=1)
