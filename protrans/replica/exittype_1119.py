#!/usr/bin/env python3
"""2026-11-19 (day): TWO-STAGE exit-type picker (docs/NIGHTLY_2026-11-19.md "next idea"). DEV ONLY: the locked
Liquicity/Hospital holdout, protrans-33 and spent fresh mixes are never loaded into training or scoring here.
Stage 1: calibrated classifier P(mid) = P(pro exits >= 32 bars before the outgoing track's music end), from pair features
  (section structure, per-bar energy/bass curves, roughness of the mid vs late windows, track lengths, BPM, key distance)
  plus, for the style version only, online DJ-style features from earlier transitions of the same mix (index < t).
  Model family (LightGBM / L2 logistic) and calibration (Platt / isotonic) chosen by inner leave-one-DJ-out (nested).
Stage 2: expected-cost choice of the exit type: choose mid iff p*C[m,m] + (1-p)*C[m,l] < p*C[l,m] + (1-p)*C[l,l], with C
  the inner-OOF mean exit-bar error of the within-type pick; then picker_1119b's exit ranker places the bar inside the chosen
  type and picker_1119b's cue ranker + X classifier are unchanged. Rules only generate candidates; hard checks only veto (later).
Variants: cost rule ('cost'), threshold tuned on inner OOF ('thr'), cost rule + abstention band to the default tuned on inner
  OOF ('abst'), oracle type (ceiling, not a policy). usage: exittype_1119.py cv"""
import json, os, sys, math, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P0), 'src2')
sys.path.insert(0, H); sys.path.insert(0, SRC2)
import picker_1119 as P, picker_1119b as B
if os.environ.get('EXTDEV') == '1': P.W = os.path.join(H, 'exittype_1119_work', 'ext')  # extended corpus_v2 snapshot (2026-11-19 7 AM); same holdout/fresh tagging
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
WK = os.path.join(H, 'exittype_1119_work'); TF = json.load(open(os.path.join(WK, 'trackfeat.json'))) if os.path.exists(os.path.join(WK, 'trackfeat.json')) else {}
MID = 32
def NA(s): return int(s.get('music_end') or s.get('n_bars'))
def is_mid(r): return float(NA(r['sa']) - r['pro_out'] >= MID)
_ST = {}
def st(yt):
    if yt not in _ST:
        p = os.path.join(SRC2, 'st', yt + '.json'); _ST[yt] = json.load(open(p)).get('bar') if os.path.exists(p) else None
        if _ST[yt] and 'bass' not in _ST[yt]: _ST[yt]['bass'] = _ST[yt].get('low')
    return _ST[yt]
def mseg(v, a, b):
    if v is None: return np.nan
    a, b = max(0, int(a)), min(len(v), int(b))
    return float(np.mean(v[a:b])) if b > a else np.nan
def cam(k):
    try: return int(k[:-1]), k[-1]
    except Exception: return None
def camdist(a, b):
    a, b = cam(a or ''), cam(b or '')
    if not a or not b: return np.nan
    d = abs(a[0] - b[0]) % 12; d = min(d, 12 - d); return d + (a[1] != b[1]) * 0.5

def rough(r):
    """log roughness ratio, mid window (16 bars ending at drop-1 end, cue at default) vs the default (late) window"""
    import consonance as CO
    ya, yb = r['ya'], r['yb']
    if not (TF.get(ya, {}).get('peaks') and TF.get(yb, {}).get('peaks')): return [np.nan, np.nan, np.nan]
    sa = r['sa']; drops = sa.get('drops') or []; ib = int(r['dcue'] - 1)
    if not drops: return [np.nan, np.nan, np.nan]
    e1 = P.ph(drops[0][1]); dw = ['n', int(r['dex'] + r['dX'] - 1), None, ib, int(r['dX'])]; mw = ['n', e1, None, ib, 16]
    try: rd = CO.win_roughness(ya, yb, dw); rm = CO.win_roughness(ya, yb, mw)
    except Exception: return [np.nan, np.nan, np.nan]
    if not rd or not rm: return [np.nan, np.nan, np.nan]
    return [rm, rd, math.log(rm / rd)]

