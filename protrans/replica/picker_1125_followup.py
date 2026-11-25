#!/usr/bin/env python3
"""Follow-up on picker-cv-1125 (n=843 dev pairs, 25 leave-one-DJ-out folds):
  1) diagnose: recover full picker-cv-1125 results, bucket exit misses (default + learned) with counts & track context.
  2) cv: cross-validate section-aware hybrid pickers on the exact same 25 folds:
     - cueonly_gated (picker_1125 baseline hybrid: old cue ranker + default exit)
     - hybrid_sec_cue (section-aware cue ranker + exit-coupled alignment features + default exit + default X)
     - hybrid_sec_mix (hybrid_sec_cue + section-aware Bayes-mixture Expected-MAE exit gate + default X)
     - hybrid_sec_mix_X (same + learned X)
     Reports exit/cue mean, median, hit@8, hit@16 with mix-clustered AND pair-clustered bootstrap 95% CIs vs default & majority.
  3) protrans_maps: train on all 843 dev pairs and emit window maps for the 33 protrans pairs (never trained on).
  4) eval_pinned: verify v1 baseline (32.40/34.07) and score hybrid_sec_cue & hybrid_sec_mix with v1 + official_v2-place8c
     on the 33 pinned pairs (PROTRANS_SRC2 = src2_pin_n1121, HARD_FALLBACK=0). Does NOT write rules.json.
"""
from __future__ import annotations
import collections, json, os, shutil, sys, traceback
import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
P0 = os.path.dirname(H)
sys.path.insert(0, H)
sys.path.insert(0, P0)

import picker_1119 as P
import picker_1119b as B
import lightgbm as lgb

W = os.path.join(H, 'nightly_1125_work')
os.makedirs(W, exist_ok=True)
FRESH_ALL = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes']}
P.W = W
P.SPENT_FRESH = FRESH_ALL
B.W = W

SEED = 20261125
MARGINS = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 1e9]
NB = 4000


def na_(r):
    return float(r['sa'].get('music_end') or r['sa'].get('n_bars'))


def real_drops(sec):
    da = [list(map(int, d)) for d in (sec.get('drops') or [])]
    real = [d for d in da if not (d[0] < 8 and (d[1] - d[0]) <= 24)]
    return real if real else da


def sec_label_rich(s, bar):
    if bar is None:
        return 'none'
    dr = s.get('drops') or []
    for p in (s.get('phases') or []):
        if p['start'] <= bar < p['end']:
            if p['name'] == 'drop':
                for i, (a, b) in enumerate(dr):
                    if a <= bar < b:
                        return f'drop{i + 1}'
            return p['name']
    if not dr:
        return 'outro' if bar >= (s.get('outro_start') or s.get('music_end') or 999) else 'intro'
    if bar < dr[0][0]:
        return 'intro'
    for i, (a, b) in enumerate(dr):
        if a <= bar < b:
            return f'drop{i + 1}'
    if bar >= (s.get('outro_start') or dr[-1][1]):
        return 'outro'
    return 'breakdown'


def sec_pair_feats(r):
    """Style-free, section-aware track A + track B + default-exit context features."""
    sa, sb = r['sa'], r['sb']
    na = na_(r)
    da = real_drops(sa)
    db = real_drops(sb)
    d1s, d1e = (da[0][0], da[0][1]) if da else (np.nan, np.nan)
    d1_len = (d1e - d1s) if da else 0.0
    d2s, d2e = (da[1][0], da[1][1]) if len(da) > 1 else (np.nan, np.nan)
    d2_len = (d2e - d2s) if len(da) > 1 else 0.0
    brk_len = (d2s - d1e) if len(da) > 1 else 0.0
    outro_s = sa.get('outro_start')
    outro_len = na - outro_s if outro_s is not None else 0.0
    bba = sa.get('bass_by_section') or {}
    bbb = sb.get('bass_by_section') or {}
    g = lambda d, k, m: (d.get(k) or {}).get(m, np.nan)
    a_db, a_dd = g(bba, 'drop', 'bass'), g(bba, 'drop', 'drums')
    a_bb, a_bd = g(bba, 'breakdown', 'bass'), g(bba, 'breakdown', 'drums')
    a_ob, a_od = g(bba, 'outro', 'bass'), g(bba, 'outro', 'drums')
    b_ib, b_id = g(bbb, 'intro', 'bass'), g(bbb, 'intro', 'drums')
    b_db, b_dd = g(bbb, 'drop', 'bass'), g(bbb, 'drop', 'drums')
    d1b = float(sb.get('drop1') or 0)
    return B.base_feats(r) + [
        len(da), d1s, d1e, d1_len, d2s, d2e, d2_len, brk_len, outro_len,
        na - d1e if np.isfinite(d1e) else np.nan,
        d1e / na if np.isfinite(d1e) else np.nan,
        na - r['dex'], P.sec_at(sa, r['dex']),
        a_db, a_dd, a_dd - a_bd, a_db - a_bb, a_dd - a_od, a_db - a_ob,
        b_db - b_ib, b_dd - b_id, float(db[0][1] - db[0][0]) if db else 0.0,
        (na - r['dex']) - d1b, (r['dex'] - d1e) if np.isfinite(d1e) else np.nan,
        r['bpm'][0] or np.nan, r['bpm'][1] or np.nan,
    ]


def fe_cue_sec(r, c):
    """Section-aware cue features: Track B thinness/build/drop1 contrast + alignment to Track A default exit."""
    sb, sa = r['sb'], r['sa']
    nb = float(sb.get('music_end') or sb.get('n_bars'))
    na = na_(r)
    d1b = float(sb.get('drop1') or 0)
    x = c['v']
    bbb = sb.get('bass_by_section') or {}
    bba = sa.get('bass_by_section') or {}
    g = lambda d, k, m: (d.get(k) or {}).get(m, np.nan)
    b_ib, b_id = g(bbb, 'intro', 'bass'), g(bbb, 'intro', 'drums')
    b_db, b_dd = g(bbb, 'drop', 'bass'), g(bbb, 'drop', 'drums')
    b_bb, b_bd = g(bbb, 'build', 'bass'), g(bbb, 'build', 'drums')
    db = real_drops(sb)
    b_d1_len = float(db[0][1] - db[0][0]) if db else 0.0
    b_build_len = max(0.0, d1b - float(sb.get('intro_end') or 0))
    sec_x = P.sec_at(sb, x)
    sec_end = P.sec_at(sb, x + r['dX'] - 1)
    bars_to_d1 = d1b - x
    out_left_dex = na - r['dex']
    outro_len_a = na - float(sa.get('outro_start') or na)
    a_dd = g(bba, 'drop', 'drums')
    a_od = g(bba, 'outro', 'drums')
    return B.fe_cue(r, c, False) + [
        b_db, b_dd, b_id, b_db - b_ib, b_dd - b_id, b_bb, b_bd, b_db - b_bb,
        b_d1_len, b_build_len, sec_end, int(sec_x != sec_end),
        bars_to_d1, bars_to_d1 - r['dX'], abs(bars_to_d1 - r['dX']),
        bars_to_d1 - out_left_dex, abs(bars_to_d1 - out_left_dex),
        out_left_dex, outro_len_a, P.sec_at(sa, r['dex']),
        float(sb.get('outro_start') or nb) - x,
        a_dd - a_od,
    ]


def ensure_sec_cue_cache(rows):
    for r in rows:
        if 'XC_sec' not in r:
            r['XC_sec'] = np.array([fe_cue_sec(r, c) for c in r['C']], float)
        if 'Xpair_sec' not in r:
            r['Xpair_sec'] = np.array(sec_pair_feats(r), float)


def fit_cue_sec(rs, cfg):
    ensure_sec_cue_cache(rs)
    X = np.vstack([r['XC_sec'] for r in rs])
    y = np.concatenate([r['Crel'] for r in rs])
    grp = [len(r['C']) for r in rs]
    m = lgb.LGBMRanker(
        objective='lambdarank', n_estimators=cfg['n'], num_leaves=cfg['leaves'],
        learning_rate=0.05, min_child_samples=cfg['mcs'], subsample=0.8,
        subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1, n_jobs=1,
    )
    m.fit(X, y, group=grp)
    return m


def scores_cue_sec(m, rs):
    ensure_sec_cue_cache(rs)
    return [m.predict(r['XC_sec']) for r in rs]


def inner_cue_sec(tr):
    djs = sorted({r['dj'] for r in tr})
    best = None
    for ci, cfg in enumerate(B.CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]
            b = [r for r in tr if r['dj'] == d]
            m = fit_cue_sec(a, cfg)
            for r, s in zip(b, scores_cue_sec(m, b)):
                S[r['id']] = s
        for t in B.TAUS:
            e = np.mean([B.perr(r, 'C', B.gpick(r, 'C', S[r['id']], t)) for r in tr])
            if best is None or e < best[0]:
                best = (e, ci, t)
    return best


