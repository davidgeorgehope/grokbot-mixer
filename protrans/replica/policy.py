#!/usr/bin/env python3
"""Per-pair chooser between the default window and the replica (breakdown-exit) window, judged only on pro decisions.
Nested grouped CV (outer leave-one-DJ-out on DEV; inner leave-one-DJ-out picks C and the conformal level), split-conformal
abstention (use the replica only when the conformal prediction set is {replica}; otherwise default), baselines
(default / always-replica rule / a-priori gate / majority choice), tolerance hit rates, acceptable-section sets,
grouped bootstrap CIs. --final evaluates the models fit on all DEV on the locked holdout (run once).
Reads replica/gate_ckpt/{default,on,gated}.jsonl; writes replica/policy_{dev,final}.json."""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
sys.path.insert(0, H); sys.path.insert(0, SRC2)
import analyze as A
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import eval_gate as EG
TOLS = (4, 8, 16)

def feats(a, b):
    os.chdir(SRC2); import sections as S, replica_rule as RR
    sa, sb = S.get(a), S.get(b); g, gi = RR.gate(sa, sb, a_id=a); w, wi = RR.window(sa, sb, a_id=a)
    na = sa.get('music_end') or 0; d = sa.get('drops') or []
    f = dict(a_ndrops=len(d), a_bd_len=gi.get('bd_len') or 0, a_dip=gi.get('dip_db') or 0, gate=int(bool(g)),
             fallback=int(bool(w) and not g and isinstance(wi, dict) and wi.get('src') == 'structure_fallback'),
             a_len=na, a_drop1=sa.get('drop1') or 0, a_outro=na - (sa.get('outro_start') or na),
             a_bd_pos=(wi['bd'] / na) if (w and na) else 1.0, b_drop1=sb.get('drop1') or 0, b_len=sb.get('music_end') or 0,
             b_ndrops=len(sb.get('drops') or []))
    bnd = sorted({int(x) for x in ([sa.get('drop1'), sa.get('breakdown'), sa.get('drop2'), sa.get('outro_start'), na] + [y for dd in d for y in dd]) if x is not None})
    bndb = sorted({int(x) for x in ([0, sb.get('drop1'), sb.get('breakdown'), sb.get('drop2'), sb.get('outro_start')] + [y for dd in (sb.get('drops') or []) for y in dd]) if x is not None})
    return f, bnd, bndb

def acc_err(ours, pro, bnd, tol_set=8):
    """distance from our bar to the acceptable set: the pro's bar plus every section boundary within tol_set bars of it"""
    S = [pro] + [x for x in bnd if abs(x - pro) <= tol_set]
    return min(abs(ours - s) for s in S)

def load_all(final):
    D, O, G = (A.subset(A.load(v), final) for v in ('default', 'on', 'gated'))
    PR = {r['id']: r for r in EG.pairs()}
    rows = []
    for i in sorted(set(D) & set(O) & set(G)):
        if any(x[i].get('error') for x in (D, O, G)): continue
        f, bnd, bndb = feats(PR[i]['a'], PR[i]['b']); pro = PR[i]['pro']
        rows.append(dict(id=i, dj=D[i]['dj'], mix=D[i]['mix'], f=f, bnd=bnd, bndb=bndb, pro=pro, D=D[i], O=O[i], G=G[i],
                         y=int(A.metric(O[i], 'exit_cue') < A.metric(D[i], 'exit_cue')),
                         same=D[i]['win'] == O[i]['win']))
    return rows

KEYS = ['a_ndrops', 'a_bd_len', 'a_dip', 'gate', 'fallback', 'a_len', 'a_drop1', 'a_outro', 'a_bd_pos', 'b_drop1', 'b_len', 'b_ndrops']
def X_(rs, style=None):
    X = np.array([[r['f'][k] for k in KEYS] for r in rs], float)
    if style is not None: X = np.hstack([X, np.array([[style(r)] for r in rs], float)])
    return X

def fit(rs, C, style=None):
    m = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000, class_weight='balanced'))
    y = np.array([r['y'] for r in rs])
    if len(set(y)) < 2: return ('const', int(y[0]))
    m.fit(X_(rs, style), y); return m

def proba(m, rs, style=None):
    if isinstance(m, tuple): return np.full(len(rs), float(m[1]))
    return m.predict_proba(X_(rs, style))[:, 1]

