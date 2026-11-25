#!/usr/bin/env python3
"""Nightly 2026-11-25 (n1125): frozen model-picker arms (see promotion_criteria.json frozen_arms_n1125, written before eval).
Reuses picker_1119b (features, LambdaMART rankers, margin gate, window legality) unchanged; adds
  * ride-vs-leave classifier gate on mid-track exits (theta by inner leave-one-DJ-out),
  * candidate set v2 for exits: outgoing drop-1 start and drop-1 start+16 (exits DURING drop 1, tag drop1_in),
  * arms: cueonly_gated (PRIMARY), ridegate, ridegate_cand2 (+ full-model reference arms, default, majority, simple rule),
  * candidate coverage report (oracle: best candidate within 4/8/16 bars of the pro choice).
Style-free throughout (the listener 2026-11-19). usage: picker_1125.py cv | fresh"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); sys.path.insert(0, H)
import picker_1119 as P
W = os.path.join(H, 'nightly_1125_work'); os.makedirs(W, exist_ok=True)
FRESH_ALL = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
FRESH_TONIGHT = 'kushsessions_z8SnJBUd-0U'
assert FRESH_TONIGHT in FRESH_ALL
P.W = W; P.SPENT_FRESH = FRESH_ALL
import picker_1119b as B
import lightgbm as lgb
B.W = W
THETAS = [0.5, 0.6, 0.7, 0.8]
SEED = 20261125

def na_(r): return float(r['sa'].get('music_end') or r['sa'].get('n_bars'))
def is_mid(r, v): return na_(r) - v > 40

def exit_cands2(r):
    E = [dict(v=c['v'], tags=set(c['tags'])) for c in r['E']]; byv = {c['v']: c for c in E}
    drops = [list(map(int, d)) for d in (r['sa'].get('drops') or [])]; na = int(na_(r))
    if drops:
        for off in (0, 16):
            v = P.ph(drops[0][0] + off) + 1
            if 1 <= v and v + 15 <= na: byv.setdefault(v, dict(v=v, tags=set()))['tags'].add('drop1_in')
    return [byv[v] for v in sorted(byv)]

def make_v2(rows):
    out = []
    for r in rows:
        E2 = exit_cands2(r); q = dict(r); q['E'] = E2; q.pop('XE0', None); q.pop('XE1', None)
        q['Erel'] = np.array([B.rel(P.acc_err(c['v'], r['pro_out'], P.bnd_a(r['sa']))) for c in E2])
        q['Edix'] = next(i for i, c in enumerate(E2) if 'default' in c['tags'])
        q['XE0'] = np.array([B.fe_exit(q, c, False) + [int('drop1_in' in c['tags'])] for c in E2], float)
        out.append(q)
    return out

RIDEF = lambda r: B.base_feats(r) + [len(r['sa'].get('drops') or []) and na_(r) - r['sa']['drops'][-1][1]]
def fit_ride(tr):
    y = np.array([float(is_mid(r, r['pro_out'])) for r in tr]); X = np.array([RIDEF(r) for r in tr], float)
    m = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=1, random_state=SEED).fit(X, y)
    return lambda rs: m.predict_proba(np.array([RIDEF(r) for r in rs], float))[:, 1]

def inner_oof(tr, part):
    """inner leave-one-DJ-out: best (cfg, tau) as in picker_1119b.inner, plus the out-of-fold scores at that cfg"""
    djs = sorted({r['dj'] for r in tr}); best = None; SS = {}
    for ci, cfg in enumerate(B.CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]; m = B.fit(a, part, False, cfg)
            for r, s in zip(b, B.scores(m, b, part, False)): S[r['id']] = s
        SS[ci] = S
        for t in B.TAUS:
            e = np.mean([B.perr(r, part, B.gpick(r, part, S[r['id']], t)) for r in tr])
            if best is None or e < best[0]: best = (e, ci, t)
    return best, SS[best[1]]

def ride_pick(r, je, p, th):
    return je if (je == r['Edix'] or not is_mid(r, r['E'][je]['v']) or p >= th) else r['Edix']

def choose_theta(tr, S_in, tau, P_in):
    best = None
    for th in THETAS:
        e = np.mean([B.perr(r, 'E', ride_pick(r, B.gpick(r, 'E', S_in[r['id']], tau), P_in[r['id']], th)) for r in tr])
        if best is None or e < best[0]: best = (e, th)
    return best

def train_predict(tr, te, tr2, te2):
    """train on tr (rows) and predict te; *2 = same rows with candidate set v2"""
    djs = sorted({r['dj'] for r in tr}); o = {}
    P_in = {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]
        for r, p in zip(b, fit_ride(a)(b)): P_in[r['id']] = p
    ride = fit_ride(tr)(te)
    for tag, TR, TE in (('v1', tr, te), ('v2', tr2, te2)):
        (eE, ciE, tauE), S_in = inner_oof(TR, 'E'); th = choose_theta(TR, S_in, tauE, P_in)
        mE = B.fit(TR, 'E', False, B.CFGS[ciE]); SE = B.scores(mE, TE, 'E', False)
        o[tag] = dict(jg=[B.gpick(r, 'E', s, tauE) for r, s in zip(TE, SE)], jp=[int(np.argmax(s)) for s in SE], cfg=ciE, tau=tauE, theta=th[1], inner_exit=round(float(eE), 2), inner_ride=round(float(th[0]), 2))
        o[tag]['jr'] = [ride_pick(r, j, p, th[1]) for r, j, p in zip(TE, o[tag]['jg'], ride)]
    eC, ciC, tauC = B.inner(tr, 'C', False); mC = B.fit(tr, 'C', False, B.CFGS[ciC]); SC = B.scores(mC, te, 'C', False)
    jc = [B.gpick(r, 'C', s, tauC) for r, s in zip(te, SC)]; jcp = [int(np.argmax(s)) for s in SC]
    Xm = B.fitX(tr, False)(te)
    D = {}
    D['cueonly_gated'] = [B.decide(r, r['Edix'], c, r['dX']) for r, c in zip(te, jc)]
    D['ridegate'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, o['v1']['jr'], jc)]
    D['ridegate_cand2'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te2, o['v2']['jr'], jc)]
    D['ref_full_gated'] = [B.decide(r, j, c, X) for r, j, c, X in zip(te, o['v1']['jg'], jc, Xm)]
    D['ref_full_plain'] = [B.decide(r, j, c, X) for r, j, c, X in zip(te, o['v1']['jp'], jcp, Xm)]
    D['ref_cand2_full_gated'] = [B.decide(r, j, c, X) for r, j, c, X in zip(te2, o['v2']['jg'], jc, Xm)]
    D['default'] = [B.base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] = [B.base_decisions(r, 'rule_drop_exit') for r in te]
    mb, md = majority(tr, te); D['majority'] = md
    for k in D:
        for x, p in zip(D[k], ride): x['p_leave'] = round(float(p), 3)
    diag = dict(v1={k: o['v1'][k] for k in ('cfg', 'tau', 'theta', 'inner_exit', 'inner_ride')}, v2={k: o['v2'][k] for k in ('cfg', 'tau', 'theta', 'inner_exit', 'inner_ride')}, C=dict(cfg=ciC, tau=tauC), majority=mb)
    return D, diag

def tagpick(r, part, tag):
    return next((i for i, c in enumerate(r[part]) if tag in c['tags']), r[part + 'dix'])
def majority(tr, te):  # identical to picker_1124.majority
    best = {}
    for part, tags in (('E', B.ETAGS), ('C', B.CTAGS)):
        errs = {t: np.mean([B.perr(r, part, tagpick(r, part, t)) for r in tr]) for t in tags if t != 'grid'}
        best[part] = min(errs, key=errs.get)
    Xs = collections.Counter(16 if (r['pro_ov'] or 0) <= 14 else 32 for r in tr).most_common(1)[0][0]
    return best, [B.decide(r, tagpick(r, 'E', best['E']), tagpick(r, 'C', best['C']), Xs) for r in te]

def _fold(args):
    d, dev, dev2 = args
    tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]
    tr2 = [r for r in dev2 if r['dj'] != d]; te2 = [r for r in dev2 if r['dj'] == d]
    D, diag = train_predict(tr, te, tr2, te2); print('fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag

def coverage(rows, rows2):
    out = {}
    for nm, R in (('v1', rows), ('v2', rows2)):
        for part, pro in (('E', 'pro_out'), ('C', 'pro_in')):
            b = [min(abs(c['v'] - r[pro]) for c in r[part]) for r in R]
            out[f'{nm}_{part}'] = {f'within{t}': round(float(np.mean([x <= t for x in b])), 3) for t in (4, 8, 16)}
        mid = [r for r in R if is_mid(r, r['pro_out'])]
        out[f'{nm}_E_midpro_within8'] = round(float(np.mean([min(abs(c['v'] - r['pro_out']) for c in r['E']) <= 8 for r in mid])), 3)
    # how often the pro exit sits in outgoing drop 1 / pro cue at incoming drop 1 (drop-on-drop)
    ind1 = [r for r in rows if r['sa'].get('drops') and r['sa']['drops'][0][0] <= r['pro_out'] < r['sa']['drops'][0][1]]
    dod = [r for r in rows if r['sb'].get('drop1') and abs(r['pro_in'] - r['sb']['drop1']) <= 4]
    out['pro_exit_in_drop1_share'] = round(len(ind1) / len(rows), 3); out['pro_cue_drop_on_drop_share'] = round(len(dod) / len(rows), 3)
    return out

def strip(D): return {k: [dict(exit=x['exit'], cue=x['cue'], X=x['X'], is_default=bool(x.get('is_default')), p_leave=x.get('p_leave'), win=x.get('win')) for x in L] for k, L in D.items()}

if __name__ == '__main__':
    mode = sys.argv[1]
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    dev = [r for r in rows if r['set'] == 'dev']; dev2 = make_v2(dev); B.XM(dev, 'E', False); B.XM(dev, 'C', False)
    for q, r in zip(dev2, dev): q['XC0'] = r['XC0']
    if mode == 'cv':
        cov = coverage(dev, dev2); print('coverage', cov, flush=True)
        from concurrent.futures import ProcessPoolExecutor
        djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}; order = []; D = collections.defaultdict(list); folds = {}
        with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 4))) as ex:
            for d, ids, Dd, diag in ex.map(_fold, [(d, dev, dev2) for d in djs]):
                order += [byid[i] for i in ids]; folds[d] = diag
                for k, v in Dd.items(): D[k] += v
        res = B.summarize(order, dict(D))
        out = dict(n=len(order), n_mixes=len({r['mix'] for r in order}), n_djs=len(djs), coverage=cov, folds=folds, results=res,
                   per_pair=[dict(id=r['id'], dj=r['dj'], mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'], na=na_(r),
                                  **{k: v[i] for k, v in strip(D).items()}) for i, r in enumerate(order)])
        json.dump(out, open(os.path.join(H, 'picker_1125_cv.json'), 'w'), indent=1, default=str)
    elif mode == 'protrans':
        # window maps for rendering the frozen arms on the official 33 protrans pairs (trained on all dev; protrans never trained on)
        import run_admitted_tune as T
        te = [r for r in rows if r['set'] == 'protrans']; te2 = make_v2(te); D, diag = train_predict(dev, te, dev2, te2)
        recs = {r['id']: r for r in T.load_recs()}; out = dict(n=len(te), diag=diag, maps={})
        for arm in ('cueonly_gated', 'ridegate'):
            by_yt, by_id = {}, {}
            for r, x in zip(te, D[arm]):
                rec = recs.get(r['id']); key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
                by_id[r['id']] = dict(win=x.get('win'), exit=x['exit'], cue=x['cue'], X=x['X'], abstain=bool(x.get('is_default')), yt_key=key)
                if key and x.get('win') and not x.get('is_default'): by_yt[key] = x['win']
            mp = dict(written='2026-11-25 n1125', model=f'picker_1125 {arm} (style-free), trained on {len(dev)} dev, applied to the 33 protrans pairs', by_yt=by_yt, by_id=by_id,
                      do_not='write rules.json or treat this map as a promotion')
            dest = os.path.join(W, f'map_{arm}.json'); json.dump(mp, open(dest, 'w'), indent=1, default=str); out['maps'][arm] = dict(path=dest, n_windows=len(by_yt))
        out['results'] = {k: dict(abstain=round(float(np.mean([bool(x.get('is_default')) for x in L])), 3)) for k, L in D.items()}
        json.dump(out, open(os.path.join(H, 'picker_1125_protrans_maps.json'), 'w'), indent=1, default=str)
    else:
        te = [r for r in rows if r['set'] == 'fresh' and r['mix'] == FRESH_TONIGHT]; te2 = make_v2(te)
        print('fresh rows', len(te), flush=True)
        D, diag = train_predict(dev, te, dev2, te2)
        res = {k: dict(exit_cue=round(float(np.mean([(abs(x['exit'] - r['pro_out']) + abs(x['cue'] - r['pro_in'])) / 2 for x, r in zip(L, te)])), 2),
                       exit=round(float(np.mean([abs(x['exit'] - r['pro_out']) for x, r in zip(L, te)])), 2), cue=round(float(np.mean([abs(x['cue'] - r['pro_in']) for x, r in zip(L, te)])), 2),
                       abstain=round(float(np.mean([bool(x.get('is_default')) for x in L])), 3)) for k, L in D.items()}
        out = dict(mix=FRESH_TONIGHT, n=len(te), diag=diag, results=res, per_pair=[dict(id=r['id'], pro_out=r['pro_out'], pro_in=r['pro_in'], na=na_(r), **{k: v[i] for k, v in strip(D).items()}) for i, r in enumerate(te)])
        json.dump(out, open(os.path.join(H, 'picker_1125_fresh.json'), 'w'), indent=1, default=str)
    for n, s in out['results'].items(): print(n, {k: v for k, v in s.items() if not isinstance(v, dict)}, flush=True)