TAUS_POS = [0.15, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 1e9]


def dj_pair_weights(rs, cap=20.0):
    cnt = collections.Counter(r['dj'] for r in rs)
    return [min(1.0, float(cap) / max(1, cnt[r['dj']])) for r in rs]


def fit_cue_djbal(rs, cfg, cap=20.0):
    ensure_sec_cue_cache(rs)
    X = np.vstack([r['XC_sec'] for r in rs])
    y = np.concatenate([r['Crel'] for r in rs])
    grp = [len(r['C']) for r in rs]
    w_pair = dj_pair_weights(rs, cap=cap)
    sw = np.repeat(w_pair, grp)
    m = lgb.LGBMRanker(
        objective='lambdarank', n_estimators=cfg['n'], num_leaves=cfg['leaves'],
        learning_rate=0.05, min_child_samples=cfg['mcs'], subsample=0.8,
        subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1, n_jobs=1,
    )
    m.fit(X, y, group=grp, sample_weight=sw)
    return m


def inner_cue_djbal(tr, cap=20.0):
    djs = sorted({r['dj'] for r in tr})
    w_tr = dj_pair_weights(tr, cap=cap)
    w_sum = sum(w_tr)
    best = None
    for ci, cfg in enumerate(B.CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]
            b = [r for r in tr if r['dj'] == d]
            m = fit_cue_djbal(a, cfg, cap=cap)
            for r, s in zip(b, scores_cue_sec(m, b)):
                S[r['id']] = s
        for t in TAUS_POS:
            e = sum(w * B.perr(r, 'C', B.gpick(r, 'C', S[r['id']], t)) for r, w in zip(tr, w_tr)) / w_sum
            if best is None or e < best[0]:
                best = (e, ci, t)
    return best


def fit_mix_exit_models(tr):
    """Fit bimodal Bayes-risk exit models on training pairs:
    p_early = P(pro_out < na - 40), mu_early = E[pro_out|early], mu_late = E[pro_out|late]."""
    ensure_sec_cue_cache(tr)
    X = np.array([r['Xpair_sec'] for r in tr], float)
    na = np.array([na_(r) for r in tr])
    y = np.array([r['pro_out'] for r in tr])
    mid = (na - y) > 40.0
    m_p = lgb.LGBMClassifier(
        n_estimators=100, num_leaves=5, learning_rate=0.05, min_child_samples=25,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X, mid.astype(float))
    m_e = lgb.LGBMRegressor(
        objective='regression_l1', n_estimators=100, num_leaves=5, learning_rate=0.05,
        min_child_samples=20, subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X[mid], y[mid])
    m_l = lgb.LGBMRegressor(
        objective='regression_l1', n_estimators=100, num_leaves=5, learning_rate=0.05,
        min_child_samples=20, subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X[~mid], y[~mid])
    return m_p, m_e, m_l


def predict_mix_exit(models, rs):
    ensure_sec_cue_cache(rs)
    m_p, m_e, m_l = models
    X = np.array([r['Xpair_sec'] for r in rs], float)
    pe = m_p.predict_proba(X)[:, 1]
    me = m_e.predict(X)
    ml = m_l.predict(X)
    out = []
    for i, r in enumerate(rs):
        p, a, b = float(pe[i]), float(me[i]), float(ml[i])
        risks = [p * abs(c['v'] - a) + (1.0 - p) * abs(c['v'] - b) for c in r['E']]
        j_best = int(np.argmin(risks))
        gain = float(risks[r['Edix']] - risks[j_best])
        out.append((j_best, gain, p, a, b))
    return out


def inner_mix_margin(tr):
    """Select Bayes-risk gate margin via inner leave-one-DJ-out CV."""
    djs = sorted({r['dj'] for r in tr})
    oof = {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]
        b = [r for r in tr if r['dj'] == d]
        mods = fit_mix_exit_models(a)
        for r, pred in zip(b, predict_mix_exit(mods, b)):
            oof[r['id']] = pred
    best = None
    for mg in MARGINS:
        errs = []
        for r in tr:
            jb, gain, _, _, _ = oof[r['id']]
            j = jb if gain >= mg else r['Edix']
            errs.append(B.perr(r, 'E', j))
        me = float(np.mean(errs))
        if best is None or me < best[0]:
            best = (me, mg)
    return best


def train_predict_followup(tr, te):
    ensure_sec_cue_cache(tr)
    ensure_sec_cue_cache(te)
    # 1) Old cueonly_gated (picker_1125 baseline)
    _, ciC_old, tauC_old = B.inner(tr, 'C', False)
    mC_old = B.fit(tr, 'C', False, B.CFGS[ciC_old])
    SC_old = B.scores(mC_old, te, 'C', False)
    jc_old = [B.gpick(r, 'C', s, tauC_old) for r, s in zip(te, SC_old)]

    # 2) Section-aware cue
    eC_sec, ciC_sec, tauC_sec = inner_cue_sec(tr)
    mC_sec = fit_cue_sec(tr, B.CFGS[ciC_sec])
    SC_sec = scores_cue_sec(mC_sec, te)
    jc_sec = [B.gpick(r, 'C', s, tauC_sec) for r, s in zip(te, SC_sec)]

    # 3) Section-aware Bayes-mixture Expected-MAE exit gate
    eE_mix, mg_best = inner_mix_margin(tr)
    mods_mix = fit_mix_exit_models(tr)
    mix_preds = predict_mix_exit(mods_mix, te)
    je_mix = [jb if gain >= mg_best else r['Edix'] for r, (jb, gain, _, _, _) in zip(te, mix_preds)]

    # 4) Learned X (from picker_1119b)
    Xm = B.fitX(tr, False)(te)

    D = {}
    D['default'] = [B.base_decisions(r, 'default') for r in te]
    D['cueonly_gated'] = [B.decide(r, r['Edix'], c, r['dX']) for r, c in zip(te, jc_old)]
    D['hybrid_sec_cue'] = [B.decide(r, r['Edix'], c, r['dX']) for r, c in zip(te, jc_sec)]
    D['hybrid_sec_mix'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, je_mix, jc_sec)]
    D['hybrid_sec_mix_X'] = [B.decide(r, j, c, X) for r, j, c, X in zip(te, je_mix, jc_sec, Xm)]
    for x, (_, gain, p, a, b) in zip(D['hybrid_sec_mix'], mix_preds):
        x['p_early'] = round(p, 3)
        x['mu_early'] = round(a, 1)
        x['mu_late'] = round(b, 1)
        x['risk_gain'] = round(gain, 2)
    diag = dict(
        cue_old=dict(cfg=ciC_old, tau=tauC_old),
        cue_sec=dict(cfg=ciC_sec, tau=tauC_sec, inner=round(float(eC_sec), 2)),
        mix_exit=dict(margin=mg_best, inner=round(float(eE_mix), 2)),
    )
    return D, diag