def pair_feats(r):
    sa, sb = r['sa'], r['sb']; na, nb = NA(sa), NA(sb); drops = [list(map(int, d)) for d in (sa.get('drops') or [])]
    d1e = drops[0][1] if drops else np.nan; lde = drops[-1][1] if drops else np.nan
    A = st(r['ya']); Bc = st(r['yb'])
    ab = A['bass'] if A else None; aa = A['all'] if A else None; bb = Bc['bass'] if Bc else None; ball = Bc['all'] if Bc else None
    dropb = mseg(ab, drops[0][0], drops[0][1]) if drops else np.nan
    f = [na, nb, len(drops), len(sb.get('drops') or []), d1e, na - d1e, lde, na - lde, (na - d1e) / na if drops else np.nan,
         na - (sa.get('outro_start') or na), float(sa.get('breakdown') or np.nan), float(bool(sa.get('drop2'))), float(sb.get('drop1') or 0), sb.get('intro_len') or 0,
         nb - (sb.get('outro_start') or nb)]
    f += B.base_feats(r)[8:]  # section bass levels
    f += [mseg(ab, na - 32, na) - dropb, mseg(ab, d1e, d1e + 32) - dropb if drops else np.nan, mseg(aa, na - 32, na) - mseg(aa, na - 64, na - 32),
          mseg(aa, na - 64, na) - mseg(aa, d1e - 32, d1e) if drops else np.nan, mseg(bb, 0, 16), mseg(bb, 0, 32) - mseg(bb, 32, 64), mseg(ball, 0, 16),
          float(A is not None)]
    f += rough(r)
    ba, bbp = r['bpm']; f += [ba or np.nan, bbp or np.nan, (ba - bbp) if (ba and bbp) else np.nan]
    ka, kb = TF.get(r['ya'], {}), TF.get(r['yb'], {})
    f += [camdist(ka.get('key'), kb.get('key')), ka.get('key_strength', np.nan), kb.get('key_strength', np.nan)]
    return f
def style_extra(r):
    h = r['hist']; past = r['past']
    if not past: return [0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]
    last = past[-1]; m = [is_mid(q) for q in past]; w = np.array([0.5 ** (len(m) - 1 - i) for i in range(len(m))])
    return [h['n'], h['left'], h['mid'], h['ov'], is_mid(last), float(NA(last['sa']) - last['pro_out']), float(np.dot(w, m) / w.sum())]
def track_proxy(r):
    """audio/structure-derived per-pair content proxy (no pro decisions): A drop-1 length and bass, A outro length,
    A breakdown depth (bass dB drop vs drop), B intro length"""
    sa, sb = r['sa'], r['sb']; na = NA(sa); drops = sa.get('drops') or []; bb = sa.get('bass_by_section') or {}
    dl = (drops[0][1] - drops[0][0]) if drops else np.nan; db = (bb.get('drop') or {}).get('bass', np.nan)
    bd = db - (bb.get('breakdown') or {}).get('bass', np.nan) if bb.get('breakdown') else np.nan
    return [dl, db, na - (sa.get('outro_start') or na), bd, float(sb.get('intro_len') or 0), na - (drops[0][1] if drops else na)]
def mixagg(r):
    """style proxy from the whole playlist's content (known before the mix is built, also for the listener's own mixes):
    mix-mean of track_proxy over all pairs of the same mix; no pro decisions are used"""
    M = np.array([track_proxy(q) for q in r['mixrows']], float)
    with np.errstate(all='ignore'): return list(np.nanmean(M, 0)) + [float(len(r['mixrows']))]
def FX(r, style):
    k = 'F%d' % style
    if k not in r:
        f = pair_feats(r)
        if os.environ.get('FEATS') == 'struct':  # drop audio-derived features (curves, roughness, key): 29% of pairs lack local audio, unevenly by DJ
            f = [v for i, v in enumerate(f) if not (18 <= i <= 28 or 32 <= i <= 34)]
        if os.environ.get('MIXAGG') == '1': f = f + mixagg(r)
        r[k] = f + (style_extra(r) if style else [])
    return r[k]

