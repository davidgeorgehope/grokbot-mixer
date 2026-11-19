#!/usr/bin/env python3
"""2026-11-19 day: SAFE placement (flag PLACE=safe, research only; rules.json untouched). Dev only: locked holdout DJs and spent
fresh mixes are never loaded. The planner deliberately chooses swap (mid-track exit) vs ride (late exit) AND the exact window per pair:
  candidates of BOTH types under hard constraints (exit window end on the 16-bar phrase grid, window may not run past the outgoing's
  music end or its last loud bar, cue on the incoming's 16-bar phrase grid relative to its drop 1 or bar 0, legal lengths X in {16,32});
  score = learned hard-fail risk (LightGBM on rendered dev blends, HC_A|HC_B labels) + phrase penalty + LAMBDA*(1 - musical fit),
  musical fit = within-pair percentile of picker_1119b's style-free exit and cue rankers (pro placement as a secondary signal);
  the default window is always a candidate; best score wins (fixed rule, no coin).
  Then render the top 2 non-default picks, keep the first that passes HC_A and HC_B, else the default.
All models are fit leave-one-DJ-out (the test DJ's renders and pairs are excluded). usage:
  safeplace_1119.py risk               grouped-by-mix CV of the risk model
  safeplace_1119.py plan TAG LAMBDA    LODO plan for eval pairs -> safeplace_work/plan_TAG.json + win_TAG_r{1,2}.json
  safeplace_1119.py eval TAG V1 V2     combine renders V1 (rank 1) and V2 (rank 2) -> safeplace_TAG_eval.json"""
import json, os, sys, pickle, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P0), 'src2')
sys.path.insert(0, H); sys.path.insert(0, SRC2)
import picker_1119 as P, picker_1119b as B, final_eval as FE
import lightgbm as lgb
WK = os.path.join(H, 'safeplace_work'); os.makedirs(WK, exist_ok=True)
RV = ['default', 'dropc', 'dropx', 'gated', 'on', 'kush_default', 'kush_dropc', 'kush_dropx', 'kush_gated', 'kush_on', 'ndef1119', 'pick1119', 'et1119c', 'et1119k']
def NA(s): return int(s.get('music_end') or s.get('n_bars'))
_ST = {}
def st(yt):
    if yt not in _ST:
        p = os.path.join(SRC2, 'st', yt + '.json'); _ST[yt] = json.load(open(p))['bar'] if os.path.exists(p) else None
    return _ST[yt]
def seg(v, a, b):
    if v is None: return np.array([])
    return np.asarray(v[max(0, int(a)):max(0, min(len(v), int(b)))], float)
def mean(x): return float(np.mean(x)) if len(x) else np.nan
def tail0(r):
    A = st(r['ya'])
    if not A: return NA(r['sa'])
    al = np.asarray(A['all'], float); body = np.percentile(al, 75); loud = np.where(al > body - 20)[0]
    return int(loud[-1]) + 1 if len(loud) else len(al)
