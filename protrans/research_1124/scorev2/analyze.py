"""Before/after numbers for official_v2: cohort means, paired bootstrap CIs, agreement with pro placement and with the listener."""
import os, sys, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = '/workspace/mixes/protrans'; sys.path.insert(0, PT)
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score_v2 as S2
from scipy.stats import spearmanr
rng = np.random.default_rng(1124); NB = 5000
DEC = json.load(open(os.path.join(PT, 'replica', 'protrans_decisions.json')))
ARMS = ['base', 'replica_x16', 'dropcand_exit']
rows = {a: {r['id']: r for r in map(json.loads, open(os.path.join(HERE, f'cohort_{a}.jsonl'))) if not r.get('error')} for a in ARMS if os.path.exists(os.path.join(HERE, f'cohort_{a}.jsonl'))}
for v in rows.values():   # v2 from the stored audio events with the current placement_score/combine (cohort job loaded an earlier copy)
    for r in v.values():
        r['v2_job'] = r['v2']
        pl = S2.placement_score(r['placement']['ours'], r['placement']['pro']); r['placement']['parts'] = pl
        r['v2'] = round(S2.combine(r['v1'], r['v1_breakdown'], pl), 2)
ids = sorted(set.intersection(*[set(v) for v in rows.values()]))
split = {i: rows['base'][i]['split'] for i in ids}

def eng_bar(yt, nat_bar):
    """protrans_decisions bars are native seconds / (240/174); convert to the engine's bar grid"""
    _, g, _ = S2._st(yt); dn = S2._downs(g); t_st = nat_bar * (240.0 / 174.0) * float(g.get('orig_bpm') or 174.0) / 174.0
    return float(np.interp(t_st, dn, np.arange(len(dn))))

import run_admitted_tune as T
recs = {r['id']: r for r in T.load_recs()}
def plan_err(i, win, ref='v2pro'):
    """placement error of the rendered plan window (engine bars, not audio) vs the pro.
    ref='v2pro': the pro measured by score_v2 (RANSAC locate); ref='decisions': replica/protrans_decisions.json"""
    kind, out_end, loop, in_begin, X = win
    if ref == 'decisions':
        d = DEC[i]; ya, yb = recs[i]['a']['yt'], recs[i]['b']['yt']
        pg, pc = eng_bar(ya, d['out_bar_at_gone']), eng_bar(yb, d['in_bar_at_entry'])
    else:
        p = rows['base'][i]['placement']['pro']
        if p.get('error'): return None
        pg = p['gone']['a'] if p['gone']['a'] is not None else p['swap']['a']
        pc = p['entry']['b']
        if pg is None or pc is None: return None
    return dict(exit=abs(out_end - pg), cue=abs(in_begin - pc))

def boot_mean_diff(x):
    x = np.asarray(x, float); b = rng.integers(0, len(x), (NB, len(x))); m = x[b].mean(1)
    return round(float(x.mean()), 2), [round(float(np.percentile(m, 2.5)), 2), round(float(np.percentile(m, 97.5)), 2)]

out = dict(n=len(ids), arms={}, diffs={}, placement_corr={}, measure_check={})
for a in rows:
    for sp in ('train', 'test'):
        ii = [i for i in ids if split[i] == sp]
        out['arms'].setdefault(a, {})[sp] = dict(v1=round(float(np.mean([rows[a][i]['v1'] for i in ii])), 2), v2=round(float(np.mean([rows[a][i]['v2'] for i in ii])), 2), n=len(ii))
for a in rows:
    if a == 'base': continue
    for sp in ('train', 'test'):
        ii = [i for i in ids if split[i] == sp]
        out['diffs'][f'{a}-base/{sp}'] = {s: boot_mean_diff([rows[a][i][s] - rows['base'][i][s] for i in ii]) for s in ('v1', 'v2')}
# placement error vs score, pooled over arms and within pair
for REF in ('v2pro', 'decisions'):
    E_, V1, V2, P = [], [], [], []
    for a in rows:
        for i in ids:
            e = plan_err(i, rows[a][i]['win'], REF)
            if e is None: continue
            E_.append(e['exit'] + e['cue']); V1.append(rows[a][i]['v1']); V2.append(rows[a][i]['v2']); P.append(i)
    E_, V1, V2, P = map(np.asarray, (E_, V1, V2, P))
    c1, c2 = spearmanr(-E_, V1)[0], spearmanr(-E_, V2)[0]
    bs = []; uid = np.unique(P)
    for _ in range(2000):
        pick = rng.choice(uid, len(uid)); sel = np.concatenate([np.flatnonzero(P == p) for p in pick])
        a1 = spearmanr(-E_[sel], V1[sel])[0]; a2 = spearmanr(-E_[sel], V2[sel])[0]
        if np.isfinite(a1) and np.isfinite(a2): bs.append(a2 - a1)
    res = dict(pooled_spearman=dict(v1=round(float(c1), 3), v2=round(float(c2), 3), v2_minus_v1_CI=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)], n=len(E_)))
    agree = {'v1': [], 'v2': []}
    for i in uid:
        sel = np.flatnonzero(P == i)
        for x in range(len(sel)):
            for y in range(x + 1, len(sel)):
                ex, ey = E_[sel[x]], E_[sel[y]]
                if abs(ex - ey) < 8: continue   # only pairs of renders where one is clearly closer to the pro
                for sname, V in (('v1', V1), ('v2', V2)):
                    agree[sname].append(float((V[sel[x]] - V[sel[y]]) * (ey - ex) > 0))
    res['within_pair_agreement'] = {k: dict(rate=round(float(np.mean(v)), 3) if v else None, n=len(v)) for k, v in agree.items()}
    if agree['v1']:
        res['within_pair_agreement']['v2_minus_v1'] = boot_mean_diff(np.asarray(agree['v2']) - np.asarray(agree['v1']))
    out['placement_corr'][REF] = res