# ---- stage 1 ------------------------------------------------------------------------------------------
MODELS = ['lgb', 'logit', 'const']
BETA = [f'beta_{a}_{dc}' for a in (0.5, 1, 2, 4) for dc in (1.0, 0.7, 0.4)]  # online beta-binomial mode prior (style only)
def models(style): return MODELS + (BETA + ['logit_style'] if style and os.environ.get('BETA', '1') == '1' else []) + (['student'] if not style and os.environ.get('STUDENT') == '1' else [])  # const = training base rate (lets nesting say 'features add nothing')
def fit_raw(rs, style, kind):
    X = np.array([FX(r, style) for r in rs], float); y = np.array([is_mid(r) for r in rs])
    if len(set(y)) < 2 or kind == 'const': c = float(y.mean()); return lambda q: np.full(len(q), c)
    if kind.startswith('beta_'):
        _, a, dc = kind.split('_'); a, dc = float(a), float(dc); m0 = float(y.mean())
        def pb(q):
            out = []
            for r in q:
                m = [is_mid(x) for x in r['past']]; w = np.array([dc ** (len(m) - 1 - i) for i in range(len(m))])
                out.append((float(np.dot(w, m)) + a * m0) / (float(w.sum()) + a) if m else m0)
            return np.array(out)
        return pb
    if kind == 'student':  # teacher/student: soft labels from the online style teacher (beta prior over earlier pro exits, training rows only)
        m0 = float(y.mean()); t = []
        for r in rs:
            m = [is_mid(x) for x in r['past']]; t.append((sum(m) + 0.5 * m0) / (len(m) + 0.5) if m else m0)
        t = np.array(t); Xn = np.array([FX(r, False) for r in rs], float)
        mr = lgb.LGBMRegressor(n_estimators=150, num_leaves=4, learning_rate=0.05, min_child_samples=10, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                               verbose=-1, n_jobs=1, random_state=20261119).fit(Xn, t)
        return lambda q: np.clip(mr.predict(np.array([FX(r, False) for r in q], float)), 0.01, 0.99)
    if kind == 'logit_style':  # style features only (lower dimension)
        Xs = np.array([style_extra(r) for r in rs], float); med = np.nanmedian(Xs, 0); med = np.where(np.isnan(med), 0, med)
        Xi = np.where(np.isnan(Xs), med, Xs); mu, sd = Xi.mean(0), Xi.std(0) + 1e-9; m = LogisticRegression(C=0.3, max_iter=2000).fit((Xi - mu) / sd, y)
        def pl(q):
            Q = np.array([style_extra(r) for r in q], float); Q = np.where(np.isnan(Q), med, Q); return m.predict_proba((Q - mu) / sd)[:, 1]
        return pl
    if kind == 'lgb':
        m = lgb.LGBMClassifier(n_estimators=120, num_leaves=4, learning_rate=0.05, min_child_samples=10, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                               reg_lambda=1.0, verbose=-1, n_jobs=1, random_state=20261119).fit(X, y)
        return lambda q: m.predict_proba(np.array([FX(r, style) for r in q], float))[:, 1]
    med = np.nanmedian(X, 0); med = np.where(np.isnan(med), 0, med); Xi = np.where(np.isnan(X), med, X); mu, sd = Xi.mean(0), Xi.std(0) + 1e-9
    m = LogisticRegression(C=0.3, max_iter=2000).fit((Xi - mu) / sd, y)
    def pr(q):
        Q = np.array([FX(r, style) for r in q], float); Q = np.where(np.isnan(Q), med, Q); return m.predict_proba((Q - mu) / sd)[:, 1]
    return pr
def calibrator(p, y, kind):
    if kind == 'none': return lambda q: np.asarray(q, float)
    p = np.clip(np.asarray(p), 1e-4, 1 - 1e-4); y = np.asarray(y)
    if len(set(y)) < 2: return lambda q: np.full(len(q), float(y.mean()))
    if kind == 'iso':
        ir = IsotonicRegression(y_min=0.02, y_max=0.98, out_of_bounds='clip').fit(p, y); return lambda q: ir.predict(np.clip(q, 1e-4, 1 - 1e-4))
    lr = LogisticRegression(C=100.0).fit(np.log(p / (1 - p))[:, None], y)
    return lambda q: lr.predict_proba(np.log(np.clip(q, 1e-4, 1 - 1e-4) / (1 - np.clip(q, 1e-4, 1 - 1e-4)))[:, None])[:, 1]