def in_drop(s, k): return any(d[0] <= k < d[1] for d in (s.get('drops') or []))
def wfeat(r, w):
    sa, sb = r['sa'], r['sb']; e, ib, X = int(w[1]), int(w[3]), int(w[4]); s = e - X; na, nb = NA(sa), NA(sb); d1b = int(sb.get('drop1') or 0)
    A, Bc = st(r['ya']), st(r['yb']); dr = sa.get('drops') or []
    ad = np.array([in_drop(sa, k) for k in range(s, e)]); bd = np.array([in_drop(sb, k) for k in range(ib, ib + X)])
    al, bl = seg(A and A['low'], s, e), seg(Bc and Bc['low'], ib, ib + X); aa, ba = seg(A and A['all'], s, e), seg(Bc and Bc['all'], ib, ib + X)
    abody = np.percentile(A['low'], 75) if A else np.nan; bbody = np.percentile(Bc['low'], 75) if Bc else np.nan
    if len(al) == X and len(bl) == X:
        u = (np.arange(X) + 0.5) / X; sl = 10 * np.log10(10 ** (al / 10) * np.cos(u * np.pi / 2) ** 2 + 10 ** (bl / 10) * np.sin(u * np.pi / 2) ** 2)
        hole = float(np.max(np.nanmax([abody, bbody]) - sl)); stack = float(np.mean((al > abody - 6) & (bl > bbody - 6)))
    else: hole = stack = np.nan
    if len(aa) == X and len(ba) == X:
        u = (np.arange(X) + 0.5) / X; la = aa + 20 * np.log10(np.maximum(np.cos(u * np.pi / 2), 1e-3)); lb = ba + 20 * np.log10(np.maximum(np.sin(u * np.pi / 2), 1e-3))
        sm = 10 * np.log10(10 ** (la / 10) + 10 ** (lb / 10)); da, db, ds = np.diff(la), np.diff(lb), np.diff(sm)
        out_rise = float(np.max(np.diff(aa))) if X > 1 else np.nan; wob = int(np.sum(np.abs(ds) >= 2.5)); sd = float(np.std(ds))
        anti = float(np.corrcoef(np.diff(aa), np.diff(ba))[0, 1]) if np.std(np.diff(aa)) > 0 and np.std(np.diff(ba)) > 0 else 0.0
        both_loud = float(np.mean((la > np.percentile(A['all'], 75) - 6) & (lb > np.percentile(Bc['all'], 75) - 6)))
    else: out_rise = wob = sd = anti = both_loud = np.nan
    slope = lambda v: float(np.polyfit(np.arange(len(v)), v, 1)[0]) if len(v) >= 4 else np.nan
    bb = sa.get('bass_by_section') or {}; bbb = sb.get('bass_by_section') or {}
    return [X, e, ib, na - e, e - (sa.get('outro_start') or na), float(e > na), e - tail0(r), float(na - (e - X + 1) >= 32),
            P.sec_at(sa, s), P.sec_at(sa, s + X // 2), P.sec_at(sa, e - 1), P.sec_at(sb, ib), P.sec_at(sb, ib + X // 2), P.sec_at(sb, ib + X - 1),
            float(ad.mean()), float(bd.mean()), float((ad & bd).mean()), e % 16, ib % 16, (ib - d1b) % 16, ib + X - d1b, ib - d1b,
            P.ndist(e, [d[1] for d in dr]), P.ndist(s, [d[0] for d in dr]), P.ndist(e, [sa.get('outro_start')]),
            mean(al) - abody if A else np.nan, mean(bl) - bbody if Bc else np.nan, slope(aa), slope(ba), hole, stack,
            mean(al[-4:]) - abody if len(al) else np.nan, mean(bl[:4]) - bbody if len(bl) else np.nan,
            (bb.get('drop') or {}).get('bass', np.nan), (bbb.get('drop') or {}).get('bass', np.nan), (bb.get('outro') or {}).get('bass', np.nan), (bbb.get('intro') or {}).get('bass', np.nan)] + \
           ([out_rise, wob, sd, anti, both_loud] if os.environ.get('PUMPF', '0') == '1' else [])
FN = ['X', 'e', 'ib', 'left', 'e_minus_outro', 'past_end', 'e_minus_tail0', 'is_mid', 'secA_s', 'secA_m', 'secA_e', 'secB_s', 'secB_m', 'secB_e', 'A_drop_frac', 'B_drop_frac',
      'both_drop_frac', 'e_mod16', 'ib_mod16', 'ibd1_mod16', 'ibX_minus_d1', 'ib_minus_d1', 'd_e_dropend', 'd_s_dropstart', 'd_e_outro', 'A_low_rel', 'B_low_rel', 'A_slope', 'B_slope',
      'sumlow_hole', 'low_stack', 'A_low_end', 'B_low_start', 'A_dropbass', 'B_dropbass', 'A_outrobass', 'B_introbass'] + (['sim_out_rise', 'sim_wobble', 'sim_sum_sd', 'sim_anti_r', 'sim_both_loud'] if os.environ.get('PUMPF', '0') == '1' else [])

def dev_rows():
    rows = [r for r in B.build(P.rows_all(), P.load_rendered_defaults()) if r['set'] == 'dev']
    for r in rows:
        f = json.load(open(os.path.join(P0, 'corpus_v2', 'features', r['id'] + '.json'))); r['ya'], r['yb'] = f['track_a']['yt'], f['track_b']['yt']
    return rows
def load(v):
    p = os.path.join(H, 'hc2_cache', f'arr_{v}.pkl'); return pickle.load(open(p, 'rb')) if os.path.exists(p) else {}
def risk_data(rows, extra=()):
    byid = {r['id']: r for r in rows}; X, y, g, dj, keys = [], [], [], [], []
    for v in list(RV) + list(extra):
        for k, a in load(v).items():
            r = byid.get(k); w = a.get('win')
            if r is None or not w or w[0] != 'n': continue
            f = FE.flags(a); X.append(wfeat(r, w)); y.append(int(f['HC_A'] or f['HC_B'])); g.append(r['mix']); dj.append(r['dj']); keys.append((v, k, tuple(w)))
    return np.array(X, float), np.array(y), np.array(g), np.array(dj), keys
def fit_risk(X, y):
    return lgb.LGBMClassifier(n_estimators=200, num_leaves=7, learning_rate=0.04, min_child_samples=15, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                              reg_lambda=2.0, verbose=-1, n_jobs=2, random_state=20261119).fit(X, y)
def auc(p, y):
    p, y = np.asarray(p), np.asarray(y); pos, neg = p[y == 1], p[y == 0]
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg])) if len(pos) and len(neg) else None