def _fold(args):
    d, dev = args
    tr = [r for r in dev if r['dj'] != d]
    te = [r for r in dev if r['dj'] == d]
    D, diag = train_predict_followup(tr, te)
    print('fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag


def clustered_boots(pp, arms, refs=('default', 'majority')):
    """Compute both mix-clustered AND pair-clustered bootstrap 95% CIs (4000 draws, seed 20261125)."""
    ex = lambda r, a: abs(r[a]['exit'] - r['pro_out'])
    cu = lambda r, a: abs(r[a]['cue'] - r['pro_in'])
    ec = lambda r, a: (ex(r, a) + cu(r, a)) / 2.0
    ov = {16: 10.0, 32: 18.0}
    bl = lambda r, a: abs(ov.get(r[a]['X'], 10.0) - (r['pro_ov'] if r['pro_ov'] is not None else 10.0))

    mixes = sorted({r['mix'] for r in pp})
    idx_m = collections.defaultdict(list)
    for i, r in enumerate(pp):
        idx_m[r['mix']].append(i)
    rng = np.random.default_rng(SEED)
    BS_mix = [np.concatenate([idx_m[mixes[m]] for m in rng.choice(len(mixes), len(mixes))]) for _ in range(NB)]
    BS_pair = rng.integers(0, len(pp), (NB, len(pp)))

    def boot(BS, f, a, b, sign=1.0):
        A = np.array([sign * (f(r, a) - f(r, b)) for r in pp])
        s = [A[ii].mean() for ii in BS]
        return [round(float(A.mean()), 3), round(float(np.percentile(s, 2.5)), 3), round(float(np.percentile(s, 97.5)), 3)]

    out = dict(mix_clustered={}, pair_clustered={})
    for bname, BS in (('mix_clustered', BS_mix), ('pair_clustered', BS_pair)):
        for a in arms:
            for ref in refs:
                if a == ref:
                    continue
                D = {m: boot(BS, f, a, ref) for m, f in (('exit_cue', ec), ('exit', ex), ('cue', cu), ('blendlen', bl))}
                for t in (4, 8, 16):
                    for nm, f in (('exit', ex), ('cue', cu)):
                        D[f'{nm}_hit{t}_gain'] = boot(BS, lambda r, x, f=f, t=t: float(f(r, x) <= t), a, ref)
                out[bname][f'{a}_vs_{ref}'] = D
    return out


def run_diagnose():
    cv = json.load(open(os.path.join(H, 'picker_1125_cv.json')))
    pp = cv['per_pair']
    recovered_results = {
        k: {kk: vv for kk, vv in v.items() if not isinstance(vv, dict)}
        for k, v in cv['results'].items()
    }

    def_buckets = collections.Counter()
    ref_buckets = collections.Counter()
    rg_buckets = collections.Counter()
    detailed = []
    for r in pp:
        f = json.load(open(os.path.join(P0, 'corpus_v2', 'features', r['id'] + '.json')))
        sa, sb = f['track_a']['sections'], f['track_b']['sections']
        na = float(sa.get('music_end') or sa.get('n_bars'))
        nb = float(sb.get('music_end') or sb.get('n_bars'))
        pout, pin = r['pro_out'], r['pro_in']
        psec = sec_label_rich(sa, pout)
        pin_sec = sec_label_rich(sb, pin)
        da = sa.get('drops') or []
        d1_end = da[0][1] if da else None
        bba = sa.get('bass_by_section') or {}
        bbb = sb.get('bass_by_section') or {}
        b_thin_b = ((bbb.get('drop') or {}).get('bass') - (bbb.get('intro') or {}).get('bass')) if ((bbb.get('drop') or {}).get('bass') is not None and (bbb.get('intro') or {}).get('bass') is not None) else None
        a_qbrk_d = ((bba.get('drop') or {}).get('drums') - (bba.get('breakdown') or {}).get('drums')) if ((bba.get('drop') or {}).get('drums') is not None and (bba.get('breakdown') or {}).get('drums') is not None) else None
        outro_len = na - (sa.get('outro_start') or na)

        dex = r['default']['exit']
        rex = r['ref_full_gated']['exit']
        gex = r['ridegate']['exit']
        ed, er, eg = abs(dex - pout), abs(rex - pout), abs(gex - pout)

        if ed <= 16:
            def_b = 'hit_within_16'
        elif pout < 16:
            def_b = 'pro_ultra_early_intro (<16 bars)'
        elif psec in ('drop1', 'build') or (d1_end and pout <= d1_end - 8):
            def_b = 'pro_exited_during_drop1_or_build'
        elif psec == 'breakdown' or (d1_end and d1_end - 8 < pout < (da[1][0] if len(da) > 1 else na) + 8):
            def_b = 'pro_exited_drop1_end_or_breakdown'
        elif psec in ('drop2', 'drop3', 'drop4', 'drop5') and pout < na - 40:
            def_b = 'pro_exited_later_drop_midtrack (>40 bars left)'
        elif na - pout <= 12 and dex < pout - 16:
            def_b = 'pro_very_late_tail_exit (<=12 bars left)'
        else:
            def_b = 'pro_late_outro_or_drop_end_offset'
        def_buckets[def_b] += 1

        for bk, ex_v in ((ref_buckets, rex), (rg_buckets, gex)):
            if abs(ex_v - pout) <= 16:
                bk['hit_within_16'] += 1
            elif pout >= na - 40 and ex_v < na - 40:
                bk['false_early_jump (pro late >=na-40, model mid-track)'] += 1
            elif pout < na - 40 and ex_v >= na - 40:
                bk['false_late_hold (pro mid-track, model stayed late/default)'] += 1
            elif pout < na - 40 and ex_v < na - 40:
                bk['wrong_midtrack_section (both mid-track, >16 bars apart)'] += 1
            else:
                bk['late_tail_or_outro_offset (both >=na-40, >16 bars apart)'] += 1

        detailed.append(dict(
            id=r['id'], dj=r['dj'], mix=r['mix'], pair=f.get('pair', ''),
            na=na, nb=nb, pro_out=pout, pro_in=pin, pro_ov=r['pro_ov'],
            pro_sec=psec, pro_in_sec=pin_sec,
            def_exit=dex, def_cue=r['default']['cue'], def_sec=sec_label_rich(sa, dex),
            ref_exit=rex, ref_sec=sec_label_rich(sa, rex),
            rg_exit=gex, rg_sec=sec_label_rich(sa, gex),
            err_def=round(ed, 1), err_ref=round(er, 1), err_rg=round(eg, 1),
            def_bucket=def_b, drops_a=da, bd_a=sa.get('breakdown'), outro_a=sa.get('outro_start'),
            outro_len=outro_len, d1b=sb.get('drop1'), b_thin_bass_db=b_thin_b, a_brk_drum_drop_db=a_qbrk_d,
        ))

    diag = dict(
        n=len(pp),
        recovered_picker_1125_results=recovered_results,
        default_exit_buckets=dict(def_buckets),
        ref_full_gated_exit_buckets=dict(ref_buckets),
        ridegate_exit_buckets=dict(rg_buckets),
        worst_default_misses=sorted(detailed, key=lambda x: -x['err_def'])[:20],
        worst_false_early_jumps_rg=sorted(
            [x for x in detailed if x['pro_out'] >= x['na'] - 40 and x['rg_exit'] < x['na'] - 40],
            key=lambda x: -(x['err_rg'] - x['err_def']),
        )[:15],
        worst_false_late_holds_rg=sorted(
            [x for x in detailed if x['pro_out'] < x['na'] - 40 and x['rg_exit'] >= x['na'] - 40],
            key=lambda x: -x['err_rg'],
        )[:15],
    )
    outp = os.path.join(H, 'picker_1125_diagnosis.json')
    json.dump(diag, open(outp, 'w'), indent=1, default=str)
    print('Saved diagnosis to', outp, flush=True)
    print('DEFAULT BUCKETS:', dict(def_buckets), flush=True)
    print('REF_FULL_GATED BUCKETS:', dict(ref_buckets), flush=True)
    print('RIDEGATE BUCKETS:', dict(rg_buckets), flush=True)


def run_cv():
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    B.XM(dev, 'E', False)
    B.XM(dev, 'C', False)
    ensure_sec_cue_cache(dev)

    # Also pull majority + ridegate from picker_1125_cv.json so all arms align on the exact same 843 ids
    cv1125 = json.load(open(os.path.join(H, 'picker_1125_cv.json')))
    byid1125 = {r['id']: r for r in cv1125['per_pair']}

    from concurrent.futures import ProcessPoolExecutor
    djs = sorted({r['dj'] for r in dev})
    byid = {r['id']: r for r in dev}
    order = []
    D = collections.defaultdict(list)
    folds = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 2))) as ex:
        for d, ids, Dd, diag in ex.map(_fold, [(d, dev) for d in djs]):
            te = [byid[i] for i in ids]
            order += te
            folds[d] = diag
            for k, v in Dd.items():
                D[k] += v
            for r in te:
                p1125 = byid1125[r['id']]
                for ref_arm in ('ridegate', 'majority', 'rule_drop_exit'):
                    D[ref_arm].append(p1125[ref_arm])

    res = B.summarize(order, dict(D))
    # Compute full per-pair table + mix/pair clustered bootstrap CIs + strata
    pp = []
    for i, r in enumerate(order):
        row = dict(id=r['id'], dj=r['dj'], mix=r['mix'], pro_out=r['pro_out'], pro_in=r['pro_in'], pro_ov=r['pro_ov'],
                   dex=r['dex'], dcue=r['dcue'], dX=r['dX'], na=na_(r))
        for k, L in D.items():
            row[k] = dict(exit=L[i]['exit'], cue=L[i]['cue'], X=L[i]['X'], is_default=bool(L[i].get('is_default')),
                          win=L[i].get('win'), p_early=L[i].get('p_early'), mu_early=L[i].get('mu_early'),
                          mu_late=L[i].get('mu_late'), risk_gain=L[i].get('risk_gain'))
        pp.append(row)

    arms = ['cueonly_gated', 'hybrid_sec_cue', 'hybrid_sec_mix', 'hybrid_sec_mix_X', 'ridegate', 'majority', 'rule_drop_exit']
    boots = clustered_boots(pp, arms)
    # Detailed metrics table (mean, median, hit@8, hit@16, strata)
    metrics = {}
    late = [r for r in pp if r['pro_out'] >= r['na'] - 40]
    mid = [r for r in pp if r['pro_out'] < r['na'] - 40]
    for a in ['default'] + arms:
        ee = [abs(r[a]['exit'] - r['pro_out']) for r in pp]
        ce = [abs(r[a]['cue'] - r['pro_in']) for r in pp]
        ec = [(x + y) / 2.0 for x, y in zip(ee, ce)]
        metrics[a] = dict(
            exit_mean=round(float(np.mean(ee)), 2),
            exit_median=round(float(np.median(ee)), 1),
            exit_hit8=round(float(np.mean([x <= 8 for x in ee])), 3),
            exit_hit16=round(float(np.mean([x <= 16 for x in ee])), 3),
            cue_mean=round(float(np.mean(ce)), 2),
            cue_median=round(float(np.median(ce)), 1),
            cue_hit8=round(float(np.mean([x <= 8 for x in ce])), 3),
            cue_hit16=round(float(np.mean([x <= 16 for x in ce])), 3),
            exit_cue_mean=round(float(np.mean(ec)), 2),
            exit_moved=round(float(np.mean([r[a]['exit'] != r['default']['exit'] for r in pp])), 3),
            cue_moved=round(float(np.mean([r[a]['cue'] != r['default']['cue'] for r in pp])), 3),
            pro_mid_exit_mean=round(float(np.mean([abs(r[a]['exit'] - r['pro_out']) for r in mid])), 2),
            pro_late_exit_mean=round(float(np.mean([abs(r[a]['exit'] - r['pro_out']) for r in late])), 2),
        )

    out = dict(
        n=len(order), n_mixes=len({r['mix'] for r in order}), n_djs=len(djs),
        folds=folds, metrics=metrics, results=res, bootstraps=boots, per_pair=pp,
    )
    outp = os.path.join(H, 'picker_1125_followup_cv.json')
    json.dump(out, open(outp, 'w'), indent=1, default=str)
    print('Saved CV to', outp, flush=True)
    for a, m in metrics.items():
        print(f"METRIC {a:18s} ec={m['exit_cue_mean']} exit={m['exit_mean']}(med {m['exit_median']}, @8 {m['exit_hit8']}, @16 {m['exit_hit16']}) "
              f"cue={m['cue_mean']}(med {m['cue_median']}, @8 {m['cue_hit8']}, @16 {m['cue_hit16']}) mid={m['pro_mid_exit_mean']} late={m['pro_late_exit_mean']}", flush=True)
    for btype in ('mix_clustered', 'pair_clustered'):
        for a in ('cueonly_gated', 'hybrid_sec_cue', 'hybrid_sec_mix', 'ridegate'):
            for ref in ('default', 'majority'):
                d = boots[btype][f'{a}_vs_{ref}']
                print(f"CI[{btype}] {a}_vs_{ref}: ec={d['exit_cue']} exit={d['exit']} cue={d['cue']} e@8={d['exit_hit8_gain']} e@16={d['exit_hit16_gain']} c@8={d['cue_hit8_gain']} c@16={d['cue_hit16_gain']}", flush=True)


