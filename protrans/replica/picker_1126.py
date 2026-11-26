#!/usr/bin/env python3
"""Nightly 2026-11-26 (n1126): frozen model-picker arms (promotion_criteria.json frozen_arms_n1126, written before eval).
Reuses picker_1125 / picker_1119b unchanged (features, LambdaMART rankers, margin gate, ride-vs-leave gate) on the grown snapshot.
Arms: ridegate (PRIMARY, same spec as n1125), ridegate_tail (SECONDARY: + tail-exit candidates, incoming enters 8 bars before the
end of the outgoing music grid with an 8-bar blend), ridegate_online_tf (DIAGNOSTIC: ride gate also sees the pro's strictly earlier
transitions in the same mix), plus cueonly_gated, ref_full_gated, default, majority, simple rule.
usage: picker_1126.py cv | protrans | fresh | holdout"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1125 as Q
P, B = Q.P, Q.B
import lightgbm as lgb
W = os.path.join(H, 'nightly_1126_work'); os.makedirs(W, exist_ok=True)
FRESH_ALL = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
FRESH_TONIGHT = 'ukf_drum_bass_wVp_VlkWqxI'; assert FRESH_TONIGHT in FRESH_ALL
P.W = W; B.W = W; Q.W = W; P.SPENT_FRESH = FRESH_ALL
EXCL_DJ = {'Liquicity Events'}  # same brand as the locked holdout; kept out of dev, never scored
SEED = 20261126

def exit_cands_tail(r):
    E = [dict(v=c['v'], tags=set(c['tags'])) for c in r['E']]; byv = {c['v']: c for c in E}; na = int(Q.na_(r))
    v = (na // 8) * 8 - 8 + 1
    if v >= 17: byv.setdefault(v, dict(v=v, tags=set()))['tags'].add('tail8')
    return [byv[k] for k in sorted(byv)]

def make_tail(rows):
    out = []
    for r in rows:
        E2 = exit_cands_tail(r); q = dict(r); q['E'] = E2; q.pop('XE0', None); q.pop('XE1', None)
        q['Erel'] = np.array([B.rel(P.acc_err(c['v'], r['pro_out'], P.bnd_a(r['sa']))) for c in E2])
        q['Edix'] = next(i for i, c in enumerate(E2) if 'default' in c['tags'])
        q['XE0'] = np.array([B.fe_exit(q, c, False) + [int('tail8' in c['tags'])] for c in E2], float)
        out.append(q)
    return out

RIDEF_TF = lambda r: Q.RIDEF(r) + B.style_feats(r)
def fit_ride_tf(tr):
    y = np.array([float(Q.is_mid(r, r['pro_out'])) for r in tr]); X = np.array([RIDEF_TF(r) for r in tr], float)
    m = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=1, random_state=SEED).fit(X, y)
    return lambda rs: m.predict_proba(np.array([RIDEF_TF(r) for r in rs], float))[:, 1]

def Xof(r, j, dX): return 8 if 'tail8' in r['E'][j]['tags'] else dX

def train_predict(tr, te, trT, teT):
    djs = sorted({r['dj'] for r in tr}); P_in, P_tf = {}, {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]
        for r, p in zip(b, Q.fit_ride(a)(b)): P_in[r['id']] = p
        for r, p in zip(b, fit_ride_tf(a)(b)): P_tf[r['id']] = p
    ride = Q.fit_ride(tr)(te); ride_tf = fit_ride_tf(tr)(te); o = {}
    for tag, TR, TE in (('v1', tr, te), ('tail', trT, teT)):
        (eE, ciE, tauE), S_in = Q.inner_oof(TR, 'E'); th = Q.choose_theta(TR, S_in, tauE, P_in)
        mE = B.fit(TR, 'E', False, B.CFGS[ciE]); SE = B.scores(mE, TE, 'E', False)
        o[tag] = dict(jg=[B.gpick(r, 'E', s, tauE) for r, s in zip(TE, SE)], cfg=ciE, tau=tauE, theta=th[1], inner_exit=round(float(eE), 2), inner_ride=round(float(th[0]), 2))
        o[tag]['jr'] = [Q.ride_pick(r, j, p, th[1]) for r, j, p in zip(TE, o[tag]['jg'], ride)]
        if tag == 'v1':
            th2 = Q.choose_theta(TR, S_in, tauE, P_tf); o[tag]['theta_tf'] = th2[1]
            o[tag]['jtf'] = [Q.ride_pick(r, j, p, th2[1]) for r, j, p in zip(TE, o[tag]['jg'], ride_tf)]
    eC, ciC, tauC = B.inner(tr, 'C', False); mC = B.fit(tr, 'C', False, B.CFGS[ciC]); SC = B.scores(mC, te, 'C', False)
    jc = [B.gpick(r, 'C', s, tauC) for r, s in zip(te, SC)]; Xm = B.fitX(tr, False)(te)
    D = {}
    D['cueonly_gated'] = [B.decide(r, r['Edix'], c, r['dX']) for r, c in zip(te, jc)]
    D['ridegate'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, o['v1']['jr'], jc)]
    D['ridegate_tail'] = [B.decide(r, j, c, Xof(r, j, r['dX'])) for r, j, c in zip(teT, o['tail']['jr'], jc)]
    D['ridegate_online_tf'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, o['v1']['jtf'], jc)]
    D['ref_full_gated'] = [B.decide(r, j, c, X) for r, j, c, X in zip(te, o['v1']['jg'], jc, Xm)]
    D['default'] = [B.base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] = [B.base_decisions(r, 'rule_drop_exit') for r in te]
    mb, md = Q.majority(tr, te); D['majority'] = md
    for k in D:
        for x, p, q in zip(D[k], ride, ride_tf): x['p_leave'] = round(float(p), 3); x['p_leave_tf'] = round(float(q), 3)
    diag = {t: {k: o[t][k] for k in o[t] if k not in ('jg', 'jr', 'jtf')} for t in o}; diag['C'] = dict(cfg=ciC, tau=tauC); diag['majority'] = mb
    return D, diag

def _fold(args):
    d, dev, devT = args
    tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]
    trT = [r for r in devT if r['dj'] != d]; teT = [r for r in devT if r['dj'] == d]
    D, diag = train_predict(tr, te, trT, teT); print('fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag

def strip(D): return {k: [dict(exit=x['exit'], cue=x['cue'], X=x['X'], is_default=bool(x.get('is_default')), p_leave=x.get('p_leave'), p_leave_tf=x.get('p_leave_tf'), win=x.get('win')) for x in L] for k, L in D.items()}
def pp_rows(rs, D): return [dict(id=r['id'], dj=r['dj'], mix=r['mix'], idx=r['idx'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'], na=Q.na_(r),
                                    **{k: v[i] for k, v in strip(D).items()}) for i, r in enumerate(rs)]

def coverage(rows, rowsT):
    out = {}
    for nm, R in (('v1', rows), ('tail', rowsT)):
        b = [min(abs(c['v'] - r['pro_out']) for c in r['E']) for r in R]
        out[f'{nm}_E'] = {f'within{t}': round(float(np.mean([x <= t for x in b])), 3) for t in (4, 8, 16)}
        tl = [r for r in R if Q.na_(r) - r['pro_out'] <= 12]
        out[f'{nm}_E_protail_within8'] = round(float(np.mean([min(abs(c['v'] - r['pro_out']) for c in r['E']) <= 8 for r in tl])), 3); out['n_protail'] = len(tl)
    return out

if __name__ == '__main__':
    mode = sys.argv[1]
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    for r in rows:
        if r['dj'] in EXCL_DJ and r['set'] == 'dev': r['set'] = 'excluded'
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    dev = [r for r in rows if r['set'] == 'dev']; B.XM(dev, 'E', False); B.XM(dev, 'C', False); devT = make_tail(dev)
    for q, r in zip(devT, dev): q['XC0'] = r['XC0']
    if mode == 'cv':
        cov = coverage(dev, devT); print('coverage', cov, flush=True)
        from concurrent.futures import ProcessPoolExecutor
        djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}; order = []; D = collections.defaultdict(list); folds = {}
        with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 3))) as ex:
            for d, ids, Dd, diag in ex.map(_fold, [(d, dev, devT) for d in djs]):
                order += [byid[i] for i in ids]; folds[d] = diag
                for k, v in Dd.items(): D[k] += v
        out = dict(n=len(order), n_mixes=len({r['mix'] for r in order}), n_djs=len(djs), coverage=cov, folds=folds, per_pair=pp_rows(order, D))
        json.dump(out, open(os.path.join(W, 'picker_1126_cv.json'), 'w'), indent=1, default=str)
    else:
        which = {'protrans': 'protrans', 'fresh': 'fresh', 'holdout': 'holdout'}[mode]
        te = [r for r in rows if r['set'] == which and (mode != 'fresh' or r['mix'] == FRESH_TONIGHT)]
        for r in te: r.pop('XE0', None); r.pop('XC0', None)
        B.XM(te, 'E', False); B.XM(te, 'C', False); teT = make_tail(te)
        for q, r in zip(teT, te): q['XC0'] = r['XC0']
        print(mode, 'rows', len(te), flush=True)
        D, diag = train_predict(dev, te, devT, teT)
        out = dict(set=mode, n=len(te), mixes=sorted({r['mix'] for r in te}), diag=diag, per_pair=pp_rows(te, D))
        if mode == 'protrans':
            import run_admitted_tune as T
            recs = {r['id']: r for r in T.load_recs()}; out['maps'] = {}
            for arm in ('ridegate', 'ridegate_tail'):
                by_yt, by_id = {}, {}
                for r, x in zip(te, D[arm]):
                    rec = recs.get(r['id']); key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
                    by_id[r['id']] = dict(win=x.get('win'), exit=x['exit'], cue=x['cue'], X=x['X'], abstain=bool(x.get('is_default')), yt_key=key)
                    if key and x.get('win') and not x.get('is_default'): by_yt[key] = x['win']
                mp = dict(written='2026-11-26 n1126', model=f'picker_1126 {arm} (style-free), trained on {len(dev)} dev, applied to the 33 protrans pairs', by_yt=by_yt, by_id=by_id,
                          do_not='write rules.json or treat this map as a promotion')
                dest = os.path.join(W, f'map_{arm}.json'); json.dump(mp, open(dest, 'w'), indent=1, default=str); out['maps'][arm] = dict(path=dest, n_windows=len(by_yt))
        json.dump(out, open(os.path.join(W, f'picker_1126_{mode}.json'), 'w'), indent=1, default=str)
    print('DONE', mode, flush=True)
