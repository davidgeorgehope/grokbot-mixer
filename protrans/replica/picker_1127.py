#!/usr/bin/env python3
"""Nightly 2026-11-27 (n1127): frozen model-picker arms (promotion_criteria.json frozen_arms_n1127, written before eval).
Reuses picker_1125 / picker_1119b unchanged (features, LambdaMART rankers, margin gate, ride-vs-leave gate). Baseline = ridegate
(the engine default since 11-26). Arms:
  rg_cond (PRIMARY): two-stage. ride-vs-leave classifier; if p_leave >= theta (nested), a SEPARATE LambdaMART ranker trained only on
    pairs where the pro left mid-track, over mid-track candidates only, picks where to leave; else ride fallback = stage-A gated pick if
    it is not mid-track, else default. Cue = ridegate cue model, blend length default.
  rg_ctx (SECONDARY): ridegate + live-usable mix-context features (CTX) in ride classifier and exit ranker.
  rg_cond_ctx (SECONDARY): rg_cond + CTX.
  rg_online_tf (DIAGNOSTIC): ride gate also sees the pro's strictly earlier transitions in the same mix.
CTX (no pro decisions): transition index, tracklist-length proxy (max accepted idx + 1), idx fraction, bpm a / b / ratio, mean outgoing
track length of strictly earlier transitions in the same mix and this track's length relative to it.
ITERATION arms (registered 2:05 AM after the frozen arms lost on dev, before any fresh scoring; cannot count as frozen tonight):
  rg_where: ridegate decides WHETHER to leave mid-track (unchanged); when it leaves, the stage-B leave-only ranker decides WHERE.
  rg_where_ctx: same with CTX features (ride gate, stage A and stage B).
usage: picker_1127.py cv | fresh"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1125 as Q
import picker_1126 as R1
P, B = Q.P, Q.B
import lightgbm as lgb
W = os.path.join(H, 'nightly_1127_work'); os.makedirs(W, exist_ok=True)
FRESH_ALL = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
FRESH_TONIGHT = 'alpha_rhythm_3k9pyJDKytE'; assert FRESH_TONIGHT in FRESH_ALL
P.W = W; B.W = W; Q.W = W; R1.W = W; P.SPENT_FRESH = FRESH_ALL
EXCL_DJ = {'Liquicity Events'}
SEED = 20261127
THETAS = [0.4, 0.5, 0.6, 0.7, 0.8]

def add_ctx(rows):
    by = collections.defaultdict(list)
    for r in rows: by[(r['src'], r['mix'])].append(r)
    for r in rows:
        g = by[(r['src'], r['mix'])]; n = max(q['idx'] for q in g) + 1
        past = [Q.na_(q) for q in g if q['idx'] < r['idx']]; pm = float(np.mean(past)) if past else np.nan
        ba, bb = [float(x) if x else np.nan for x in (r.get('bpm') or (None, None))]
        r['CTX'] = [r['idx'], n, r['idx'] / max(1, n - 1), ba, bb, bb / ba if ba and bb else np.nan, pm, Q.na_(r) / pm if past else np.nan]

def with_ctx(rows):
    out = []
    for r in rows:
        q = dict(r); q['XE0'] = np.hstack([r['XE0'], np.tile(np.array(r['CTX'], float), (len(r['E']), 1))]); out.append(q)
    return out

RIDEF_C = lambda r: Q.RIDEF(r) + r['CTX']
RIDEF_TF = lambda r: Q.RIDEF(r) + B.style_feats(r)
def fit_clf(tr, F):
    y = np.array([float(Q.is_mid(r, r['pro_out'])) for r in tr]); X = np.array([F(r) for r in tr], float)
    m = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=1, random_state=SEED).fit(X, y)
    return lambda rs: m.predict_proba(np.array([F(r) for r in rs], float))[:, 1]

def midsub(r):
    """stage-B view: only mid-track exit candidates (None if there are none)"""
    ii = [i for i, c in enumerate(r['E']) if Q.is_mid(r, c['v'])]
    if not ii: return None, ii
    q = dict(r); q['E'] = [r['E'][i] for i in ii]; q['XE0'] = r['XE0'][ii]; q['Erel'] = r['Erel'][ii]; q.pop('Edix', None); return q, ii

def fit_B(tr, cfg):
    L = [midsub(r)[0] for r in tr if Q.is_mid(r, r['pro_out'])]; L = [q for q in L if q is not None]
    return B.fit(L, 'E', False, cfg)
def pick_B(m, r):
    q, ii = midsub(r)
    if q is None: return None
    return ii[int(np.argmax(B.scores(m, [q], 'E', False)[0]))]

def ride_fb(r, jA): return jA if not Q.is_mid(r, r['E'][jA]['v']) else r['Edix']
def cond_pick(r, jA, jB, p, th): return jB if (jB is not None and p >= th) else ride_fb(r, jA)

def ridegate_block(TR, TE, F, djs):
    """stage A (= ridegate) and stage B, all settings by inner leave-one-DJ-out on TR"""
    P_in, SB_in = {}, {}
    (eE, ciE, tauE), S_in = Q.inner_oof(TR, 'E')
    for d in djs:
        a = [r for r in TR if r['dj'] != d]; b = [r for r in TR if r['dj'] == d]
        for r, p in zip(b, fit_clf(a, F)(b)): P_in[r['id']] = p
        mb = fit_B(a, B.CFGS[0])
        for r in b: SB_in[r['id']] = pick_B(mb, r)
    jA_in = {r['id']: B.gpick(r, 'E', S_in[r['id']], tauE) for r in TR}
    # ridegate theta (same rule as n1126: Q.ride_pick over Q.THETAS)
    thR = min(((np.mean([B.perr(r, 'E', Q.ride_pick(r, jA_in[r['id']], P_in[r['id']], th)) for r in TR]), th) for th in Q.THETAS))
    thC = min(((np.mean([B.perr(r, 'E', cond_pick(r, jA_in[r['id']], SB_in[r['id']], P_in[r['id']], th)) for r in TR]), th) for th in THETAS))
    mE = B.fit(TR, 'E', False, B.CFGS[ciE]); SE = B.scores(mE, TE, 'E', False); ride = fit_clf(TR, F)(TE); mB = fit_B(TR, B.CFGS[0])
    jA = [B.gpick(r, 'E', s, tauE) for r, s in zip(TE, SE)]; jB = [pick_B(mB, r) for r in TE]
    jR = [Q.ride_pick(r, j, p, thR[1]) for r, j, p in zip(TE, jA, ride)]
    jC = [cond_pick(r, a, b, p, thC[1]) for r, a, b, p in zip(TE, jA, jB, ride)]
    jW = [b if (j != r['Edix'] and Q.is_mid(r, r['E'][j]['v']) and b is not None) else j for r, j, b in zip(TE, jR, jB)]
    diag = dict(cfg=ciE, tau=tauE, theta_ride=thR[1], theta_cond=thC[1], inner_ride=round(float(thR[0]), 2), inner_cond=round(float(thC[0]), 2))
    return jR, jC, jW, ride, diag

def train_predict(tr, te):
    djs = sorted({r['dj'] for r in tr}); trC, teC = with_ctx(tr), with_ctx(te)
    jR, jC, jW, ride, d0 = ridegate_block(tr, te, Q.RIDEF, djs)
    jRc, jCc, jWc, ridec, d1 = ridegate_block(trC, teC, RIDEF_C, djs)
    # diagnostic: teacher-forced style in the ride gate (stage A unchanged)
    P_tf = {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]
        for r, p in zip(b, fit_clf(a, RIDEF_TF)(b)): P_tf[r['id']] = p
    (eE, ciE, tauE), S_in = Q.inner_oof(tr, 'E'); thT = Q.choose_theta(tr, S_in, tauE, P_tf)
    mE = B.fit(tr, 'E', False, B.CFGS[ciE]); SE = B.scores(mE, te, 'E', False); rtf = fit_clf(tr, RIDEF_TF)(te)
    jT = [Q.ride_pick(r, B.gpick(r, 'E', s, tauE), p, thT[1]) for r, s, p in zip(te, SE, rtf)]
    eC, ciC, tauC = B.inner(tr, 'C', False); mC = B.fit(tr, 'C', False, B.CFGS[ciC]); SC = B.scores(mC, te, 'C', False)
    jc = [B.gpick(r, 'C', s, tauC) for r, s in zip(te, SC)]
    D = {}
    D['ridegate'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jR, jc)]
    D['rg_cond'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jC, jc)]
    D['rg_ctx'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jRc, jc)]
    D['rg_cond_ctx'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jCc, jc)]
    D['rg_where'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jW, jc)]
    D['rg_where_ctx'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jWc, jc)]
    D['rg_online_tf'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, jT, jc)]
    D['default'] = [B.base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] = [B.base_decisions(r, 'rule_drop_exit') for r in te]
    mb, md = Q.majority(tr, te); D['majority'] = md
    for k in D:
        for x, p, q, s in zip(D[k], ride, ridec, rtf): x['p_leave'] = round(float(p), 3); x['p_leave_ctx'] = round(float(q), 3); x['p_leave_tf'] = round(float(s), 3)
    return D, dict(plain=d0, ctx=d1, tf_theta=thT[1], C=dict(cfg=ciC, tau=tauC), majority=mb)

def _fold(args):
    d, dev = args; tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]
    D, diag = train_predict(tr, te); print('fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag

def strip(D): return {k: [dict(exit=x['exit'], cue=x['cue'], X=x['X'], is_default=bool(x.get('is_default')), p_leave=x.get('p_leave'), p_leave_ctx=x.get('p_leave_ctx'), p_leave_tf=x.get('p_leave_tf'), win=x.get('win')) for x in L] for k, L in D.items()}
def pp_rows(rs, D): return [dict(id=r['id'], dj=r['dj'], mix=r['mix'], idx=r['idx'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'], na=Q.na_(r),
                                    sec_out=P.sec_at(r['sa'], r['pro_out']), **{k: v[i] for k, v in strip(D).items()}) for i, r in enumerate(rs)]

if __name__ == '__main__':
    mode = sys.argv[1]
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    for r in rows:
        if r['dj'] in EXCL_DJ and r['set'] == 'dev': r['set'] = 'excluded'
    add_ctx(rows)
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    dev = [r for r in rows if r['set'] == 'dev']; B.XM(dev, 'E', False); B.XM(dev, 'C', False)
    if mode == 'cv':
        cov = R1.coverage(dev, R1.make_tail(dev)); cov.update({k: v for k, v in Q.coverage(dev, Q.make_v2(dev)).items() if 'share' in k or k.startswith('v2')}); print('coverage', cov, flush=True)
        from concurrent.futures import ProcessPoolExecutor
        djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}; order = []; D = collections.defaultdict(list); folds = {}
        with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 3))) as ex:
            for d, ids, Dd, diag in ex.map(_fold, [(d, dev) for d in djs]):
                order += [byid[i] for i in ids]; folds[d] = diag
                for k, v in Dd.items(): D[k] += v
        out = dict(n=len(order), n_mixes=len({r['mix'] for r in order}), n_djs=len(djs), coverage=cov, folds=folds, per_pair=pp_rows(order, D))
        json.dump(out, open(os.path.join(W, 'picker_1127_cv.json'), 'w'), indent=1, default=str)
    else:
        te = [r for r in rows if r['set'] == 'fresh' and r['mix'] == FRESH_TONIGHT]
        B.XM(te, 'E', False); B.XM(te, 'C', False); print(mode, 'rows', len(te), flush=True)
        D, diag = train_predict(dev, te)
        out = dict(set=mode, n=len(te), mixes=sorted({r['mix'] for r in te}), diag=diag, per_pair=pp_rows(te, D))
        json.dump(out, open(os.path.join(W, f'picker_1127_{mode}.json'), 'w'), indent=1, default=str)
    print('DONE', mode, flush=True)
