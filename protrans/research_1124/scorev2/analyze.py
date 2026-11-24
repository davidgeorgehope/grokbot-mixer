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
def plan_err(i, win):
    """placement error from the rendered plan window vs the pro decisions (independent of the v2 audio measurement)"""
    d = DEC[i]; ya, yb = recs[i]['a']['yt'], recs[i]['b']['yt']
    kind, out_end, loop, in_begin, X = win
    pro_gone = eng_bar(ya, d['out_bar_at_gone']); pro_cue = eng_bar(yb, d['in_bar_at_entry'])
    return dict(exit=abs(out_end - pro_gone), cue=abs(in_begin - pro_cue), start=abs((out_end - X) - eng_bar(ya, d['out_bar_at_entry'])))

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
E_, V1, V2, P = [], [], [], []
for a in rows:
    for i in ids:
        e = plan_err(i, rows[a][i]['win']); E_.append(e['exit'] + e['cue']); V1.append(rows[a][i]['v1']); V2.append(rows[a][i]['v2']); P.append(i)
E_, V1, V2 = map(np.asarray, (E_, V1, V2)); P = np.asarray(P)
def corr(sel):
    return spearmanr(-E_[sel], V1[sel])[0], spearmanr(-E_[sel], V2[sel])[0]
c1, c2 = corr(np.ones(len(E_), bool))
bs = []
uid = np.array(ids)
for _ in range(2000):
    pick = rng.choice(uid, len(uid)); sel = np.concatenate([np.flatnonzero(P == p) for p in pick])
    with np.errstate(all='ignore'):
        a1 = spearmanr(-E_[sel], V1[sel])[0]; a2 = spearmanr(-E_[sel], V2[sel])[0]
    if np.isfinite(a1) and np.isfinite(a2): bs.append(a2 - a1)
out['placement_corr']['pooled_spearman(-err, score)'] = dict(v1=round(float(c1), 3), v2=round(float(c2), 3), v2_minus_v1_CI=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)])
# within pair: does the arm with the smaller placement error get the higher score?
agree = {'v1': [], 'v2': []}
for i in ids:
    sel = np.flatnonzero(P == i)
    for x in range(len(sel)):
        for y in range(x + 1, len(sel)):
            ex, ey = E_[sel[x]], E_[sel[y]]
            if abs(ex - ey) < 8: continue   # only pairs where one placement is clearly closer to the pro
            for s, V in (('v1', V1), ('v2', V2)):
                agree[s].append(float((V[sel[x]] - V[sel[y]]) * (ey - ex) > 0))
out['placement_corr']['within_pair_agreement'] = {s: dict(rate=round(float(np.mean(v)), 3), n=len(v)) for s, v in agree.items()}
if agree['v1']:
    d = np.asarray(agree['v2']) - np.asarray(agree['v1']); out['placement_corr']['within_pair_agreement']['v2_minus_v1'] = boot_mean_diff(d)
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
    out['david'] = dict(n=len(R), spearman_v1=round(float(spearmanr(r, [x['v1'] for x in R])[0]), 3), spearman_v2=round(float(spearmanr(r, [x['v2'] for x in R])[0]), 3),
                        rows=[{k: x[k] for k in ('pair', 'src', 'rating', 'v1', 'v2')} for x in R])
# the ukf__10 pick
u = 'hybrid_minds_ukf__10'
out['ukf10'] = {a: dict(win=rows[a][u]['win'], v1=rows[a][u]['v1'], v2=rows[a][u]['v2'], place=rows[a][u]['placement']['parts']) for a in rows if u in rows[a]}
json.dump(out, open(os.path.join(HERE, 'analysis.json'), 'w'), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