def logloss(p, y): p = np.clip(p, 1e-3, 1 - 1e-3); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
def stage1(tr, te, style):
    """nested: inner LODO raw OOF per model; calibration cross-fitted across inner DJs; pick (model, cal) by inner log loss.
    returns calibrated p for te, calibrated OOF p for tr (for stage-2 tuning), chosen cfg"""
    djs = sorted({r['dj'] for r in tr}); y = np.array([is_mid(r) for r in tr]); raw = {}
    for kind in models(style):
        o = np.zeros(len(tr))
        for d in djs:
            a = [r for r in tr if r['dj'] != d]; ix = [i for i, r in enumerate(tr) if r['dj'] == d]
            o[ix] = fit_raw(a, style, kind)([tr[i] for i in ix])
        raw[kind] = o
    best = None
    for kind in models(style):
        for cal in (('none',) if kind == 'const' or kind.startswith('beta_') else ('none', 'platt', 'iso')):
            # const is never calibrated: leave-one-DJ-out base rates are anti-correlated with the held-out DJ's rate, and a
            # calibrator fit on them learns a spurious negative slope (seen in the first run: every fold chose const+platt, AUC 0.12)
            oc = np.zeros(len(tr))
            for d in djs:
                ix = np.array([r['dj'] == d for r in tr]); c = calibrator(raw[kind][~ix], y[~ix], cal); oc[ix] = c(raw[kind][ix])
            ll = logloss(oc, y)
            if best is None or ll < best[0]: best = (ll, kind, cal, oc)
    ll, kind, cal, oc = best
    c = calibrator(raw[kind], y, cal); pte = c(fit_raw(tr, style, kind)(te))
    return np.asarray(pte), oc, dict(model=kind, cal=cal, inner_logloss=round(ll, 4), base_logloss=round(logloss(np.full(len(y), y.mean()), y), 4))

# ---- stage 2 ------------------------------------------------------------------------------------------
def types(r):
    na = NA(r['sa']); return np.array([na - c['v'] >= MID for c in r['E']])
def within(r, s):
    """best candidate inside each type by ranker score s (mid, late); None if the type is empty"""
    t = types(r); out = []
    for want in (True, False):
        ix = np.where(t == want)[0]; out.append(int(ix[np.argmax(s[ix])]) if len(ix) else None)
    return out
def eerr(r, j): return abs(r['E'][j]['v'] - r['pro_out'])
def exit_inner(tr, style):
    """picker_1119b's inner selection for the exit ranker (same cfgs/taus), but keeping the OOF scores"""
    djs = sorted({r['dj'] for r in tr}); best = None; SS = {}
    for ci, cfg in enumerate(B.CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]; m = B.fit(a, 'E', style, cfg)
            for r, s in zip(b, B.scores(m, b, 'E', style)): S[r['id']] = s
        SS[ci] = S
        for t in B.TAUS:
            e = np.mean([B.perr(r, 'E', B.gpick(r, 'E', S[r['id']], t)) for r in tr])
            if best is None or e < best[0]: best = (e, ci, t)
    return best, SS[best[1]]
def cost_matrix(tr, S):
    """C[choice][truth], choice/truth in (mid, late): inner-OOF mean exit error of the within-type pick; missing type -> default"""
    C = np.zeros((2, 2)); n = np.zeros((2, 2))
    for r in tr:
        w = within(r, S[r['id']]); tt = 0 if is_mid(r) else 1
        for ch in (0, 1):
            j = w[ch] if w[ch] is not None else r['Edix']; C[ch, tt] += eerr(r, j); n[ch, tt] += 1
    return C / np.maximum(n, 1)
def choose(p, C):
    em = p * C[0, 0] + (1 - p) * C[0, 1]; el = p * C[1, 0] + (1 - p) * C[1, 1]; return 0 if em < el else 1, em, el
def pick_type(r, s, ch):
    w = within(r, s); return w[ch] if w[ch] is not None else r['Edix']