def oof(rs, C, style=None):
    """leave-one-DJ-out out-of-fold P(replica better)"""
    p = np.zeros(len(rs)); djs = sorted({r['dj'] for r in rs})
    for d in djs:
        tr = [r for r in rs if r['dj'] != d]; te = [j for j, r in enumerate(rs) if r['dj'] == d]
        m = fit(tr, C, style); p[te] = proba(m, [rs[j] for j in te], style)
    return p

def conformal_q(p, y, alpha):
    s = np.where(y == 1, 1 - p, p); n = len(s)  # nonconformity = 1 - p(true label)
    k = int(np.ceil((n + 1) * (1 - alpha))); return float(np.sort(s)[min(k, n) - 1])

def choose(p, q):
    """replica iff the conformal set is exactly {replica}: 1-p<=q and p>q"""
    return (1 - p <= q) & (p > q)

def pick_rows(rs, use):  # use[j] True -> replica row
    return [r['O'] if u else r['D'] for r, u in zip(rs, use)]

def err_of(r, k):
    return A.metric(r, k)

def inner_select(tr, style=None):
    best = None
    for C in (0.01, 0.1, 1.0, 10.0):
        p = oof(tr, C, style); y = np.array([r['y'] for r in tr])
        for alpha in (0.1, 0.2, 0.3):
            # conformal calibrated on the same out-of-fold probabilities, evaluated by the policy's exit+cue error
            q = conformal_q(p, y, alpha); use = choose(p, q)
            e = np.mean([err_of(x, 'exit_cue') for x in pick_rows(tr, use)])
            if best is None or e < best[0]: best = (e, C, alpha, q)
    return best

def policies(train, test, style=None):
    """returns dict name -> list of chosen rows for test, plus model diagnostics"""
    out = {}; diag = {}
    out['default'] = [r['D'] for r in test]; out['rule_always_replica'] = [r['O'] for r in test]; out['gate_apriori'] = [r['G'] for r in test]
    maj = int(np.mean([r['y'] for r in train]) > 0.5); out['majority'] = [r['O'] if maj else r['D'] for r in test]
    e, C, alpha, q = inner_select(train, style)
    m = fit(train, C, style); p = proba(m, test, style); use = choose(p, q)
    out['model_conformal'] = pick_rows(test, use)
    out['model_plain'] = pick_rows(test, p > 0.5)
    y = np.array([r['y'] for r in test])
    inset = [((1 - pj <= q) if yj == 1 else (pj <= q)) for pj, yj in zip(p, y)]
    diag = dict(C=C, alpha=alpha, q=round(q, 3), use=use.tolist(), coverage=inset, p=p.round(3).tolist(), maj=maj)
    return out, diag

def evaluate(rs_test, chosen, name_ref='default'):
    res = {}
    groups = {r['id']: r['mix'] for r in rs_test}
    for name, rows in chosen.items():
        s = {}
        for k in ('exit', 'cue', 'exit_cue', 'overlap', 'swap', 'fade'):
            v = [err_of(x, k) for x in rows]; v = [x for x in v if x is not None]
            s[k + '_median'] = round(float(np.median(v)), 1) if v else None; s[k + '_mean'] = round(float(np.mean(v)), 1) if v else None
        for t in TOLS:
            s[f'exit_hit{t}'] = round(float(np.mean([x['err']['exit'] <= t for x in rows])), 3)
            s[f'cue_hit{t}'] = round(float(np.mean([x['err']['cue'] <= t for x in rows])), 3)
            s[f'exit_accset_hit{t}'] = round(float(np.mean([acc_err(x['ours']['out_bar'], r['pro']['out_bar'], r['bnd']) <= t for x, r in zip(rows, rs_test)])), 3)
            s[f'cue_accset_hit{t}'] = round(float(np.mean([acc_err(x['ours']['in_bar'], r['pro']['in_bar'], r['bndb']) <= t for x, r in zip(rows, rs_test)])), 3)
        s['hard_fail'] = sum(1 for x in rows if x['hard']['hard_fail']); s['n'] = len(rows)
        s['replica_used'] = sum(1 for x, r in zip(rows, rs_test) if x is r['O'] and not r['same'])
        res[name] = s
    ref = {r['id']: x for r, x in zip(rs_test, chosen[name_ref])}; ids = [r['id'] for r in rs_test]
    for name, rows in chosen.items():
        if name == name_ref: continue
        B = {r['id']: x for r, x in zip(rs_test, rows)}
        res[name]['delta_vs_default'] = {k: A.boot_delta(ids, ref, B, k, groups) for k in ('exit', 'cue', 'exit_cue', 'overlap', 'fade')}
        # hit-rate delta CI (exit within 16), grouped bootstrap on per-pair hit differences
        res[name]['delta_exit_hit16'] = hit_delta(ids, ref, B, groups, 16)
        res[name]['delta_exit_hit8'] = hit_delta(ids, ref, B, groups, 8)
    return res