def run_protrans_maps():
    import run_admitted_tune as T
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    te = [r for r in rows if r['set'] == 'protrans']
    D, diag = train_predict_followup(dev, te)
    recs = {r['id']: r for r in T.load_recs()}
    out = dict(n=len(te), diag=diag, maps={})
    for arm in ('hybrid_sec_cue', 'hybrid_sec_mix'):
        by_yt, by_id = {}, {}
        for r, x in zip(te, D[arm]):
            rec = recs.get(r['id'])
            key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
            by_id[r['id']] = dict(win=x.get('win'), exit=x['exit'], cue=x['cue'], X=x['X'],
                                  abstain=bool(x.get('is_default')), yt_key=key)
            if key and x.get('win') and not x.get('is_default'):
                by_yt[key] = x['win']
        mp = dict(
            written='2026-11-25 followup',
            model=f'picker_1125_followup {arm} (style-free), trained on {len(dev)} dev, applied to 33 protrans pairs',
            by_yt=by_yt, by_id=by_id,
            do_not='write rules.json or treat this map as a promotion',
        )
        dest = os.path.join(W, f'map_{arm}.json')
        json.dump(mp, open(dest, 'w'), indent=1, default=str)
        out['maps'][arm] = dict(path=dest, n_windows=len(by_yt), n_total=len(by_id))
    json.dump(out, open(os.path.join(H, 'picker_1125_followup_protrans_maps.json'), 'w'), indent=1, default=str)
    print('Wrote protrans maps:', out['maps'], 'diag:', diag, flush=True)


