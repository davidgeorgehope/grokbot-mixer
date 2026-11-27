"""Compare lc_1127 (LEVEL_COMP=1) vs lcb_1127 (current default): v1, v2, must-pass, hard fails, bootstrap CIs."""
import json, sys, os, glob
import numpy as np
sys.path.insert(0, '/workspace/mixes/protrans')
import run_admitted_tune as T, promotion_judge as PJ
B, A = 'lcb_1127', 'lc_1127'
rb, ra = list(T.load_ckpt(B).values()), list(T.load_ckpt(A).values())
def v2(var):
    return {json.loads(l)['id']: json.loads(l) for l in open(f'/workspace/mixes/protrans/research_1126/v2_{var}.jsonl')}
vb, va = v2(B), v2(A)
te = {v: json.load(open(f'/workspace/mixes/protrans/results/eval_tailexit_{v}.json')) for v in (B, A)}
def m(x): return round(float(np.mean(x)), 2) if len(x) else None
for sp in ('train', 'test', 'all'):
    ids = [i for i in vb if i in va and (sp == 'all' or vb[i]['split'] == sp)]
    d1 = [va[i]['v1'] - vb[i]['v1'] for i in ids]; d2 = [va[i]['v2'] - vb[i]['v2'] for i in ids]
    print(sp, len(ids), 'v1', m([vb[i]['v1'] for i in ids]), '->', m([va[i]['v1'] for i in ids]), 'delta', m(d1), '| v2', m([vb[i]['v2'] for i in ids]), '->', m([va[i]['v2'] for i in ids]), 'delta', m(d2), '| changed v1:', sum(abs(x) > 1e-6 for x in d1))
for sp in ('train', 'test'):
    print('CI v1', sp, PJ.paired_delta_ci(rb, ra, sp))
print(list(te[B].keys())[:5])

print('--- must-pass')
for v in (B, A):
    print(v, {k: te[v]['summary'][k]['all_pass'] for k in ('train', 'test', 'all')}, te[v]['summary']['all']['fails'], 'dip_med', te[v]['summary']['all']['dip_med'], 'banger', te[v]['summary']['all']['banger_med'])
# v2 CI (mix-grouped bootstrap, same seed/method as promotion_judge)
def boot(ids, d):
    mixes = {}
    for i in ids: mixes.setdefault(i.rsplit('__', 1)[0], []).append(d[i])
    ks = sorted(mixes); rng = np.random.default_rng(PJ.SEED); out = []
    for _ in range(PJ.N_BOOT):
        pick = rng.choice(len(ks), len(ks)); vals = [x for j in pick for x in mixes[ks[j]]]; out.append(np.mean(vals))
    return [round(float(np.percentile(out, 2.5)), 2), round(float(np.percentile(out, 97.5)), 2)]
for sp in ('train', 'test', 'all'):
    ids = [i for i in vb if i in va and (sp == 'all' or vb[i]['split'] == sp)]
    print('CI v2', sp, boot(ids, {i: va[i]['v2'] - vb[i]['v2'] for i in ids}))
print('--- per-pair changes (v1, v2)')
for i in sorted(vb):
    d1, d2 = va[i]['v1'] - vb[i]['v1'], va[i]['v2'] - vb[i]['v2']
    if abs(d1) > 1e-6 or abs(d2) > 1e-6: print(i, vb[i]['split'], round(d1, 2), round(d2, 2))
print('--- hard checks (pump etc.)')
sys.path.insert(0, '/workspace/mixes/protrans/replica'); sys.path.insert(0, '/workspace/mixes/src2'); sys.path.insert(0, '/workspace/mixes/protrans')
import hardcheck as HC
os.chdir('/workspace/mixes/src2')
hc = {}
for v in (B, A):
    hc[v] = {}
    for rid, r in te[v]['rows'].items():
        try: hc[v][rid] = HC.check(r['meta'])
        except Exception as ex: hc[v][rid] = dict(err=str(ex)[:80])
    ok = [x for x in hc[v].values() if 'err' not in x]
    print(v, 'n', len(ok), 'hard_fail', sum(x['hard_fail'] for x in ok), 'pump', sum(x['pumping'] for x in ok), 'hole', sum(x['bass_hole'] for x in ok), 'clash', sum(x['beat_clash'] for x in ok), 'vanish', sum(x['incoming_vanish'] for x in ok), 'mean pump_db', round(np.mean([x['pump_db'] for x in ok]), 2))
for rid in sorted(hc[B]):
    a, b = hc[B][rid], hc[A][rid]
    if 'err' in a or 'err' in b: print(rid, 'err'); continue
    if a['pump_db'] != b['pump_db'] or a['hard_fail'] != b['hard_fail']: print(rid, 'pump', a['pump_db'], '->', b['pump_db'], 'hard_fail', a['hard_fail'], '->', b['hard_fail'])
json.dump({v: hc[v] for v in hc}, open('/workspace/mixes/protrans/research_1127/hardcheck_levelcomp.json', 'w'), default=str)