THR = np.round(np.arange(0.2, 0.91, 0.05), 2); BANDS = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3]
def tune(tr, S, poof, C):
    """thr: P(mid) threshold minimising inner-OOF exit error; band: abstain to the default exit when |p - p*| < band (p* = cost break-even)"""
    E = {r['id']: (eerr(r, pick_type(r, S[r['id']], 0)), eerr(r, pick_type(r, S[r['id']], 1)), eerr(r, r['Edix'])) for r in tr}
    bt = min(THR, key=lambda t: (np.mean([E[r['id']][0] if p >= t else E[r['id']][1] for r, p in zip(tr, poof)]), abs(t - 0.5)))
    den = (C[0, 0] - C[0, 1] - C[1, 0] + C[1, 1]); pstar = float((C[1, 1] - C[0, 1]) / den) if abs(den) > 1e-9 else 0.5
    def ab(b): return np.mean([E[r['id']][2] if abs(p - pstar) < b else E[r['id']][choose(p, C)[0]] for r, p in zip(tr, poof)])
    bb = min(BANDS, key=lambda b: (ab(b), b))
    return float(bt), float(bb), pstar

def _fold(args):
    d, dev = args; tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]; res = {}
    for style in (True, False):
        nm = 'style' if style else 'nostyle'
        (e_in, ci, tau), S = exit_inner(tr, style); mE = B.fit(tr, 'E', style, B.CFGS[ci]); Ste = B.scores(mE, te, 'E', style)
        ec, cci, ctau = B.inner(tr, 'C', style); mC = B.fit(tr, 'C', style, B.CFGS[cci]); Ctes = B.scores(mC, te, 'C', style)
        jc = [B.gpick(r, 'C', s, ctau) for r, s in zip(te, Ctes)]; X = B.fitX(tr, style)(te)
        pte, poof, s1 = stage1(tr, te, style); C = cost_matrix(tr, S); bt, bb, pstar = tune(tr, S, poof, C)
        D = collections.defaultdict(list); info = []
        for i, r in enumerate(te):
            s = Ste[i]; p = float(pte[i]); ch, em, el = choose(p, C)
            D[f'b1119_{nm}_gated'].append(B.decide(r, B.gpick(r, 'E', s, tau), jc[i], X[i]))
            D[f'b1119_{nm}_plain'].append(B.decide(r, int(np.argmax(s)), int(np.argmax(B.scores(mC, [r], 'C', style)[0])), X[i]))
            D[f'two_{nm}_cost'].append(B.decide(r, pick_type(r, s, ch), jc[i], X[i]))
            D[f'two_{nm}_thr'].append(B.decide(r, pick_type(r, s, 0 if p >= bt else 1), jc[i], X[i]))
            D[f'two_{nm}_abst'].append(B.decide(r, r['Edix'] if abs(p - pstar) < bb else pick_type(r, s, ch), jc[i], X[i]))
            D[f'knob_{nm}_mid'].append(B.decide(r, pick_type(r, s, 0), jc[i], X[i]))
            D[f'knob_{nm}_late'].append(B.decide(r, pick_type(r, s, 1), jc[i], X[i]))
            D[f'oracle_{nm}'].append(B.decide(r, pick_type(r, s, 0 if is_mid(r) else 1), jc[i], X[i]))
            info.append(dict(id=r['id'], style=style, p_mid=round(p, 3), choice='mid' if ch == 0 else 'late', em=round(em, 1), el=round(el, 1), mid_true=bool(is_mid(r))))
        res[nm] = dict(D=dict(D), info=info, diag=dict(stage1=s1, C=np.round(C, 1).tolist(), thr=bt, band=bb, pstar=round(pstar, 3), exit_cfg=ci, exit_tau=tau, cue_cfg=cci, cue_tau=ctau))
    print('fold', d, {k: v['diag'] for k, v in res.items()}, flush=True)
    return d, [r['id'] for r in te], res

def auc(p, y):
    p, y = np.asarray(p), np.asarray(y); pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg): return None
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))
def ece(p, y, k=5):
    p, y = np.asarray(p), np.asarray(y); bins = np.minimum((p * k).astype(int), k - 1)
    return float(sum(abs(p[bins == b].mean() - y[bins == b].mean()) * (bins == b).mean() for b in range(k) if (bins == b).any()))