def _pinned_worker(payload):
    arm, map_path, i, rec = payload
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    os.environ.setdefault('PROTRANS_SRC2', '/workspace/mixes/src2_pin_n1121')
    if map_path:
        os.environ['PICKER_STYLE_GATED'] = '1'
        os.environ['PICKER_STYLE_GATED_MAP'] = map_path
    else:
        os.environ.pop('PICKER_STYLE_GATED', None)
        os.environ.pop('PICKER_STYLE_GATED_MAP', None)
    if arm.startswith('djbal_'):
        os.environ['PICKER_INJECT_CS'] = '1'
    else:
        os.environ.pop('PICKER_INJECT_CS', None)
    import paths, recreate, score, score_v2 as S2
    rules = json.load(open(paths.RULES))
    if map_path:
        rules['PICKER_STYLE_GATED'] = 1
    if arm.startswith('djbal_'):
        rules['PICKER_INJECT_CS'] = 1
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    try:
        info = recreate.recreate(
            rec['a']['yt'], rec['b']['yt'], sa, sb,
            hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
            rules=rules, tag=f'pf{arm[:4]}{i}',
        )
        dst = os.path.join(W, 'pinned_renders', arm, rec['id'] + '.mp3')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(info['ours'], dst)
        v1 = score.score(rec['pro_clip'], dst, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
        r2 = S2.score_v2(rec['pro_clip'], dst, sa, sb, v1=v1)
        pinfo = info.get('picker') or {}
        return dict(
            id=rec['id'], split=rec['split'], dj=rec['dj'], arm=arm,
            fam=info['fam'], win=info['win'], injected_cs=bool(pinfo.get('injected_cs')),
            v1=v1['score'],
            v1_breakdown={k: v1['breakdown'][k] for k in ('stem_curves', 'deck_curves', 'beat_align', 'bass_swap', 'outgoing_cut', 'blend_length')},
            v2=r2['official_v2'], placement=r2['placement'], ours=dst,
        )
    except Exception:
        return dict(id=rec['id'], split=rec['split'], dj=rec['dj'], arm=arm, error=traceback.format_exc()[-600:])


def run_eval_pinned():
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, run_admitted_tune as T, score_v2 as S2
    recs = T.load_recs()

    for arm in ('hybrid_sec_cue', 'hybrid_sec_mix'):
        if not os.path.exists(os.path.join(W, f'map_{arm}.json')):
            run_protrans_maps()
            break

    # Load verified base cohort (recomputing v2 with current score_v2.py) and cross-check any live pinned_base.jsonl rows
    cohort_base_p = os.path.join(P0, 'research_1124', 'scorev2', 'cohort_base.jsonl')
    base_by_id = {}
    for l in open(cohort_base_p):
        if l.strip():
            row = json.loads(l)
            if not row.get('error'):
                pl = S2.placement_score(row['placement']['ours'], row['placement']['pro'])
                row['placement']['parts'] = pl
                row['v2'] = round(S2.combine(row['v1'], row['v1_breakdown'], pl), 2)
                base_by_id[row['id']] = row
    live_base_ck = os.path.join(W, 'pinned_base.jsonl')
    if os.path.exists(live_base_ck):
        for l in open(live_base_ck):
            if l.strip():
                lr = json.loads(l)
                if not lr.get('error') and lr['id'] in base_by_id:
                    b = base_by_id[lr['id']]
                    assert abs(lr['v1'] - b['v1']) < 0.05 and abs(lr['v2'] - b['v2']) < 0.05, f"base mismatch {lr['id']}: {lr['v1']}/{lr['v2']} vs {b['v1']}/{b['v2']}"

    arms = [
        ('hybrid_sec_cue', os.path.join(W, 'map_hybrid_sec_cue.json')),
        ('cueonly_gated', os.path.join(W, 'map_cueonly_gated.json')),
        ('hybrid_sec_mix', os.path.join(W, 'map_hybrid_sec_mix.json')),
    ]
    import multiprocessing as mp

    def _summarize(arm_name, rows_ok):
        tr = [x for x in rows_ok if x['split'] == 'train']
        te = [x for x in rows_ok if x['split'] == 'test']
        fams = collections.Counter(x['fam'] for x in rows_ok)
        d_v1 = [x['v1'] - base_by_id[x['id']]['v1'] for x in rows_ok]
        d_v2 = [x['v2'] - base_by_id[x['id']]['v2'] for x in rows_ok]
        rng = np.random.default_rng(SEED)
        bs = rng.integers(0, len(rows_ok), (NB, len(rows_ok)))
        ci = lambda arr: [round(float(np.mean(arr)), 2), round(float(np.percentile(np.asarray(arr)[bs].mean(1), 2.5)), 2), round(float(np.percentile(np.asarray(arr)[bs].mean(1), 97.5)), 2)]
        return dict(
            n=len(rows_ok), n_train=len(tr), n_test=len(te),
            v1_train=round(float(np.mean([x['v1'] for x in tr])), 2) if tr else None,
            v1_test=round(float(np.mean([x['v1'] for x in te])), 2) if te else None,
            v1_all=round(float(np.mean([x['v1'] for x in rows_ok])), 2) if rows_ok else None,
            v2_train=round(float(np.mean([x['v2'] for x in tr])), 2) if tr else None,
            v2_test=round(float(np.mean([x['v2'] for x in te])), 2) if te else None,
            v2_all=round(float(np.mean([x['v2'] for x in rows_ok])), 2) if rows_ok else None,
            delta_v1_vs_base=ci(d_v1) if arm_name != 'base' else [0.0, 0.0, 0.0],
            delta_v2_vs_base=ci(d_v2) if arm_name != 'base' else [0.0, 0.0, 0.0],
            n_picker_applied=sum(1 for x in rows_ok if x['fam'] == 'picker_style_gated'),
            fams=dict(fams),
        )

    summary = dict(base=_summarize('base', [base_by_id[r['id']] for r in recs]))
    print(f"PINNED base repro: v1={summary['base']['v1_train']}/{summary['base']['v1_test']} (target 32.40/34.07) v2={summary['base']['v2_train']}/{summary['base']['v2_test']}", flush=True)

    for arm, mpath in arms:
        mp_tab = json.load(open(mpath))
        by_yt = mp_tab.get('by_yt') or {}
        ck = os.path.join(W, f'pinned_{arm}.jsonl')
        have = {}
        if os.path.exists(ck):
            for l in open(ck):
                if l.strip():
                    row = json.loads(l)
                    if not row.get('error'):
                        have[row['id']] = row
        todo = []
        for i, r in enumerate(recs):
            if r['id'] in have:
                continue
            key = f"{r['a']['yt']}|{r['b']['yt']}"
            if key not in by_yt:
                b_copy = dict(base_by_id[r['id']], arm=arm, abstained_to_base=True)
                with open(ck, 'a') as fh:
                    fh.write(json.dumps(b_copy, default=str) + '\n')
                have[r['id']] = b_copy
            else:
                todo.append((arm, mpath, i, r))
        print(f'PINNED {arm}: {len(have)} cached (incl abstains), {len(todo)} to render', flush=True)
        if todo:
            with mp.get_context('spawn').Pool(int(os.environ.get('PINW', 2)), maxtasksperchild=4) as pool:
                for row in pool.imap_unordered(_pinned_worker, todo):
                    with open(ck, 'a') as fh:
                        fh.write(json.dumps(row, default=str) + '\n')
                    print(arm, row['id'], row.get('fam'), row.get('win'), 'v1=', row.get('v1'), 'v2=', row.get('v2'), row.get('error', '')[-120:], flush=True)
                    if not row.get('error'):
                        have[row['id']] = row
        rows_ok = [have[r['id']] for r in recs if r['id'] in have]
        summary[arm] = _summarize(arm, rows_ok)
        outp = os.path.join(H, 'picker_1125_followup_pinned.json')
        json.dump(summary, open(outp, 'w'), indent=2)
        print('PINNED CHECKPOINT', arm, json.dumps(summary[arm]), flush=True)
    print('PINNED SUMMARY:', json.dumps(summary, indent=2), flush=True)


def train_predict_djbal(tr, te):
    ensure_sec_cue_cache(tr)
    ensure_sec_cue_cache(te)
    eC_dj, ciC_dj, tauC_dj = inner_cue_djbal(tr)
    mC_dj = fit_cue_djbal(tr, B.CFGS[ciC_dj])
    SC_dj = scores_cue_sec(mC_dj, te)
    jc_dj = [B.gpick(r, 'C', s, tauC_dj) for r, s in zip(te, SC_dj)]

    eE_mix, mg_best = inner_mix_margin(tr)
    mods_mix = fit_mix_exit_models(tr)
    mix_preds = predict_mix_exit(mods_mix, te)
    je_mix = [jb if gain >= mg_best else r['Edix'] for r, (jb, gain, _, _, _) in zip(te, mix_preds)]

    D = {}
    D['djbal_cue_defexit'] = [B.decide(r, r['Edix'], c, r['dX']) for r, c in zip(te, jc_dj)]
    D['djbal_cue_sec_mix'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, je_mix, jc_dj)]
    for x, (_, gain, p, a, b) in zip(D['djbal_cue_sec_mix'], mix_preds):
        x['p_early'] = round(p, 3)
        x['mu_early'] = round(a, 1)
        x['mu_late'] = round(b, 1)
        x['risk_gain'] = round(gain, 2)
    diag = dict(
        cue_djbal=dict(cfg=ciC_dj, tau=tauC_dj, inner_djbal=round(float(eC_dj), 2)),
        mix_exit=dict(margin=mg_best, inner=round(float(eE_mix), 2)),
        cue_abstain_rate=round(float(np.mean([c == r['Cdix'] for r, c in zip(te, jc_dj)])), 3),
    )
    return D, diag


def _fold_djbal(args):
    d, dev = args
    tr = [r for r in dev if r['dj'] != d]
    te = [r for r in dev if r['dj'] == d]
    D, diag = train_predict_djbal(tr, te)
    print('djbal_fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag


def _slice_metrics(pp_sub, arms):
    late = [r for r in pp_sub if r['pro_out'] >= r['na'] - 40]
    mid = [r for r in pp_sub if r['pro_out'] < r['na'] - 40]
    out = {}
    for a in arms:
        ee = [abs(r[a]['exit'] - r['pro_out']) for r in pp_sub]
        ce = [abs(r[a]['cue'] - r['pro_in']) for r in pp_sub]
        ec = [(x + y) / 2.0 for x, y in zip(ee, ce)]
        out[a] = dict(
            n=len(pp_sub),
            exit_cue_mean=round(float(np.mean(ec)), 2),
            exit_mean=round(float(np.mean(ee)), 2),
            exit_median=round(float(np.median(ee)), 1),
            exit_hit8=round(float(np.mean([x <= 8 for x in ee])), 3),
            exit_hit16=round(float(np.mean([x <= 16 for x in ee])), 3),
            cue_mean=round(float(np.mean(ce)), 2),
            cue_median=round(float(np.median(ce)), 1),
            cue_hit8=round(float(np.mean([x <= 8 for x in ce])), 3),
            cue_hit16=round(float(np.mean([x <= 16 for x in ce])), 3),
            exit_moved=round(float(np.mean([r[a]['exit'] != r['default']['exit'] for r in pp_sub])), 3),
            cue_moved=round(float(np.mean([r[a]['cue'] != r['default']['cue'] for r in pp_sub])), 3),
            abstain=round(float(np.mean([r[a].get('is_default', False) for r in pp_sub])), 3),
            pro_mid_exit_mean=round(float(np.mean([abs(r[a]['exit'] - r['pro_out']) for r in mid])), 2) if mid else None,
            pro_late_exit_mean=round(float(np.mean([abs(r[a]['exit'] - r['pro_out']) for r in late])), 2) if late else None,
        )
    return out


def run_djbal_cv():
    from concurrent.futures import ProcessPoolExecutor
    prev = json.load(open(os.path.join(H, 'picker_1125_followup_cv.json')))
    prev_by_id = {r['id']: r for r in prev['per_pair']}

    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    ensure_sec_cue_cache(dev)
    djs = sorted({r['dj'] for r in dev})

    folds = {}
    pred_by_arm = {'djbal_cue_defexit': {}, 'djbal_cue_sec_mix': {}}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('DJBAL_W', 4))) as ex:
        for d, ids, D, diag in ex.map(_fold_djbal, [(d, dev) for d in djs]):
            folds[d] = diag
            for a in pred_by_arm:
                for pid, val in zip(ids, D[a]):
                    pred_by_arm[a][pid] = val

    pp = []
    for r in dev:
        row = dict(prev_by_id[r['id']])
        for a in ('djbal_cue_defexit', 'djbal_cue_sec_mix'):
            row[a] = pred_by_arm[a][r['id']]
        pp.append(row)

    all_arms = ['default', 'majority', 'cueonly_gated', 'hybrid_sec_cue', 'hybrid_sec_mix', 'ridegate', 'djbal_cue_defexit', 'djbal_cue_sec_mix']
    boots_all = clustered_boots(pp, ['cueonly_gated', 'hybrid_sec_cue', 'hybrid_sec_mix', 'djbal_cue_defexit', 'djbal_cue_sec_mix'])
    pp_nonkush = [r for r in pp if r['dj'] != 'KushSessions']
    pp_kush = [r for r in pp if r['dj'] == 'KushSessions']
    boots_nonkush = clustered_boots(pp_nonkush, ['cueonly_gated', 'hybrid_sec_cue', 'hybrid_sec_mix', 'djbal_cue_defexit', 'djbal_cue_sec_mix'])

    slices = dict(
        all_843=_slice_metrics(pp, all_arms),
        non_kush_437=_slice_metrics(pp_nonkush, all_arms),
        kush_406=_slice_metrics(pp_kush, all_arms),
    )
    out = dict(
        n=len(pp), n_mixes=len({r['mix'] for r in pp}), n_djs=len(djs),
        folds=folds, slices=slices, bootstraps_all=boots_all, bootstraps_nonkush=boots_nonkush,
        per_pair=pp,
    )
    outp = os.path.join(H, 'picker_1125_djbal_cv.json')
    json.dump(out, open(outp, 'w'), indent=1, default=str)
    print('Saved DJBAL CV to', outp, flush=True)
    for sl_name, sl in slices.items():
        print(f'=== SLICE {sl_name} ===', flush=True)
        for a, m in sl.items():
            print(f"  {a:18s} ec={m['exit_cue_mean']} exit={m['exit_mean']}(med {m['exit_median']}, @8 {m['exit_hit8']}, @16 {m['exit_hit16']}) "
                  f"cue={m['cue_mean']}(med {m['cue_median']}, @8 {m['cue_hit8']}, @16 {m['cue_hit16']}) cmov={m['cue_moved']} emov={m['exit_moved']}", flush=True)
    for btype in ('mix_clustered', 'pair_clustered'):
        for a in ('djbal_cue_defexit', 'djbal_cue_sec_mix', 'hybrid_sec_cue', 'hybrid_sec_mix'):
            for ref in ('default', 'majority'):
                d = boots_all[btype][f'{a}_vs_{ref}']
                dn = boots_nonkush[btype][f'{a}_vs_{ref}']
                print(f"CI_ALL[{btype}] {a}_vs_{ref}: ec={d['exit_cue']} exit={d['exit']} cue={d['cue']} c@8={d['cue_hit8_gain']} c@16={d['cue_hit16_gain']}", flush=True)
                print(f"CI_NONKUSH[{btype}] {a}_vs_{ref}: ec={dn['exit_cue']} exit={dn['exit']} cue={dn['cue']} c@8={dn['cue_hit8_gain']} c@16={dn['cue_hit16_gain']}", flush=True)


