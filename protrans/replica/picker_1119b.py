#!/usr/bin/env python3
"""Nightly 2026-11-19, iteration 2 (after the joint-window ranker's dev CI included 0 with renderable X in {16,32}):
FACTORED picker. Separate LambdaMART rankers for (1) the exit (incoming entry bar on the outgoing grid; 8-bar grid + rule
anchors: default exit, outro-intro, drop-1-end, later drop ends, breakdown) and (2) the cue (incoming start; phrase grid 0..80
+ section anchors: drop1-16/-32/-8, drop1, breakdown, drop2), each with its own margin gate vs the default's value (tau by inner
leave-one-DJ-out), and (3) blend length X in {16,32} from a small classifier (pro audible overlap > 14 bars). Labels =
acceptable sets (pro bar + section boundaries within 8 bars). Online style features (earlier transitions, index < t).
Same data, splits, baselines and bootstrap as picker_1119.py. usage: picker_1119b.py cv | protrans | holdout | fresh"""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1119 as P
import lightgbm as lgb
W = P.W

def exit_cands(r, dex):
    sa = r['sa']; na = int(sa.get('music_end') or sa.get('n_bars')); drops = [list(map(int, d)) for d in (sa.get('drops') or [])]
    C = {}
    for k in range(4, na // 8 + 1):
        s = 8 * k + 1
        if s + 16 - 1 <= na: C.setdefault(s, set()).add('grid')
    for X in (16, 32):
        C.setdefault((na // 8) * 8 - X + 1, set()).add('outro_intro')
        if drops: C.setdefault(P.ph(drops[0][1]) - X + 1, set()).add('drop_exit')
        for d in drops[1:]: C.setdefault(P.ph(d[1]) - X + 1, set()).add('dropN_exit')
        if sa.get('breakdown'): C.setdefault(P.ph(sa['breakdown']) + 8 - X + 1, set()).add('replica_bd')
    C.setdefault(dex, set()).add('default')
    return [dict(v=v, tags=t) for v, t in sorted(C.items()) if 1 <= v <= na or 'default' in t]

def cue_cands(r, dcue):
    sb = r['sb']; nb = int(sb.get('music_end') or sb.get('n_bars')); d1b = int(sb.get('drop1') or 0)
    C = {}
    for v in range(0, 81, 16): C.setdefault(v + 1, set()).add('grid')
    for v, t in ((d1b - 32, 'drop_m32'), (d1b - 16, 'drop_m16'), (d1b - 8, 'drop_m8'), (d1b, 'drop_cue'), (sb.get('breakdown'), 'bd'), (sb.get('drop2'), 'drop2')):
        if v is not None and v >= 0: C.setdefault(P.ph(v) + 1, set()).add(t)
    C.setdefault(dcue, set()).add('default')
    return [dict(v=v, tags=t) for v, t in sorted(C.items()) if v + 16 <= nb or 'default' in t]

ETAGS = ['default', 'outro_intro', 'drop_exit', 'dropN_exit', 'replica_bd', 'grid']; CTAGS = ['default', 'drop_m32', 'drop_m16', 'drop_m8', 'drop_cue', 'bd', 'drop2', 'grid']
def base_feats(r):
    sa, sb = r['sa'], r['sb']; na = float(sa.get('music_end') or sa.get('n_bars')); nb = float(sb.get('music_end') or sb.get('n_bars'))
    bb = sa.get('bass_by_section') or {}; bbb = sb.get('bass_by_section') or {}
    return [na, nb, len(sa.get('drops') or []), len(sb.get('drops') or []), sa.get('intro_len') or 0, sb.get('intro_len') or 0, na - (sa.get('outro_start') or na),
            float(sb.get('drop1') or 0), (bb.get('outro') or {}).get('bass', np.nan), (bbb.get('intro') or {}).get('bass', np.nan), (bb.get('breakdown') or {}).get('bass', np.nan)]
def style_feats(r):
    h = r['hist']
    return [h['n'], h['left'], h['mid'], h['cue_rel'], h['cue_in_drop'], h['ov']] if h else [0] + [np.nan] * 5
def fe_exit(r, c, style):
    sa = r['sa']; na = float(sa.get('music_end') or sa.get('n_bars')); drops = sa.get('drops') or []; x = c['v']; left = na - x
    v = [x, x / na, left, P.sec_at(sa, x), P.sec_at(sa, x + 15), P.ndist(x, [d[1] for d in drops]), P.ndist(x, [drops[0][1]] if drops else []),
         P.ndist(x, [sa.get('outro_start')]), P.ndist(x, [sa.get('breakdown')]), P.ndist(x, [d[0] for d in drops])] + [int(t in c['tags']) for t in ETAGS] + base_feats(r)
    if style:
        h = r['hist']; v += style_feats(r) + ([left - h['left'], float(left > 40) - h['mid']] if h else [np.nan, np.nan])
    return v
def fe_cue(r, c, style):
    sb = r['sb']; nb = float(sb.get('music_end') or sb.get('n_bars')); d1b = float(sb.get('drop1') or 0); x = c['v']
    v = [x, x / nb, x - d1b, P.sec_at(sb, x), P.ndist(x, [sb.get('breakdown'), sb.get('drop2')]), P.ndist(x, [sb.get('intro_end')])] + [int(t in c['tags']) for t in CTAGS] + base_feats(r)
    if style:
        h = r['hist']; v += style_feats(r) + ([(x - d1b) - h['cue_rel'], float(x - d1b >= -2) - h['cue_in_drop']] if h else [np.nan, np.nan])
    return v
def rel(err): return 4 if err <= 4 else 3 if err <= 8 else 2 if err <= 16 else 1 if err <= 32 else 0

def build(rows, D):
    for r in rows:
        d = D.get(r['id']); r['def_src'] = 'rendered' if d else 'proxy'
        if d: dex, dcue, dX = d['ours']['out_bar'], d['ours']['in_bar'], int(d['win'][4])
        else:
            oi = [c['win'] for c in r['feat_cands'] if c['type'] == 'outro_intro']; sa, sb = r['sa'], r['sb']
            w = oi[0] if oi else ['n', (int(sa.get('music_end')) // 8) * 8, None, max(0, int(sb.get('drop1') or 0) - 16), 16]
            dex, dcue, dX = w[1] - w[4] + 1, w[3] + 1, int(w[4])
        r['dex'], r['dcue'], r['dX'] = float(dex), float(dcue), dX
        r['E'] = exit_cands(r, r['dex']); r['C'] = cue_cands(r, r['dcue'])
        r['Erel'] = np.array([rel(P.acc_err(c['v'], r['pro_out'], P.bnd_a(r['sa']))) for c in r['E']])
        r['Crel'] = np.array([rel(P.acc_err(c['v'], r['pro_in'], P.bnd_b(r['sb']))) for c in r['C']])
        r['Edix'] = next(i for i, c in enumerate(r['E']) if 'default' in c['tags']); r['Cdix'] = next(i for i, c in enumerate(r['C']) if 'default' in c['tags'])
    return rows

def XM(rs, part, style):
    k = f'X{part}{int(style)}'
    for r in rs:
        if k not in r: r[k] = np.array([(fe_exit if part == 'E' else fe_cue)(r, c, style) for c in r[part]], float)
    return np.vstack([r[k] for r in rs])
CFGS = [dict(n=150, leaves=7, mcs=20), dict(n=300, leaves=15, mcs=40)]
TAUS = [-1e9, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 1e9]
def fit(rs, part, style, cfg):
    m = lgb.LGBMRanker(objective='lambdarank', n_estimators=cfg['n'], num_leaves=cfg['leaves'], learning_rate=0.05, min_child_samples=cfg['mcs'], subsample=0.8,
                       subsample_freq=1, colsample_bytree=0.8, random_state=20261119, verbose=-1, n_jobs=1)
    m.fit(XM(rs, part, style), np.concatenate([r[part + 'rel'] for r in rs]), group=[len(r[part]) for r in rs]); return m
def scores(m, rs, part, style): return [m.predict(XM([r], part, style)) for r in rs]
def gpick(r, part, s, tau):
    j = int(np.argmax(s)); d = r[part + 'dix']; return j if s[j] - s[d] > tau else d
def perr(r, part, j): return abs(r[part][j]['v'] - (r['pro_out'] if part == 'E' else r['pro_in']))
def inner(tr, part, style):
    djs = sorted({r['dj'] for r in tr}); best = None
    for ci, cfg in enumerate(CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]; m = fit(a, part, style, cfg)
            for r, s in zip(b, scores(m, b, part, style)): S[r['id']] = s
        for t in TAUS:
            e = np.mean([perr(r, part, gpick(r, part, S[r['id']], t)) for r in tr])
            if best is None or e < best[0]: best = (e, ci, t)
    return best
OVF = lambda r, style: base_feats(r) + (style_feats(r) if style else [])
def fitX(tr, style):
    y = np.array([float((r['pro_ov'] or 0) > 14) for r in tr]); X = np.array([OVF(r, style) for r in tr], float)
    if len(set(y)) < 2: return lambda rs: [16 if y[0] == 0 else 32] * len(rs)
    m = lgb.LGBMClassifier(n_estimators=100, num_leaves=7, learning_rate=0.05, min_child_samples=10, verbose=-1, n_jobs=1, random_state=20261119).fit(X, y)
    return lambda rs: [32 if p > 0.5 else 16 for p in m.predict_proba(np.array([OVF(r, style) for r in rs], float))[:, 1]]

def window(r, ex, cue, X):
    """renderable window from the chosen exit / cue / X: e = exit + X - 1 on the 8-grid, ib = cue - 1; X=32 falls back to 16 if illegal"""
    na = int(r['sa'].get('music_end') or r['sa'].get('n_bars')); nb = int(r['sb'].get('music_end') or r['sb'].get('n_bars'))
    for XX in ((X, 16) if X == 32 else (X,)):
        e = int(round((ex + XX - 1) / 8) * 8); ib = int(round(cue - 1))
        if e <= na and e - XX >= 16 and ib >= 0 and ib + XX <= nb - 16: return ['n', e, None, ib, XX]
    return None

def decide(r, je, jc, X):
    """final decision for a pair; exactly the default window when both parts abstain"""
    if je == r['Edix'] and jc == r['Cdix'] and X == r['dX']: return dict(exit=r['dex'], cue=r['dcue'], X=r['dX'], win=None, is_default=True)
    w = window(r, r['E'][je]['v'], r['C'][jc]['v'], X)
    if w is None: return dict(exit=r['dex'], cue=r['dcue'], X=r['dX'], win=None, is_default=True, why='illegal')
    return dict(exit=float(w[1] - w[4] + 1), cue=float(w[3] + 1), X=w[4], win=w, is_default=False)

def run_part(tr, te, style):
    out = {}
    for part in ('E', 'C'):
        e, ci, tau = inner(tr, part, style); m = fit(tr, part, style, CFGS[ci]); S = scores(m, te, part, style)
        out[part] = dict(g=[gpick(r, part, s, tau) for r, s in zip(te, S)], p=[int(np.argmax(s)) for s in S], cfg=ci, tau=tau, inner=round(float(e), 2), model=m)
    out['X'] = fitX(tr, style)(te); return out

def _fold(args):
    d, dev = args; tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]; res = {}
    for style in (True, False):
        o = run_part(tr, te, style); nm = 'style' if style else 'nostyle'
        res[nm] = dict(g=[decide(r, je, jc, X) for r, je, jc, X in zip(te, o['E']['g'], o['C']['g'], o['X'])],
                       p=[decide(r, je, jc, X) for r, je, jc, X in zip(te, o['E']['p'], o['C']['p'], o['X'])],
                       diag={k: {kk: o[k][kk] for kk in ('cfg', 'tau', 'inner')} for k in ('E', 'C')})
    print('fold', d, {k: v['diag'] for k, v in res.items()}, flush=True)
    return d, [r['id'] for r in te], res

def base_decisions(r, kind):
    if kind == 'default': return dict(exit=r['dex'], cue=r['dcue'], X=r['dX'], is_default=True)
    if kind == 'rule_drop_exit':
        je = next((i for i, c in enumerate(r['E']) if 'drop_exit' in c['tags']), r['Edix']); jc = next((i for i, c in enumerate(r['C']) if 'drop_m16' in c['tags']), r['Cdix'])
        return decide(r, je, jc, 16)
def summarize(rs, D):
    """D: name -> list of decision dicts aligned with rs"""
    res = {}
    for n, L in D.items():
        e = [abs(x['exit'] - r['pro_out']) for x, r in zip(L, rs)]; c = [abs(x['cue'] - r['pro_in']) for x, r in zip(L, rs)]
        ea = [P.acc_err(x['exit'], r['pro_out'], P.bnd_a(r['sa'])) for x, r in zip(L, rs)]; ca = [P.acc_err(x['cue'], r['pro_in'], P.bnd_b(r['sb'])) for x, r in zip(L, rs)]
        ov = {16: 10.0, 32: 18.0}; bl = [abs(ov.get(x['X'], 10.0) - r['pro_ov']) for x, r in zip(L, rs) if r['pro_ov'] is not None]
        s = dict(n=len(rs), exit_mean=round(float(np.mean(e)), 2), cue_mean=round(float(np.mean(c)), 2), exit_cue_mean=round(float(np.mean([(a + b) / 2 for a, b in zip(e, c)])), 2),
                 exit_median=round(float(np.median(e)), 1), cue_median=round(float(np.median(c)), 1), blendlen_proxy_err_mean=round(float(np.mean(bl)), 2),
                 changed_vs_default=int(sum(not x.get('is_default') for x in L)), abstain_rate=round(float(np.mean([bool(x.get('is_default')) for x in L])), 3))
        for t in (4, 8, 16):
            s[f'exit_hit{t}'] = round(float(np.mean([v <= t for v in e])), 3); s[f'cue_hit{t}'] = round(float(np.mean([v <= t for v in c])), 3)
            s[f'exit_acc_hit{t}'] = round(float(np.mean([v <= t for v in ea])), 3); s[f'cue_acc_hit{t}'] = round(float(np.mean([v <= t for v in ca])), 3)
        s['_v'] = dict(exit=e, cue=c, exit_cue=[(a + b) / 2 for a, b in zip(e, c)], exit_acc=ea, cue_acc=ca, bl=[abs({16: 10.0, 32: 18.0}.get(x['X'], 10.0) - (r['pro_ov'] if r['pro_ov'] is not None else 10.0)) for x, r in zip(L, rs)])
        res[n] = s
    g = [r['mix'] for r in rs]; R = res['default']['_v']
    for n, s in res.items():
        if n == 'default': continue
        s['delta_vs_default'] = {k: P.boot(g, R[k], s['_v'][k]) for k in ('exit', 'cue', 'exit_cue', 'exit_acc', 'cue_acc', 'bl')}
        for t in (8, 16):
            for k in ('exit', 'cue'):
                hd = P.boot(g, [float(v <= t) for v in R[k]], [float(v <= t) for v in s['_v'][k]]); hd['verdict'] = 'better' if hd['ci'][0] > 0 else ('worse' if hd['ci'][1] < 0 else 'no clear difference')
                s[f'delta_{k}_hit{t}'] = hd
    for s in res.values(): s.pop('_v')
    return res

def run_cv(rows):
    from concurrent.futures import ProcessPoolExecutor
    dev = [r for r in rows if r['set'] == 'dev']; djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}
    for st in (True, False): XM(dev, 'E', st); XM(dev, 'C', st)
    order = []; D = collections.defaultdict(list); folds = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 5))) as ex:
        for d, ids, res in ex.map(_fold, [(d, dev) for d in djs]):
            te = [byid[i] for i in ids]; order += te; folds[d] = {k: v['diag'] for k, v in res.items()}
            for nm in ('style', 'nostyle'):
                D[f'model_{nm}_gated'] += res[nm]['g']; D[f'model_{nm}_plain'] += res[nm]['p']
            D['default'] += [base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] += [base_decisions(r, 'rule_drop_exit') for r in te]
    # majority choice baseline: the single generator tag (exit tag x cue tag) with the lowest mean train error, fit leave-one-DJ-out
    for d in djs:
        pass
    res = summarize(order, dict(D))
    return dict(n=len(order), n_mixes=len({r['mix'] for r in order}), def_src=dict(collections.Counter(r['def_src'] for r in order)), folds=folds, results=res,
                per_pair=[dict(id=r['id'], dj=r['dj'], mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'],
                               style_gated={k: v for k, v in D['model_style_gated'][i].items()}) for i, r in enumerate(order)])