def run_cv():
    from concurrent.futures import ProcessPoolExecutor
    rows = B.build(P.rows_all(), P.load_rendered_defaults()); dev = [r for r in rows if r['set'] == 'dev']
    assert all(r['set'] == 'dev' and r['src'] == 'corpus_v2' for r in dev)
    fm = {}
    for l in open(os.path.join(P.W, 'accepted_snapshot.jsonl')):
        a = json.loads(l); f = json.load(open(os.path.join(P0, 'corpus_v2', 'features', a['id'] + '.json'))); fm[a['id']] = (f['track_a']['yt'], f['track_b']['yt'])
    by = collections.defaultdict(list)
    for r in dev: r['ya'], r['yb'] = fm[r['id']]; by[r['mix']].append(r)
    for r in dev: r['mixrows'] = by[r['mix']]
    for r in dev: r['past'] = sorted([q for q in by[r['mix']] if q['idx'] < r['idx']], key=lambda q: q['idx'])  # online: strictly earlier
    for r in dev: FX(r, True); FX(r, False); B.XM([r], 'E', True); B.XM([r], 'E', False); B.XM([r], 'C', True); B.XM([r], 'C', False)
    djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}; order = []; D = collections.defaultdict(list); folds = {}; INFO = []
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 3))) as ex:
        for d, ids, res in ex.map(_fold, [(d, dev) for d in djs]):
            te = [byid[i] for i in ids]; order += te; folds[d] = {k: v['diag'] for k, v in res.items()}
            for nm in res:
                for k, L in res[nm]['D'].items(): D[k] += L
                INFO += res[nm]['info']
            D['default'] += [B.base_decisions(r, 'default') for r in te]
    PS = {x['id']: x for x in INFO if not x['style']}; pst = {d: folds[d]['nostyle']['pstar'] for d in folds}
    mm = collections.defaultdict(list)
    for r in order: mm[r['mix']].append(PS[r['id']]['p_mid'])
    D['commit_nostyle'] = [D['knob_nostyle_' + ('mid' if np.mean(mm[r['mix']]) >= pst[r['dj']] else 'late')][i] for i, r in enumerate(order)]
    for nm in ('style', 'nostyle'):  # fixed-style diagnostic bounds: best fixed style per mix (upper bound of a per-mix setting chosen perfectly)
        em = collections.defaultdict(lambda: [0.0, 0.0])
        for i, r in enumerate(order):
            for j, t in enumerate(('mid', 'late')): em[r['mix']][j] += abs(D[f'knob_{nm}_{t}'][i]['exit'] - r['pro_out'])
        D[f'knob_{nm}_bestpermix'] = [D[f'knob_{nm}_' + ('mid' if em[r['mix']][0] <= em[r['mix']][1] else 'late')][i] for i, r in enumerate(order)]
        D[f'knob_{nm}_worstpermix'] = [D[f'knob_{nm}_' + ('late' if em[r['mix']][0] <= em[r['mix']][1] else 'mid')][i] for i, r in enumerate(order)]
    res = B.summarize(order, dict(D))
    # deltas vs picker_1119b (style_gated and nostyle_plain/gated) as well
    g = [r['mix'] for r in order]
    def ec(L): return [(abs(x['exit'] - r['pro_out']) + abs(x['cue'] - r['pro_in'])) / 2 for x, r in zip(L, order)]
    for ref in ('b1119_style_gated', 'b1119_nostyle_gated', 'b1119_nostyle_plain'):
        for n in D:
            if n.startswith(('two_', 'oracle_', 'knob_', 'commit_')): res[n][f'delta_vs_{ref}'] = P.boot(g, ec(D[ref]), ec(D[n]))
    # stage-1 quality
    s1q = {}
    for style in (True, False):
        I = [x for x in INFO if x['style'] == style]; p = [x['p_mid'] for x in I]; y = [float(x['mid_true']) for x in I]
        s1q['style' if style else 'nostyle'] = dict(n=len(I), base_rate=round(float(np.mean(y)), 3), auc=round(auc(p, y), 3), logloss=round(logloss(np.array(p), np.array(y)), 4),
            logloss_base=round(logloss(np.full(len(y), np.mean(y)), np.array(y)), 4), brier=round(float(np.mean((np.array(p) - np.array(y)) ** 2)), 4), ece5=round(ece(p, y), 3),
            acc_choice=round(float(np.mean([(x['choice'] == 'mid') == x['mid_true'] for x in I])), 3), chose_mid=round(float(np.mean([x['choice'] == 'mid' for x in I])), 3))
    # history-only rule (last transition's mode) as a stage-1 baseline
    hl = [(is_mid(r['past'][-1]) if r['past'] else None, is_mid(r)) for r in order]; hl = [x for x in hl if x[0] is not None]
    s1q['last_mode_rule_acc'] = round(float(np.mean([a == b for a, b in hl])), 3); s1q['last_mode_rule_n'] = len(hl)
    # per-DJ and per-type breakdowns
    arms = list(D)
    def m_(L, ix): return round(float(np.mean([ec(L)[i] for i in ix])), 2) if ix else None
    perdj = {}
    for d in djs:
        ix = [i for i, r in enumerate(order) if r['dj'] == d]; perdj[d] = dict(n=len(ix), mid_rate=round(float(np.mean([is_mid(order[i]) for i in ix])), 2), **{a: m_(D[a], ix) for a in arms})
    bytype = {}
    for t, nm in ((1.0, 'mid'), (0.0, 'late')):
        ix = [i for i, r in enumerate(order) if is_mid(r) == t]; bytype[nm] = dict(n=len(ix), **{a: m_(D[a], ix) for a in arms})
        gg = [g[i] for i in ix]
        for a in ('two_style_cost', 'two_nostyle_cost', 'two_nostyle_thr', 'two_style_thr'):
            bytype[nm][f'{a}_vs_b1119_style_gated'] = P.boot(gg, [ec(D['b1119_style_gated'])[i] for i in ix], [ec(D[a])[i] for i in ix])
            bytype[nm][f'{a}_vs_default'] = P.boot(gg, [ec(D['default'])[i] for i in ix], [ec(D[a])[i] for i in ix])
    # the pairs picker_1119b missed by 32-48 exit bars on late exits
    miss = []
    for i, r in enumerate(order):
        e = abs(D['b1119_style_gated'][i]['exit'] - r['pro_out'])
        if not is_mid(r) and 32 <= e <= 56:
            inf = {x['style']: x for x in INFO if x['id'] == r['id']}
            miss.append(dict(id=r['id'], dj=r['dj'], b1119_exit_err=round(e, 1), **{a + '_exit_err': round(abs(D[a][i]['exit'] - r['pro_out']), 1) for a in ('default', 'two_style_cost', 'two_nostyle_cost', 'two_style_thr', 'two_nostyle_thr')},
                             p_mid_style=inf[True]['p_mid'], p_mid_nostyle=inf[False]['p_mid']))
    pp = [dict(id=r['id'], dj=r['dj'], mix=r['mix'], mid=bool(is_mid(r)), pro_out=r['pro_out'], pro_in=r['pro_in'], **{a: dict(exit=D[a][i]['exit'], cue=D[a][i]['cue'], X=D[a][i]['X'], win=D[a][i].get('win'), is_default=bool(D[a][i].get('is_default'))) for a in arms}) for i, r in enumerate(order)]
    return dict(n=len(order), n_mixes=len(set(g)), n_djs=len(djs), mid_def=f'pro exit >= {MID} bars before music_end', folds=folds, stage1=s1q, results=res, per_dj=perdj, by_type=bytype, late_misses=miss, info=INFO, per_pair=pp)

if __name__ == '__main__':
    out = run_cv(); tag = os.environ.get('TAG', '')
    json.dump(out, open(os.path.join(H, f'exittype_1119_cv{tag}.json'), 'w'), indent=1, default=str)
    print('stage1', json.dumps(out['stage1']))
    for n, s in out['results'].items():
        d = s.get('delta_vs_default', {}).get('exit_cue') or {}; db = s.get('delta_vs_b1119_style_gated') or {}
        print(f"{n:22s} ec {s['exit_cue_mean']} exit {s['exit_mean']} cue {s['cue_mean']} dDef {d.get('delta')} {d.get('ci')} dB1119sg {db.get('delta')} {db.get('ci')} e@16 {s['exit_hit16']} c@16 {s['cue_hit16']} chg {s['changed_vs_default']}")
    print('per_dj', json.dumps(out['per_dj'])); print('by_type', json.dumps({k: {a: v[a] for a in v if not isinstance(v[a], dict)} for k, v in out['by_type'].items()}))