def hit_delta(ids, R, B, groups, t, n=4000):
    d = collections.defaultdict(list)
    for i in ids: d[groups[i]].append(float(B[i]['err']['exit'] <= t) - float(R[i]['err']['exit'] <= t))
    G = list(d); rng = np.random.default_rng(20261118); allv = [x for g in G for x in d[g]]
    bs = [np.mean([x for j in rng.choice(len(G), len(G)) for x in d[G[j]]]) for _ in range(n)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(delta=round(float(np.mean(allv)), 3), ci=[round(float(lo), 3), round(float(hi), 3)], verdict='better' if lo > 0 else ('worse' if hi < 0 else 'no clear difference'))

def mid_exit(r):  # pro mid-track exit (>40 bars of outgoing music left): the DJ-style bit
    return float(r['f']['a_len'] - r['pro']['out_bar'] > 40)

def run_dev(style_mode=None):
    rs = load_all(False); djs = sorted({r['dj'] for r in rs})
    style = None
    if style_mode == 'mix_setting':  # style as a user setting: 1 bit per mix (does this DJ exit mid-track?), from the pros of that mix
        mixbit = collections.defaultdict(list)
        for r in rs: mixbit[r['mix']].append(mid_exit(r))
        mb = {k: float(np.mean(v) > 0.5) for k, v in mixbit.items()}; style = lambda r: mb[r['mix']]
    allchosen = collections.defaultdict(list); order = []; diags = {}
    for d in djs:
        tr = [r for r in rs if r['dj'] != d]; te = [r for r in rs if r['dj'] == d]
        ch, dg = policies(tr, te, style); diags[d] = dict(C=dg['C'], alpha=dg['alpha'], q=dg['q'], n=len(te), used=int(sum(dg['use'])), maj=dg['maj'])
        for k, v in ch.items(): allchosen[k] += v
        order += te; diags[d]['coverage'] = dg['coverage']
    res = evaluate(order, allchosen)
    cov = [c for d in diags.values() for c in d['coverage']]
    for d in diags.values(): d.pop('coverage')
    abst = sum(d['n'] - d['used'] for d in diags.values()) / max(1, sum(d['n'] for d in diags.values()))
    return dict(n=len(rs), djs=djs, label_rate=round(float(np.mean([r['y'] for r in rs])), 3), results=res, folds=diags,
                conformal_coverage=round(float(np.mean(cov)), 3), abstain_rate=round(abst, 3),
                worst=worst(order, allchosen['model_conformal'], allchosen['default']))

def worst(rs, M, D, k=6):
    w = sorted(((err_of(m, 'exit_cue') - err_of(d, 'exit_cue'), r['id'], r['dj'], m['fam'], m['win'], d['win'], r['pro']['out_bar'], r['pro']['in_bar'])
                for r, m, d in zip(rs, M, D)), reverse=True)[:k]
    return [dict(delta=round(x[0], 1), id=x[1], dj=x[2], fam=x[3], win=x[4], default_win=x[5], pro_exit=x[6], pro_cue=x[7]) for x in w]

def run_final(style_mode=None):
    dev = load_all(False); te = load_all(True)
    ch, dg = policies(dev, te)
    res = evaluate(te, ch)
    return dict(n=len(te), djs=sorted({r['dj'] for r in te}), mixes=sorted({r['mix'] for r in te}), model=dict(C=dg['C'], alpha=dg['alpha'], q=dg['q']),
                used=int(sum(dg['use'])), abstain_rate=round(1 - float(np.mean(dg['use'])), 3), conformal_coverage=round(float(np.mean(dg['coverage'])), 3),
                results=res, worst=worst(te, ch['model_conformal'], ch['default']))

if __name__ == '__main__':
    if '--final' in sys.argv:
        out = run_final(); json.dump(out, open(os.path.join(H, 'policy_final.json'), 'w'), indent=1, default=str)
    else:
        out = dict(no_style=run_dev(), style_setting=run_dev('mix_setting'))
        json.dump(out, open(os.path.join(H, 'policy_dev.json'), 'w'), indent=1, default=str)
    print(json.dumps(out, default=str)[:3000])