def run_djbal_maps():
    import run_admitted_tune as T
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    te = [r for r in rows if r['set'] == 'protrans']
    D, diag = train_predict_djbal(dev, te)
    recs = {r['id']: r for r in T.load_recs()}
    out = dict(n=len(te), diag=diag, maps={})
    for arm in ('djbal_cue_defexit', 'djbal_cue_sec_mix'):
        by_yt, by_id = {}, {}
        for r, x in zip(te, D[arm]):
            rec = recs.get(r['id'])
            key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
            by_id[r['id']] = dict(win=x.get('win'), exit=x['exit'], cue=x['cue'], X=x['X'],
                                  abstain=bool(x.get('is_default')), yt_key=key)
            if key and x.get('win') and not x.get('is_default'):
                by_yt[key] = x['win']
        mp = dict(
            written='2026-11-25 djbal followup',
            model=f'picker_1125_followup {arm} (DJ-balanced cue, tau>0, PICKER_INJECT_CS=1), trained on {len(dev)} dev, applied to 33 protrans pairs',
            by_yt=by_yt, by_id=by_id,
            do_not='write rules.json or treat this map as a promotion',
        )
        dest = os.path.join(W, f'map_{arm}.json')
        json.dump(mp, open(dest, 'w'), indent=1, default=str)
        out['maps'][arm] = dict(path=dest, n_windows=len(by_yt), n_total=len(by_id))
    json.dump(out, open(os.path.join(H, 'picker_1125_djbal_protrans_maps.json'), 'w'), indent=1, default=str)
    print('Wrote DJBAL protrans maps:', out['maps'], 'diag:', diag, flush=True)


def run_djbal_pinned():
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, run_admitted_tune as T, score_v2 as S2
    recs = T.load_recs()

    for arm in ('djbal_cue_defexit', 'djbal_cue_sec_mix'):
        if not os.path.exists(os.path.join(W, f'map_{arm}.json')):
            run_djbal_maps()
            break

    cohort_base_p = os.path.join(P0, 'research_1124', 'scorev2', 'cohort_base.jsonl')
    base_by_id = {}
    for l in open(cohort_base_p):
        if l.strip():
            row = json.loads(l)
            if not row.get('error'):
                pl = S2.placement_score(row['placement']['ours'], row['placement']['pro'])
                row['placement']['parts'] = pl
                row['v2'] = round(S2.combine(row['v1'], row['v1_breakdown'], pl), 2)
                base_by_id[row['id']] = row

    prev_pinned = json.load(open(os.path.join(H, 'picker_1125_followup_pinned.json')))
    summary = dict(prev_pinned)

    import multiprocessing as mp
    def _summarize(arm_name, rows_ok):
        tr = [x for x in rows_ok if x['split'] == 'train']
        te = [x for x in rows_ok if x['split'] == 'test']
        fams = collections.Counter(x['fam'] for x in rows_ok)
        d_v1 = [x['v1'] - base_by_id[x['id']]['v1'] for x in rows_ok]
        d_v2 = [x['v2'] - base_by_id[x['id']]['v2'] for x in rows_ok]
        mix_ids = sorted({x['id'].rsplit('__', 1)[0] for x in rows_ok})
        idx_m = collections.defaultdict(list)
        for i, x in enumerate(rows_ok):
            idx_m[x['id'].rsplit('__', 1)[0]].append(i)
        rng = np.random.default_rng(SEED)
        BS_pair = rng.integers(0, len(rows_ok), (NB, len(rows_ok)))
        BS_mix = [np.concatenate([idx_m[mix_ids[m]] for m in rng.choice(len(mix_ids), len(mix_ids))]) for _ in range(NB)]
        ci_pair = lambda arr: [round(float(np.mean(arr)), 2), round(float(np.percentile(np.asarray(arr)[BS_pair].mean(1), 2.5)), 2), round(float(np.percentile(np.asarray(arr)[BS_pair].mean(1), 97.5)), 2)]
        ci_mix = lambda arr: [round(float(np.mean(arr)), 2), round(float(np.percentile([np.asarray(arr)[ii].mean() for ii in BS_mix], 2.5)), 2), round(float(np.percentile([np.asarray(arr)[ii].mean() for ii in BS_mix], 97.5)), 2)]
        eb, ea, pe, px, ps = [], [], [], [], []
        for x in rows_ok:
            pl = x['placement']; pr, ou = pl['pro'], pl['ours']
            if pr.get('entry', {}).get('b') is not None and ou.get('entry', {}).get('b') is not None:
                eb.append(abs(ou['entry']['b'] - pr['entry']['b']))
            if pr.get('gone', {}).get('a') is not None and ou.get('gone', {}).get('a') is not None:
                ea.append(abs(ou['gone']['a'] - pr['gone']['a']))
            if pl.get('parts'):
                pe.append(pl['parts']['entry']); px.append(pl['parts']['gone']); ps.append(pl['parts']['swap'])
        return dict(
            n=len(rows_ok), n_train=len(tr), n_test=len(te),
            v1_train=round(float(np.mean([x['v1'] for x in tr])), 2) if tr else None,
            v1_test=round(float(np.mean([x['v1'] for x in te])), 2) if te else None,
            v1_all=round(float(np.mean([x['v1'] for x in rows_ok])), 2) if rows_ok else None,
            v2_train=round(float(np.mean([x['v2'] for x in tr])), 2) if tr else None,
            v2_test=round(float(np.mean([x['v2'] for x in te])), 2) if te else None,
            v2_all=round(float(np.mean([x['v2'] for x in rows_ok])), 2) if rows_ok else None,
            delta_v1_vs_base_pair=ci_pair(d_v1),
            delta_v2_vs_base_pair=ci_pair(d_v2),
            delta_v1_vs_base_mix=ci_mix(d_v1),
            delta_v2_vs_base_mix=ci_mix(d_v2),
            place_parts=dict(entry=round(float(np.mean(pe)), 1), gone=round(float(np.mean(px)), 1), swap=round(float(np.mean(ps)), 1)),
            audio_b_entry_mae=round(float(np.mean(eb)), 1) if eb else None,
            audio_a_exit_mae=round(float(np.mean(ea)), 1) if ea else None,
            n_picker_applied=sum(1 for x in rows_ok if x['fam'] == 'picker_style_gated'),
            n_injected_cs=sum(1 for x in rows_ok if x.get('injected_cs')),
            fams=dict(fams),
        )

    for arm in ('djbal_cue_defexit', 'djbal_cue_sec_mix'):
        mpath = os.path.join(W, f'map_{arm}.json')
        mp_tab = json.load(open(mpath))
        by_yt = mp_tab.get('by_yt') or {}
        ck = os.path.join(W, f'pinned_{arm}.jsonl')
        have = {}
        if os.path.exists(ck):
            for l in open(ck):
                if l.strip():
                    row = json.loads(l)
                    if not row.get('error'):
                        have[row['id']] = row
        todo = []
        for i, r in enumerate(recs):
            if r['id'] in have:
                continue
            key = f"{r['a']['yt']}|{r['b']['yt']}"
            if key not in by_yt:
                b_copy = dict(base_by_id[r['id']], arm=arm, abstained_to_base=True, injected_cs=False)
                with open(ck, 'a') as fh:
                    fh.write(json.dumps(b_copy, default=str) + '\n')
                have[r['id']] = b_copy
            else:
                todo.append((arm, mpath, i, r))
        print(f'DJBAL_PINNED {arm}: {len(have)} cached (incl abstains), {len(todo)} to render', flush=True)
        if todo:
            with mp.get_context('spawn').Pool(int(os.environ.get('PINW', 4)), maxtasksperchild=4) as pool:
                for row in pool.imap_unordered(_pinned_worker, todo):
                    with open(ck, 'a') as fh:
                        fh.write(json.dumps(row, default=str) + '\n')
                    print(arm, row['id'], row.get('fam'), 'inj=', row.get('injected_cs'), row.get('win'), 'v1=', row.get('v1'), 'v2=', row.get('v2'), row.get('error', '')[-120:], flush=True)
                    if not row.get('error'):
                        have[row['id']] = row
        rows_ok = [have[r['id']] for r in recs if r['id'] in have]
        summary[arm] = _summarize(arm, rows_ok)
        outp = os.path.join(H, 'picker_1125_djbal_pinned.json')
        json.dump(summary, open(outp, 'w'), indent=2)
        print('DJBAL_PINNED CHECKPOINT', arm, json.dumps(summary[arm]), flush=True)