def cands(r):
    sa, sb = r['sa'], r['sb']; na, nb = NA(sa), NA(sb); d1b = int(sb.get('drop1') or 0); t0 = tail0(r); out = {}
    emax = min(na, t0 + 8)
    for X in (16, 32):
        cues = {c for c in range(0, 97, 16)} | {d1b - X + 16 * k for k in range(-2, 2)} | {d1b, d1b - 16}
        cues = {c for c in cues if c >= 0 and c + X <= nb - 16}
        for e in range(16 * (emax // 16), X + 15, -16):
            if e - X < 16: continue
            for ib in cues: out[('n', e, None, ib, X)] = dict(win=['n', e, None, ib, X], phrase_ok=(ib % 16 == 0) or ((ib - d1b) % 16 == 0))
    return list(out.values())
def default_win(r): return ['n', int(round((r['dex'] + r['dX'] - 1) / 8) * 8), None, int(r['dcue'] - 1), int(r['dX'])]

def plan(tag, lam):
    rows = dev_rows(); DEF = {}
    for v in ('default', 'ndef1119'):
        for k, a in load(v).items(): DEF.setdefault(k, a)
    src = lambda y: os.path.exists(os.path.join(P0, 'corpus_v2', 'feat_lib', y + '.m4a')) or os.path.exists(os.path.join(H, 'nightly_1119_work', 'src', y + '.m4a'))
    ev = [r for r in rows if r['id'] in DEF and src(r['ya']) and src(r['yb'])]
    Xr, yr, gr, djr, keys = risk_data(rows, [v for v in os.environ.get('EXTRA_RV', '').split(',') if v]); out = []; W1, W2 = {}, {}
    for d in sorted({r['dj'] for r in ev}):
        tr = [r for r in rows if r['dj'] != d]; m = fit_risk(Xr[djr != d], yr[djr != d])
        mE = B.fit(tr, 'E', False, B.CFGS[0]); mC = B.fit(tr, 'C', False, B.CFGS[0])
        for r in [r for r in ev if r['dj'] == d]:
            C = cands(r); dw = default_win(r); C = [c for c in C if c['win'] != dw] + [dict(win=dw, phrase_ok=True, default=True)]
            F = np.array([wfeat(r, c['win']) for c in C], float); pr = m.predict_proba(F)[:, 1]
            se = mE.predict(np.array([B.fe_exit(r, dict(v=c['win'][1] - c['win'][4] + 1, tags={'grid'} if not c.get('default') else {'default'}), False) for c in C], float))
            sc = mC.predict(np.array([B.fe_cue(r, dict(v=c['win'][3] + 1, tags={'grid'} if not c.get('default') else {'default'}), False) for c in C], float))
            pct = lambda s: (np.argsort(np.argsort(s)) + 0.5) / len(s); fit = (pct(se) + pct(sc)) / 2
            secpen = float(os.environ.get('SECPEN', 0)); bnd = P.bnd_a(r['sa'])
            offsec = np.array([min((abs((c['win'][1] - c['win'][4] + 1) - v) for v in bnd), default=99) > 4 for c in C]) if secpen else np.zeros(len(C))
            score = pr + 0.15 * np.array([not c['phrase_ok'] for c in C]) + lam * (1 - fit) + secpen * offsec
            o = np.argsort(score); di = len(C) - 1
            top = [int(j) for j in o if j != di][:2]
            rec = dict(id=r['id'], dj=d, mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], default_win=dw, default_risk=round(float(pr[di]), 3), default_score=round(float(score[di]), 3),
                       default_rank=int(np.where(o == di)[0][0]), n_cands=len(C),
                       top=[dict(win=C[j]['win'], risk=round(float(pr[j]), 3), fit=round(float(fit[j]), 3), score=round(float(score[j]), 3), is_mid=bool(NA(r['sa']) - (C[j]['win'][1] - C[j]['win'][4] + 1) >= 32)) for j in top])
            rec['keep_default'] = bool(score[di] <= min(score[j] for j in top))
            if not rec['keep_default']:
                W1[f"{r['ya']}|{r['yb']}"] = rec['top'][0]['win']
                if len(rec['top']) > 1: W2[f"{r['ya']}|{r['yb']}"] = rec['top'][1]['win']
            out.append(rec)
        print('dj', d, 'pairs', sum(1 for x in out if x['dj'] == d), flush=True)
    json.dump(out, open(os.path.join(WK, f'plan_{tag}.json'), 'w'), indent=1, default=str)
    json.dump(W1, open(os.path.join(WK, f'win_{tag}_r1.json'), 'w')); json.dump(W2, open(os.path.join(WK, f'win_{tag}_r2.json'), 'w'))
    json.dump([x['id'] for x in out if not x['keep_default']], open(os.path.join(WK, f'ids_{tag}.json'), 'w'))
    print('eval pairs', len(out), 'keep default', sum(x['keep_default'] for x in out), 'mid picks', sum((not x['keep_default']) and x['top'][0]['is_mid'] for x in out))

def risk_cv():
    rows = dev_rows(); X, y, g, dj, keys = risk_data(rows, [v for v in os.environ.get('EXTRA_RV', '').split(',') if v]); from sklearn.model_selection import GroupKFold
    res = dict(n=len(y), pos_rate=round(float(y.mean()), 3), n_mixes=len(set(g)))
    for name, grp in (('by_mix', g), ('by_dj', dj)):
        p = np.zeros(len(y))
        for a, b in GroupKFold(n_splits=min(5, len(set(grp)))).split(X, y, grp): p[b] = fit_risk(X[a], y[a]).predict_proba(X[b])[:, 1]
        res[name] = dict(auc=round(auc(p, y), 3), top_quintile_fail=round(float(y[p >= np.percentile(p, 80)].mean()), 3), bottom_quintile_fail=round(float(y[p <= np.percentile(p, 20)].mean()), 3))
    m = fit_risk(X, y); imp = sorted(zip(FN, m.booster_.feature_importance('gain')), key=lambda t: -t[1])[:12]; res['top_features'] = [(a, round(float(b), 1)) for a, b in imp]
    json.dump(res, open(os.path.join(H, f"safeplace_risk_cv{os.environ.get('TAG', '')}.json"), 'w'), indent=1); print(json.dumps(res))

if __name__ == '__main__':
    if sys.argv[1] == 'risk': risk_cv()
    elif sys.argv[1] == 'plan': plan(sys.argv[2], float(sys.argv[3]))