def run_final(rows, which):
    dev = [r for r in rows if r['set'] == 'dev']; te = [r for r in rows if r['set'] == which]; D = {}; diag = {}
    for style in (True, False):
        o = run_part(dev, te, style); nm = 'style' if style else 'nostyle'
        D[f'model_{nm}_gated'] = [decide(r, je, jc, X) for r, je, jc, X in zip(te, o['E']['g'], o['C']['g'], o['X'])]
        D[f'model_{nm}_plain'] = [decide(r, je, jc, X) for r, je, jc, X in zip(te, o['E']['p'], o['C']['p'], o['X'])]
        diag[nm] = {k: {kk: o[k][kk] for kk in ('cfg', 'tau', 'inner')} for k in ('E', 'C')}
        if style:
            for k in ('E', 'C'): o[k]['model'].booster_.save_model(os.path.join(W, f'picker_1119b_{k}.txt'))
    D['default'] = [base_decisions(r, 'default') for r in te]; D['rule_drop_exit'] = [base_decisions(r, 'rule_drop_exit') for r in te]
    res = summarize(te, D)
    return dict(set=which, n=len(te), mixes=sorted({r['mix'] for r in te}), def_src=dict(collections.Counter(r['def_src'] for r in te)), diag=diag, results=res,
                per_pair=[dict(id=r['id'], mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], dex=r['dex'], dcue=r['dcue'], dX=r['dX'], style_gated=D['model_style_gated'][i],
                               nostyle_gated=D['model_nostyle_gated'][i]) for i, r in enumerate(te)])

if __name__ == '__main__':
    mode = sys.argv[1]; rows = build(P.rows_all(), P.load_rendered_defaults())
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    out = run_cv(rows) if mode == 'cv' else run_final(rows, mode)
    json.dump(out, open(os.path.join(H, f'picker_1119b_{mode}.json'), 'w'), indent=1, default=str)
    for n, s in out['results'].items():
        d = s.get('delta_vs_default', {})
        f = lambda k: (d.get(k) or {}).get('delta'), lambda k: (d.get(k) or {}).get('ci')
        print(f"{n:20s} exit {s['exit_mean']} cue {s['cue_mean']} ec {s['exit_cue_mean']} dEC {f[0]('exit_cue')} {f[1]('exit_cue')} dExit {f[0]('exit')} {f[1]('exit')} dCue {f[0]('cue')} {f[1]('cue')} "
              f"e@16 {s['exit_hit16']} c@16 {s['cue_hit16']} e@8 {s['exit_hit8']} c@8 {s['cue_hit8']} bl {s['blendlen_proxy_err_mean']} abstain {s['abstain_rate']}")