MARGINS_ASYM = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 1e9]
MIN_NA_GRID = [0, 190, 200]


def inner_asym_mix_gate(tr):
    """Learn late-safe (min_na, margin) gate via inner leave-one-DJ-out CV optimizing asymmetric regret:
    |ex - pro_out| + 1.0 * max(0, |ex - pro_out| - |dex - pro_out|) on dev pairs only."""
    djs = sorted({r['dj'] for r in tr})
    oof = {}
    for d in djs:
        a = [r for r in tr if r['dj'] != d]
        b = [r for r in tr if r['dj'] == d]
        mods = fit_mix_exit_models(a)
        for r, pred in zip(b, predict_mix_exit(mods, b)):
            oof[r['id']] = pred
    best = None
    for min_na in MIN_NA_GRID:
        for mg in MARGINS_ASYM:
            losses = []
            for r in tr:
                jb, gain, _, _, _ = oof[r['id']]
                go = (na_(r) >= min_na) and (gain >= mg) and (jb != r['Edix'])
                ex = r['E'][jb]['v'] if go else r['dex']
                e_x = abs(ex - r['pro_out'])
                e_d = abs(r['dex'] - r['pro_out'])
                losses.append(e_x + 1.0 * max(0.0, e_x - e_d))
            ml = float(np.mean(losses))
            if best is None or ml < best[0]:
                best = (ml, min_na, mg)
    return best


def train_predict_asym(tr, te):
    ensure_sec_cue_cache(tr)
    ensure_sec_cue_cache(te)
    eC_dj, ciC_dj, tauC_dj = inner_cue_djbal(tr)
    mC_dj = fit_cue_djbal(tr, B.CFGS[ciC_dj])
    SC_dj = scores_cue_sec(mC_dj, te)
    jc_dj = [B.gpick(r, 'C', s, tauC_dj) for r, s in zip(te, SC_dj)]

    eE_asym, min_na_best, mg_best = inner_asym_mix_gate(tr)
    mods_mix = fit_mix_exit_models(tr)
    mix_preds = predict_mix_exit(mods_mix, te)
    je_asym = [
        jb if (na_(r) >= min_na_best and gain >= mg_best) else r['Edix']
        for r, (jb, gain, _, _, _) in zip(te, mix_preds)
    ]

    D = {}
    D['djbal_cue_asym_mix'] = [B.decide(r, j, c, r['dX']) for r, j, c in zip(te, je_asym, jc_dj)]
    for x, (_, gain, p, a, b) in zip(D['djbal_cue_asym_mix'], mix_preds):
        x['p_early'] = round(p, 3)
        x['mu_early'] = round(a, 1)
        x['mu_late'] = round(b, 1)
        x['risk_gain'] = round(gain, 2)
    diag = dict(
        cue_djbal=dict(cfg=ciC_dj, tau=tauC_dj, inner_djbal=round(float(eC_dj), 2)),
        asym_exit=dict(min_na=min_na_best, margin=mg_best, inner_asym2=round(float(eE_asym), 2)),
        cue_abstain_rate=round(float(np.mean([c == r['Cdix'] for r, c in zip(te, jc_dj)])), 3),
        exit_moved_rate=round(float(np.mean([j != r['Edix'] for r, j in zip(te, je_asym)])), 3),
    )
    return D, diag


def _fold_asym(args):
    d, dev = args
    tr = [r for r in dev if r['dj'] != d]
    te = [r for r in dev if r['dj'] == d]
    D, diag = train_predict_asym(tr, te)
    print('asym_fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], D, diag


def run_asym_cv():
    from concurrent.futures import ProcessPoolExecutor
    prev = json.load(open(os.path.join(H, 'picker_1125_djbal_cv.json')))
    prev_by_id = {r['id']: r for r in prev['per_pair']}

    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    ensure_sec_cue_cache(dev)
    djs = sorted({r['dj'] for r in dev})

    folds = {}
    preds = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('DJBAL_W', 4))) as ex:
        for d, ids, D, diag in ex.map(_fold_asym, [(d, dev) for d in djs]):
            folds[d] = diag
            for pid, val in zip(ids, D['djbal_cue_asym_mix']):
                preds[pid] = val

    pp = []
    for r in dev:
        row = dict(prev_by_id[r['id']])
        row['djbal_cue_asym_mix'] = preds[r['id']]
        pp.append(row)

    all_arms = ['default', 'majority', 'djbal_cue_defexit', 'djbal_cue_sec_mix', 'djbal_cue_asym_mix']
    boots_all = clustered_boots(pp, ['djbal_cue_defexit', 'djbal_cue_sec_mix', 'djbal_cue_asym_mix'])
    pp_nk = [r for r in pp if r['dj'] != 'KushSessions']
    pp_k = [r for r in pp if r['dj'] == 'KushSessions']
    boots_nk = clustered_boots(pp_nk, ['djbal_cue_defexit', 'djbal_cue_sec_mix', 'djbal_cue_asym_mix'])
    slices = dict(
        all_843=_slice_metrics(pp, all_arms),
        non_kush_437=_slice_metrics(pp_nk, all_arms),
        kush_406=_slice_metrics(pp_k, all_arms),
    )
    out = dict(
        n=len(pp), n_mixes=len({r['mix'] for r in pp}), n_djs=len(djs),
        folds=folds, slices=slices, bootstraps_all=boots_all, bootstraps_nonkush=boots_nk, per_pair=pp,
    )
    outp = os.path.join(H, 'picker_1125_asym_cv.json')
    json.dump(out, open(outp, 'w'), indent=1, default=str)
    print('Saved ASYM CV to', outp, flush=True)
    for sl_name, sl in slices.items():
        print(f'=== ASYM SLICE {sl_name} ===', flush=True)
        for a, m in sl.items():
            print(f"  {a:20s} ec={m['exit_cue_mean']} exit={m['exit_mean']}(med {m['exit_median']}, @8 {m['exit_hit8']}, @16 {m['exit_hit16']}, mid={m['pro_mid_exit_mean']}, late={m['pro_late_exit_mean']}) "
                  f"cue={m['cue_mean']}(@16 {m['cue_hit16']}) emov={m['exit_moved']} cmov={m['cue_moved']}", flush=True)
    for btype in ('mix_clustered', 'pair_clustered'):
        for ref in ('default', 'majority'):
            d = boots_all[btype][f'djbal_cue_asym_mix_vs_{ref}']
            dn = boots_nk[btype][f'djbal_cue_asym_mix_vs_{ref}']
            print(f"CI_ALL[{btype}] djbal_cue_asym_mix_vs_{ref}: ec={d['exit_cue']} exit={d['exit']} cue={d['cue']} e@16={d['exit_hit16_gain']} c@16={d['cue_hit16_gain']}", flush=True)
            print(f"CI_NONKUSH[{btype}] djbal_cue_asym_mix_vs_{ref}: ec={dn['exit_cue']} exit={dn['exit']} cue={dn['cue']} e@16={dn['exit_hit16_gain']} c@16={dn['cue_hit16_gain']}", flush=True)