# measurement check: v2's audio-measured A exit bar vs the plan's out_end, and v2's pro measurement vs protrans_decisions
dev = []
for a in rows:
    for i in ids:
        o = rows[a][i]['placement']['ours']
        if o.get('error') or o['gone']['a'] is None: continue
        dev.append(o['gone']['a'] - rows[a][i]['win'][1])
dev = np.asarray(dev); out['measure_check']['ours_gone_minus_plan_out_end'] = dict(median=round(float(np.median(dev)), 1), p90_abs=round(float(np.percentile(np.abs(dev), 90)), 1), n=len(dev), over_8=int((np.abs(dev) > 8).sum()))
pd = []
for i in ids:
    p = rows['base'][i]['placement']['pro']
    if p.get('error') or p['entry']['a'] is None or DEC[i].get('out_bar_at_entry') is None: continue
    pd.append(dict(id=i, v2_entry_a=p['entry']['a'], dec_entry_a=round(eng_bar(recs[i]['a']['yt'], DEC[i]['out_bar_at_entry']), 1)))
dd = np.asarray([x['v2_entry_a'] - x['dec_entry_a'] for x in pd])
out['measure_check']['pro_entry_a_v2_minus_decisions'] = dict(median=round(float(np.median(dd)), 1), over_8=[x for x in pd if abs(x['v2_entry_a'] - x['dec_entry_a']) > 8], n=len(dd))
# the listener's ratings
rp = os.path.join(HERE, 'ratings.json')
if os.path.exists(rp):
    R = json.load(open(rp)); r = np.array([x['rating'] for x in R])
    from collections import defaultdict
    by = defaultdict(list)
    for x in R: by[x['pair']].append(x)
    pairs = list(by)
    def spr(key, items):
        return spearmanr([x['rating'] for x in items], [x[key] for x in items])[0]
    c1, c2 = spr('v1', R), spr('v2', R)
    bs1, bs2, bsd = [], [], []
    for _ in range(NB):
        items = [x for p in rng.choice(pairs, len(pairs)) for x in by[p]]
        a1, a2 = spr('v1', items), spr('v2', items)
        if np.isfinite(a1) and np.isfinite(a2):
            bs1.append(a1); bs2.append(a2); bsd.append(a2 - a1)
    def ci(a):
        return [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]
    out['david'] = dict(n=len(R), n_pairs=len(pairs), spearman_v1=round(float(c1), 3), spearman_v2=round(float(c2), 3),
                        spearman_v1_CI=ci(bs1), spearman_v2_CI=ci(bs2), v2_minus_v1_CI=ci(bsd),
                        rows=[{k: x[k] for k in ('pair', 'src', 'rating', 'v1', 'v2')} for x in R])
# reproduction: base renders vs the like1124_base checkpoint (same rules, same pin)
L = {r['id']: r for r in map(json.loads, open(os.path.join(PT, 'results', 'score_ckpt', 'like1124_base.jsonl'))) if not r.get('error')}
rep = [(i, rows['base'][i]['v1'], L[i]['score']['score']) for i in ids if i in L]
out['repro_vs_like1124_base'] = dict(n=len(rep), exact=sum(abs(a - b) < 0.01 for _, a, b in rep), diffs=[x for x in rep if abs(x[1] - x[2]) >= 0.01])
# the ukf__10 pick
u = 'hybrid_minds_ukf__10'
out['ukf10'] = {a: dict(win=rows[a][u]['win'], v1=rows[a][u]['v1'], v2=rows[a][u]['v2'], place=rows[a][u]['placement']['parts']) for a in rows if u in rows[a]}
# replica_on (32-bar blend starting at A bar 128) was the 32.7 v1 score; not a cohort arm
ron = os.path.join(HERE, 'renders', 'ukf10_replica_on.mp3')
if os.path.exists(ron):
    import score
    rec = recs[u]; sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    r = S2.score_v2(rec['pro_clip'], ron, sa, sb)
    out['ukf10']['replica_on'] = dict(win=['n', 160, None, 16, 32], v1=r['score'], v2=r['official_v2'], place=r['placement']['parts'],
                                      ours={k: r['placement']['ours'].get(k) for k in ('entry', 'gone', 'swap')})
if 'replica_on' in out['ukf10'] and 'base' in out['ukf10']:
    out['ukf10']['v2_prefers_bar129'] = out['ukf10']['replica_on']['v2'] > out['ukf10']['base']['v2']
    out['ukf10']['v1_prefers_bar129'] = out['ukf10']['replica_on']['v1'] > out['ukf10']['base']['v1']
sp = os.path.join(HERE, 'synth_v1v2.json')
if os.path.exists(sp):
    out['gameability'] = json.load(open(sp))
# pinned official floor (v1 means on the 33 admitted pairs)
out['pinned_floor_v1'] = dict(train=out['arms']['base']['train']['v1'], test=out['arms']['base']['test']['v1'], published=dict(train=32.40, test=34.07))
json.dump(out, open(os.path.join(HERE, 'analysis.json'), 'w'), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