def run_asym_maps():
    import run_admitted_tune as T
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    te = [r for r in rows if r['set'] == 'protrans']
    D, diag = train_predict_asym(dev, te)
    recs = {r['id']: r for r in T.load_recs()}
    by_yt, by_id = {}, {}
    for r, x in zip(te, D['djbal_cue_asym_mix']):
        rec = recs.get(r['id'])
        key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
        by_id[r['id']] = dict(win=x.get('win'), exit=x['exit'], cue=x['cue'], X=x['X'],
                              abstain=bool(x.get('is_default')), yt_key=key)
        if key and x.get('win') and not x.get('is_default'):
            by_yt[key] = x['win']
    mp = dict(
        written='2026-11-25 asym followup',
        model=f'picker_1125_followup djbal_cue_asym_mix (DJ-balanced cue tau>0, asym2 late-safe exit gate, PICKER_INJECT_CS=1), trained on {len(dev)} dev only, applied to 33 protrans pairs',
        diag=diag,
        by_yt=by_yt, by_id=by_id,
        do_not='write rules.json or treat this map as a promotion',
    )
    dest1 = os.path.join(W, 'map_djbal_cue_asym_mix.json')
    dest2 = os.path.join(H, 'picker_djbal_sec_mix_windows.json')
    json.dump(mp, open(dest1, 'w'), indent=1, default=str)
    json.dump(mp, open(dest2, 'w'), indent=1, default=str)
    out = dict(n=len(te), diag=diag, n_windows=len(by_yt), paths=[dest1, dest2])
    json.dump(out, open(os.path.join(H, 'picker_1125_asym_protrans_maps.json'), 'w'), indent=1, default=str)
    print('Wrote ASYM protrans maps:', out, flush=True)


def run_asym_pinned():
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, run_admitted_tune as T, score_v2 as S2
    recs = T.load_recs()

    mpath = os.path.join(W, 'map_djbal_cue_asym_mix.json')
    if not os.path.exists(mpath):
        run_asym_maps()

    cohort_base_p = os.path.join(P0, 'research_1124', 'scorev2', 'cohort_base.jsonl')
    base_by_id = {}
    for l in open(cohort_base_p):
        if l.strip():
            row = json.loads(l)
            if not row.get('error'):
                pl = S2.placement_score(row['placement']['ours'], row['placement']['pro'])
                row['placement']['parts'] = pl
                row['v2'] = round(S2.combine(row['v1'], row['v1_breakdown'], pl), 2)
                base_by_id[row['id']] = row

    summary = json.load(open(os.path.join(H, 'picker_1125_djbal_pinned.json')))
    import multiprocessing as mp

    def _ci_subset(rows_sub, metric):
        d = [x[metric] - base_by_id[x['id']][metric] for x in rows_sub]
        mix_ids = sorted({x['id'].rsplit('__', 1)[0] for x in rows_sub})
        idx_m = collections.defaultdict(list)
        for i, x in enumerate(rows_sub):
            idx_m[x['id'].rsplit('__', 1)[0]].append(i)
        rng = np.random.default_rng(SEED)
        BS_p = rng.integers(0, len(rows_sub), (NB, len(rows_sub)))
        BS_m = [np.concatenate([idx_m[mix_ids[m]] for m in rng.choice(len(mix_ids), len(mix_ids))]) for _ in range(NB)]
        arr = np.asarray(d)
        return dict(
            pair=[round(float(arr.mean()), 2), round(float(np.percentile(arr[BS_p].mean(1), 2.5)), 2), round(float(np.percentile(arr[BS_p].mean(1), 97.5)), 2)],
            mix=[round(float(arr.mean()), 2), round(float(np.percentile([arr[ii].mean() for ii in BS_m], 2.5)), 2), round(float(np.percentile([arr[ii].mean() for ii in BS_m], 97.5)), 2)],
        )

    arm = 'djbal_cue_asym_mix'
    mp_tab = json.load(open(mpath))
    by_yt = mp_tab.get('by_yt') or {}
    ck = os.path.join(W, f'pinned_{arm}.jsonl')
    have = {}
    if os.path.exists(ck):
        for l in open(ck):
            if l.strip():
                row = json.loads(l)
                if not row.get('error'):
                    have[row['id']] = row
    todo = []
    for i, r in enumerate(recs):
        if r['id'] in have:
            continue
        key = f"{r['a']['yt']}|{r['b']['yt']}"
        if key not in by_yt:
            b_copy = dict(base_by_id[r['id']], arm=arm, abstained_to_base=True, injected_cs=False)
            with open(ck, 'a') as fh:
                fh.write(json.dumps(b_copy, default=str) + '\n')
            have[r['id']] = b_copy
        else:
            todo.append((arm, mpath, i, r))
    print(f'ASYM_PINNED {arm}: {len(have)} cached (incl abstains), {len(todo)} to render', flush=True)
    if todo:
        with mp.get_context('spawn').Pool(int(os.environ.get('PINW', 2)), maxtasksperchild=4) as pool:
            for row in pool.imap_unordered(_pinned_worker, todo):
                with open(ck, 'a') as fh:
                    fh.write(json.dumps(row, default=str) + '\n')
                print(arm, row['id'], row.get('fam'), row.get('win'), 'v1=', row.get('v1'), 'v2=', row.get('v2'), row.get('error', '')[-120:], flush=True)
                if not row.get('error'):
                    have[row['id']] = row
    rows_ok = [have[r['id']] for r in recs if r['id'] in have]
    tr = [x for x in rows_ok if x['split'] == 'train']
    te = [x for x in rows_ok if x['split'] == 'test']
    eb, ea, pe, px, ps = [], [], [], [], []
    for x in rows_ok:
        pl = x['placement']; pr, ou = pl['pro'], pl['ours']
        if pr.get('entry', {}).get('b') is not None and ou.get('entry', {}).get('b') is not None:
            eb.append(abs(ou['entry']['b'] - pr['entry']['b']))
        if pr.get('gone', {}).get('a') is not None and ou.get('gone', {}).get('a') is not None:
            ea.append(abs(ou['gone']['a'] - pr['gone']['a']))
        if pl.get('parts'):
            pe.append(pl['parts']['entry']); px.append(pl['parts']['gone']); ps.append(pl['parts']['swap'])
    summary[arm] = dict(
        n=len(rows_ok), n_train=len(tr), n_test=len(te),
        v1_train=round(float(np.mean([x['v1'] for x in tr])), 2),
        v1_test=round(float(np.mean([x['v1'] for x in te])), 2),
        v1_all=round(float(np.mean([x['v1'] for x in rows_ok])), 2),
        v2_train=round(float(np.mean([x['v2'] for x in tr])), 2),
        v2_test=round(float(np.mean([x['v2'] for x in te])), 2),
        v2_all=round(float(np.mean([x['v2'] for x in rows_ok])), 2),
        delta_v1_all=_ci_subset(rows_ok, 'v1'),
        delta_v2_all=_ci_subset(rows_ok, 'v2'),
        delta_v1_train=_ci_subset(tr, 'v1'),
        delta_v2_train=_ci_subset(tr, 'v2'),
        delta_v1_test=_ci_subset(te, 'v1'),
        delta_v2_test=_ci_subset(te, 'v2'),
        place_parts=dict(entry=round(float(np.mean(pe)), 1), gone=round(float(np.mean(px)), 1), swap=round(float(np.mean(ps)), 1)),
        audio_b_entry_mae=round(float(np.mean(eb)), 1) if eb else None,
        audio_a_exit_mae=round(float(np.mean(ea)), 1) if ea else None,
        n_picker_applied=sum(1 for x in rows_ok if x['fam'] == 'picker_style_gated'),
        fams=dict(collections.Counter(x['fam'] for x in rows_ok)),
    )
    outp = os.path.join(H, 'picker_1125_asym_pinned.json')
    json.dump(summary, open(outp, 'w'), indent=2)
    print('ASYM_PINNED SUMMARY:', json.dumps(summary[arm], indent=2), flush=True)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'diagnose':
        run_diagnose()
    elif mode == 'cv':
        run_cv()
    elif mode == 'protrans_maps':
        run_protrans_maps()
    elif mode == 'eval_pinned':
        run_eval_pinned()
    elif mode == 'djbal_cv':
        run_djbal_cv()
    elif mode == 'djbal_maps':
        run_djbal_maps()
    elif mode == 'djbal_pinned':
        run_djbal_pinned()
    elif mode == 'asym_cv':
        run_asym_cv()
    elif mode == 'asym_maps':
        run_asym_maps()
    elif mode == 'asym_pinned':
        run_asym_pinned()
    else:
        raise SystemExit(f'unknown mode: {mode}')
