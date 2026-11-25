#!/usr/bin/env python3
"""Early-exit per-pair picker (2026-11-25, trained on 843 dev pairs only, 25-fold leave-one-DJ-out CV).

Builds on picker_1125_followup.py's section-aware cue ranker + Bayes-mixture exit gate,
adding:
  - DJ-balanced exit & regret models (so KushSessions doesn't dominate non-Kush priors).
  - Post-drop-1 breakdown early-exit window construction (X in 32..44 bars, cue aligned
    ~16 bars before B's drop1) ONLY when the per-pair model chooses an early exit
    (na - ex >= 24 and ex in breakdown/mid-track); otherwise keeps the safe outro blend.
  - Ranked shortlist (K <= 6) across early-exit candidate X/ex/cue combinations for
    select_compatible_picker_window.
  - Reports exit MAE, cue MAE, play_time_sec vs pro, and mix/pair-clustered 95% CIs.
Does NOT touch rules.json or tune against the 12 held-out pinned pairs.
"""
from __future__ import annotations
import collections, json, os, sys
import numpy as np
import lightgbm as lgb

H = os.path.dirname(os.path.abspath(__file__))
P0 = os.path.dirname(H)
sys.path.insert(0, H)
sys.path.insert(0, P0)

import picker_1119 as P
import picker_1119b as B
import picker_1125_followup as F

W = os.path.join(H, 'nightly_1125_work')
os.makedirs(W, exist_ok=True)
P.W = W
P.SPENT_FRESH = F.FRESH_ALL
B.W = W
SEED = 20261125
NB = 4000


def _is_bd_early_exit(r):
    """True when pro exited early AFTER drop1 and BEFORE/AT drop2 (post-drop-1 breakdown or 1-drop early exit)."""
    na = float(F.na_(r))
    po = float(r['pro_out'])
    if (na - po) < 28.0:
        return False
    da = F.real_drops(r['sa'])
    if not da:
        return True
    d1e = float(da[0][1])
    if po < d1e - 4.0:
        return False
    if len(da) >= 2 and po > float(da[1][0]) + 12.0:
        return False
    return True


def _fit_djbal_mix_exit_models(tr):
    """Fit P(post-drop-1 BD early exit), E[exit|BD], E[exit|other] on tr with DJ-balanced sample weights."""
    X = np.array([r['Xpair_sec'] for r in tr], float)
    w = np.asarray(F.dj_pair_weights(tr, cap=20.0), float)
    y_out = np.array([r['pro_out'] for r in tr], float)
    y_early = np.array([1.0 if _is_bd_early_exit(r) else 0.0 for r in tr], float)

    m_p = lgb.LGBMClassifier(
        n_estimators=120, num_leaves=7, learning_rate=0.05, min_child_samples=20,
        subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X, y_early, sample_weight=w)

    mask_e = y_early > 0.5
    mask_l = ~mask_e
    m_e = lgb.LGBMRegressor(
        n_estimators=120, num_leaves=7, learning_rate=0.05, min_child_samples=15,
        subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X[mask_e], y_out[mask_e], sample_weight=w[mask_e])
    m_l = lgb.LGBMRegressor(
        n_estimators=120, num_leaves=7, learning_rate=0.05, min_child_samples=15,
        subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(X[mask_l], y_out[mask_l], sample_weight=w[mask_l])
    return m_p, m_e, m_l



def _valid_ee_bar(r, v, min_rem=36.0):
    """Strict post-drop-1 breakdown (or single super-drop) eligibility: never jump past drop2 or late drop1."""
    v = float(v)
    na = int(F.na_(r))
    if na - v < min_rem:
        return False
    da = F.real_drops(r['sa'])
    if not da:
        return False
    d1s, d1e = da[0]
    if len(da) >= 2:
        d2s, _d2e = da[1]
        if d1e > 160 or d2s < 120 or (d2s - d1e) < 18:
            return False
        return (d1e - 4 <= v <= d2s - 12)
    if (d1e - d1s) >= 128:
        return v >= d1s + 24
    return d1e >= 120 and v >= d1e - 4


def _predict_valid_mix_exit(mods, rows_sub, min_rem=36.0):
    m_p, m_e, m_l = mods
    X = np.array([r['Xpair_sec'] for r in rows_sub], float)
    pe = m_p.predict_proba(X)[:, 1]
    me = m_e.predict(X)
    ml = m_l.predict(X)
    out = []
    for r, p, a, b in zip(rows_sub, pe, me, ml):
        p, a, b = float(p), float(a), float(b)
        na = int(F.na_(r))
        risks = [p * abs(c['v'] - a) + (1.0 - p) * abs(c['v'] - b) for c in r['E']]
        cands = [i for i, c in enumerate(r['E']) if i == r['Edix'] or (na - c['v'] < 24.0) or _valid_ee_bar(r, c['v'], min_rem)]
        jb = min(cands, key=lambda i: risks[i])
        gain = float(risks[r['Edix']] - risks[jb])
        out.append((jb, gain, p, a, b))
    return out


def _early_exit_cands_for_row(r, je, jc, m_eg, p, a, b, risks, k_max=6):
    """Build ranked shortlist for render-time compatibility.

    If je != r['Edix'] and na - ex >= 24 (early exit chosen per pair), build 32..44 bar
    post-drop-1 breakdown windows aligned to incoming drop1 (k_drop ~ 16 bars).
    Otherwise fall back to standard F.build_ranked_shortlist (safe outro blend).
    """
    na = int(F.na_(r))
    nb = int(r['sb'].get('music_end') or r['sb'].get('n_bars'))
    ex = float(r['E'][je]['v'])
    if je == r['Edix'] or (na - ex) < 36.0:
        return F.build_ranked_shortlist(r, je, jc, m_eg, 0.0, p, a, b, risks, k_max=k_max)

    da = F.real_drops(r['sa'])
    d2s = da[1][0] if (len(da) >= 2 and (da[1][1] - da[1][0]) >= 16) else None

    d1b = int(r['sb'].get('drop1') or 0)
    # Candidate cues for early exit: strongly prefer k_drop ~ 16 (ib = d1b - 16) so entry=0 and swap~16.
    # Only put cue_learned ahead of d1b-16 when cue_learned already places k_drop in [12, 18].
    cue_learned = int(round(r['C'][jc]['v']))
    kd_learned = d1b - (cue_learned - 1)
    cues = []
    if 12 <= kd_learned <= 18:
        cues.append(cue_learned)
    if d1b >= 16:
        cues.append(d1b - 15)  # ib = d1b - 16 -> drop1 at k=16
    if 8 <= kd_learned <= 20:
        cues.append(cue_learned)
    if d1b >= 12:
        cues.append(d1b - 11)  # ib = d1b - 12 -> drop1 at k=12
    if d1b >= 20:
        cues.append(d1b - 19)  # ib = d1b - 20 -> drop1 at k=20
    if d1b >= 24:
        cues.append(d1b - 23)  # ib = d1b - 24 -> drop1 at k=24 (fallback only)
    if not cues:
        cues.append(cue_learned)
    cues_uniq = []
    for c_v in cues:
        if c_v not in cues_uniq and c_v >= 1:
            cues_uniq.append(c_v)

    # Candidate exits: primary je, plus top 2 nearby valid early-exit bars in breakdown (within 24 bars)
    ex_order = [je]
    other_ex = [
        i for i in np.argsort(risks)
        if i != r['Edix'] and i != je and _valid_ee_bar(r, r['E'][i]['v'], 36.0) and abs(r['E'][i]['v'] - ex) <= 24.0
    ]
    ex_order.extend(int(i) for i in other_ex[:2])

    clean_out, fallback_out, seen = [], [], set()
    for ei in ex_order:
        ex_i = float(r['E'][ei]['v'])
        for cv in cues_uniq:
            ib = int(round(cv - 1))
            if ib < 0:
                continue
            kd = d1b - ib
            x_pref = int(np.clip(round((kd + 22) / 4.0) * 4, 36, 40))
            xs_try = [x_pref] + [x for x in (36, 40, 44) if x != x_pref]
            for XX in xs_try:
                e = int(round((ex_i + XX - 1) / 8.0) * 8)
                s_bar = e - XX
                if e <= na - 20 and s_bar >= 16 and _valid_ee_bar(r, s_bar, 36.0) and ib >= 0 and ib + XX <= nb - 16:
                    w = ['n', e, None, ib, XX]
                    tw = tuple(w)
                    if tw not in seen:
                        seen.add(tw)
                        # Prefer candidates whose incoming drop1 (s_bar + kd) lands before drop2 starts
                        if d2s is not None and (s_bar + kd) > d2s - 6 and s_bar < d2s:
                            fallback_out.append(w)
                        else:
                            clean_out.append(w)
    out = (clean_out + fallback_out)[:k_max]
    if not out:
        return F.build_ranked_shortlist(r, je, jc, m_eg, 0.0, p, a, b, risks, k_max=k_max)
    return out


def train_predict_early_exit(tr, te, asym_w=2.00):
    """Train cue ranker + DJ-balanced early-exit gate on tr (dev only), predict on te."""
    F.ensure_sec_cue_cache(tr)
    F.ensure_sec_cue_cache(te)
    djs_tr = sorted({r['dj'] for r in tr})
    w_tr = F.dj_pair_weights(tr, cap=20.0)

    # 1) Cue ranker + fast-cue guard (identical to djbal_cue_struct_compat)
    eC_dj, ciC, tau_slow = F.inner_cue_djbal(tr)
    oof_S_c = {}
    for d2 in djs_tr:
        a2 = [r for r in tr if r['dj'] != d2]
        b2 = [r for r in tr if r['dj'] == d2]
        m2 = F.fit_cue_djbal(a2, B.CFGS[ciC])
        for r, s in zip(b2, F.scores_cue_sec(m2, b2)):
            oof_S_c[r['id']] = s

    Xf_tr, yf_tr, wf_tr, fast_rows = [], [], [], []
    for r, w in zip(tr, w_tr):
        if r['dcue'] <= 17:
            s = oof_S_c[r['id']]
            j = int(np.argmax(s))
            if j != r['Cdix'] and (s[j] - s[r['Cdix']]) > 0.0:
                mg = float(s[j] - s[r['Cdix']])
                Xf_tr.append(F.fast_cue_feats(r, j, mg))
                yf_tr.append(float(abs(r['C'][j]['v'] - r['pro_in']) < abs(r['dcue'] - r['pro_in']) - 1.0))
                wf_tr.append(w)
                fast_rows.append((r, w, j))

    m_fc = lgb.LGBMClassifier(
        n_estimators=80, num_leaves=5, learning_rate=0.05, min_child_samples=15,
        subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(np.array(Xf_tr, float), np.array(yf_tr, float), sample_weight=np.array(wf_tr, float))

    dj_f = sorted({r['dj'] for r, _, _ in fast_rows})
    oof_p_fc = np.zeros(len(fast_rows))
    for k_fold in range(5):
        vd = set(dj_f[k_fold::5])
        itr = [i for i, (r, _, _) in enumerate(fast_rows) if r['dj'] not in vd]
        iva = [i for i, (r, _, _) in enumerate(fast_rows) if r['dj'] in vd]
        if not iva or len(set(yf_tr[i] for i in itr)) < 2:
            continue
        mf = lgb.LGBMClassifier(
            n_estimators=80, num_leaves=5, learning_rate=0.05, min_child_samples=15,
            subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
        )
        mf.fit(np.array([Xf_tr[i] for i in itr], float), np.array([yf_tr[i] for i in itr], float),
               sample_weight=np.array([wf_tr[i] for i in itr], float))
        oof_p_fc[iva] = mf.predict_proba(np.array([Xf_tr[i] for i in iva], float))[:, 1]

    best_fc = (1e9, 0.55)
    for thr in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 1.0]:
        errs = [
            w * abs(r['C'][j if oof_p_fc[idx] >= thr else r['Cdix']]['v'] - r['pro_in'])
            for idx, (r, w, j) in enumerate(fast_rows)
        ]
        me = float(sum(errs) / max(sum(w for _, w, _ in fast_rows), 1e-9))
        if me < best_fc[0]:
            best_fc = (me, thr)
    thr_fc = best_fc[1]

    mC = F.fit_cue_djbal(tr, B.CFGS[ciC])
    SC_te = F.scores_cue_sec(mC, te)
    jc_te = []
    for r, s in zip(te, SC_te):
        j = int(np.argmax(s))
        mg = float(s[j] - s[r['Cdix']])
        if r['dcue'] <= 17:
            if j != r['Cdix'] and mg > 0.0:
                p_ok = float(m_fc.predict_proba(np.array([F.fast_cue_feats(r, j, mg)], float))[:, 1][0])
                jc_te.append(j if p_ok >= thr_fc else r['Cdix'])
            else:
                jc_te.append(r['Cdix'])
        else:
            jc_te.append(j if mg > tau_slow else r['Cdix'])

    # 2) DJ-balanced mixture exit model + DJ-balanced regret gate (no min_na)
    oof_ex = {}
    for d2 in djs_tr:
        a2 = [r for r in tr if r['dj'] != d2]
        b2 = [r for r in tr if r['dj'] == d2]
        mods2 = _fit_djbal_mix_exit_models(a2)
        for r, pred in zip(b2, _predict_valid_mix_exit(mods2, b2, min_rem=36.0)):
            oof_ex[r['id']] = pred

    Xg_tr, yg_tr, wg_tr, gate_rows = [], [], [], []
    for r, w in zip(tr, w_tr):
        jb, gain, p, a, b = oof_ex[r['id']]
        if jb == r['Edix'] or gain <= 0:
            continue
        c = r['E'][jb]
        ex = float(c['v'])
        e_x = abs(ex - r['pro_out'])
        e_d = abs(r['dex'] - r['pro_out'])
        reg_gain = e_d - (e_x + (asym_w - 1.0) * max(0.0, e_x - e_d))
        Xg_tr.append(F.exit_struct_feats_no_na(r, c, p, a, b, gain))
        yg_tr.append(reg_gain)
        wg_tr.append(w)
        gate_rows.append((r, w, jb))

    m_eg = lgb.LGBMRegressor(
        n_estimators=100, num_leaves=5, learning_rate=0.05, min_child_samples=25,
        subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
    ).fit(np.array(Xg_tr, float), np.array(yg_tr, float), sample_weight=np.array(wg_tr, float))

    dj_g = sorted({r['dj'] for r, _, _ in gate_rows})
    oof_eg = np.zeros(len(gate_rows))
    for k_fold in range(5):
        vd = set(dj_g[k_fold::5])
        itr = [i for i, (r, _, _) in enumerate(gate_rows) if r['dj'] not in vd]
        iva = [i for i, (r, _, _) in enumerate(gate_rows) if r['dj'] in vd]
        if not iva:
            continue
        mgf = lgb.LGBMRegressor(
            n_estimators=100, num_leaves=5, learning_rate=0.05, min_child_samples=25,
            subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=1,
        )
        mgf.fit(np.array([Xg_tr[i] for i in itr], float), np.array([yg_tr[i] for i in itr], float),
                sample_weight=np.array([wg_tr[i] for i in itr], float))
        oof_eg[iva] = mgf.predict(np.array([Xg_tr[i] for i in iva], float))
    g_map = {r['id']: float(oof_eg[i]) for i, (r, _, _) in enumerate(gate_rows)}

    best_eg = (1e9, 0.0)
    for thr in [0.0, 3.0, 6.0, 10.0, 15.0, 20.0, 25.0]:
        losses = []
        ws_l = []
        for r, w in zip(tr, w_tr):
            jb, gain, p, a, b = oof_ex[r['id']]
            go = (jb != r['Edix'] and gain > 0 and g_map.get(r['id'], -1e9) >= thr)
            ex = float(r['E'][jb]['v']) if go else float(r['dex'])
            e_x = abs(ex - r['pro_out'])
            e_d = abs(r['dex'] - r['pro_out'])
            losses.append(w * (e_x + (asym_w - 1.0) * max(0.0, e_x - e_d)))
            ws_l.append(w)
        ml = float(sum(losses) / max(sum(ws_l), 1e-9))
        if ml < best_eg[0]:
            best_eg = (ml, thr)
    thr_eg = best_eg[1]

    mods_ex = _fit_djbal_mix_exit_models(tr)
    m_p, m_e, m_l = mods_ex
    X_ex_te = np.array([r['Xpair_sec'] for r in te], float)
    pe_te = m_p.predict_proba(X_ex_te)[:, 1]
    me_te = m_e.predict(X_ex_te)
    ml_te = m_l.predict(X_ex_te)

    decs = []
    for i, r in enumerate(te):
        p, a, b = float(pe_te[i]), float(me_te[i]), float(ml_te[i])
        na = int(F.na_(r))
        risks = [p * abs(c['v'] - a) + (1.0 - p) * abs(c['v'] - b) for c in r['E']]
        cands_valid = [ii for ii, cc in enumerate(r['E']) if ii == r['Edix'] or (na - cc['v'] < 24.0) or _valid_ee_bar(r, cc['v'], 36.0)]
        jb = min(cands_valid, key=lambda ii: risks[ii])
        gain = float(risks[r['Edix']] - risks[jb])

        je = r['Edix']
        if jb != r['Edix'] and gain > 0:
            rg = float(m_eg.predict(np.array([F.exit_struct_feats_no_na(r, r['E'][jb], p, a, b, gain)], float))[0])
            if rg >= thr_eg:
                je = jb

        jc = jc_te[i]
        ex_v = float(r['E'][je]['v'])
        is_ee = (je != r['Edix'] and (na - ex_v) >= 36.0)
        rk = _early_exit_cands_for_row(r, je, jc, m_eg, p, a, b, risks, k_max=6)
        if is_ee and rk and int(rk[0][4]) >= 36:
            w0 = rk[0]
            dec = dict(
                exit=float(w0[1] - w0[4] + 1),
                cue=float(w0[3] + 1),
                X=int(w0[4]),
                win=list(w0),
                is_default=False,
                early_exit=True,
                p_early=round(p, 3),
                mu_early=round(a, 1),
                mu_late=round(b, 1),
                risk_gain=round(gain, 2),
                ranked=rk,
            )
        else:
            dec = B.decide(r, je, jc, r['dX'])
            dec['early_exit'] = False
            dec['p_early'] = round(p, 3)
            dec['mu_early'] = round(a, 1)
            dec['mu_late'] = round(b, 1)
            dec['risk_gain'] = round(gain, 2)
            dec['ranked'] = rk
        decs.append(dec)

    diag = dict(
        asym_w=asym_w,
        cue_djbal=dict(cfg=ciC, tau_slow=tau_slow, thr_fast_cue=thr_fc, inner_djbal=round(float(eC_dj), 2)),
        early_exit_gate=dict(thr_regret=thr_eg, inner_djbal=round(float(best_eg[0]), 2)),
        cue_abstain_rate=round(float(np.mean([c == r['Cdix'] for r, c in zip(te, jc_te)])), 3),
        exit_moved_rate=round(float(np.mean([d['exit'] != r['dex'] for r, d in zip(te, decs)])), 3),
        early_exit_rate=round(float(np.mean([bool(d.get('early_exit')) for d in decs])), 3),
    )
    return decs, diag


def _fold_ee(args):
    d, dev, asym_w = args
    tr = [r for r in dev if r['dj'] != d]
    te = [r for r in dev if r['dj'] == d]
    decs, diag = train_predict_early_exit(tr, te, asym_w=asym_w)
    print('ee_fold', d, len(te), diag, flush=True)
    return d, [r['id'] for r in te], decs, diag


def run_cv(asym_w=2.00):
    from concurrent.futures import ProcessPoolExecutor
    prev = json.load(open(os.path.join(H, 'picker_1125_struct_cv.json')))
    prev_by_id = {r['id']: r for r in prev['per_pair']}

    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    F.ensure_sec_cue_cache(dev)
    djs = sorted({r['dj'] for r in dev})

    folds, preds = {}, {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('DJBAL_W', 4))) as ex:
        for d, ids, decs, diag in ex.map(_fold_ee, [(d, dev, asym_w) for d in djs]):
            folds[d] = diag
            for pid, val in zip(ids, decs):
                preds[pid] = val

    pp = []
    dev_by_id = {r['id']: r for r in dev}
    for r in dev:
        row = dict(prev_by_id[r['id']])
        row['early_exit'] = preds[r['id']]
        row['bpm_a'] = float(r['bpm'][0] or 174.0)
        pp.append(row)

    all_arms = ['default', 'djbal_cue_struct_compat', 'early_exit']
    boots_all = F.clustered_boots(pp, ['djbal_cue_struct_compat', 'early_exit'])
    pp_nk = [r for r in pp if r['dj'] != 'KushSessions']
    pp_k = [r for r in pp if r['dj'] == 'KushSessions']
    boots_nk = F.clustered_boots(pp_nk, ['djbal_cue_struct_compat', 'early_exit'])

    def _playtime(sub, arm):
        pro_s = np.array([r['pro_out'] * 240.0 / r['bpm_a'] for r in sub])
        arm_s = np.array([r[arm]['exit'] * 240.0 / r['bpm_a'] for r in sub])
        return dict(
            pro_mean_sec=round(float(pro_s.mean()), 1),
            arm_mean_sec=round(float(arm_s.mean()), 1),
            diff_sec=round(float(arm_s.mean() - pro_s.mean()), 1),
            mae_sec=round(float(np.abs(arm_s - pro_s).mean()), 1),
            pro_med_sec=round(float(np.median(pro_s)), 1),
            arm_med_sec=round(float(np.median(arm_s)), 1),
        )

    slices = dict(
        all_843=F._slice_metrics(pp, all_arms),
        non_kush_437=F._slice_metrics(pp_nk, all_arms),
        kush_406=F._slice_metrics(pp_k, all_arms),
    )
    playtimes = {
        sl_name: {a: _playtime(sub, a) for a in all_arms}
        for sl_name, sub in (('all_843', pp), ('non_kush_437', pp_nk), ('kush_406', pp_k))
    }
    out = dict(
        asym_w=asym_w,
        n=len(pp), n_mixes=len({r['mix'] for r in pp}), n_djs=len(djs),
        folds=folds, slices=slices, playtimes=playtimes,
        bootstraps_all=boots_all, bootstraps_nonkush=boots_nk, per_pair=pp,
    )
    outp = os.path.join(H, 'picker_1125_early_exit_cv.json')
    json.dump(out, open(outp, 'w'), indent=1, default=str)
    print('Saved EARLY_EXIT CV to', outp, flush=True)
    for sl_name, sl in slices.items():
        print(f'=== EARLY_EXIT SLICE {sl_name} ===', flush=True)
        for a, m in sl.items():
            pt = playtimes[sl_name][a]
            print(f"  {a:25s} ec={m['exit_cue_mean']} exit={m['exit_mean']}(@8={m['exit_hit8']}, @16={m['exit_hit16']}, mid={m['pro_mid_exit_mean']}, late={m['pro_late_exit_mean']}) "
                  f"cue={m['cue_mean']} emov={m['exit_moved']} play={pt['arm_mean_sec']}s(pro {pt['pro_mean_sec']}s, diff {pt['diff_sec']:+.1f}s)", flush=True)
    for btype in ('mix_clustered', 'pair_clustered'):
        d = boots_all[btype]['early_exit_vs_default']
        dn = boots_nk[btype]['early_exit_vs_default']
        print(f"CI_ALL[{btype}] early_exit_vs_default: ec={d['exit_cue']} exit={d['exit']} cue={d['cue']} e@16={d['exit_hit16_gain']}", flush=True)
        print(f"CI_NONKUSH[{btype}] early_exit_vs_default: ec={dn['exit_cue']} exit={dn['exit']} cue={dn['cue']} e@16={dn['exit_hit16_gain']}", flush=True)


def run_protrans_maps(asym_w=2.00):
    import run_admitted_tune as T
    rows = B.build(P.rows_all(), P.load_rendered_defaults())
    dev = [r for r in rows if r['set'] == 'dev']
    te = [r for r in rows if r['set'] == 'protrans']
    decs, diag = train_predict_early_exit(dev, te, asym_w=asym_w)
    recs = {r['id']: r for r in T.load_recs()}
    by_yt, ranked_by_yt, by_id = {}, {}, {}
    n_ee = 0
    for r, x in zip(te, decs):
        rec = recs.get(r['id'])
        key = f"{rec['a']['yt']}|{rec['b']['yt']}" if rec else None
        rk = x.get('ranked') or []
        by_id[r['id']] = dict(
            win=x.get('win'), ranked=rk, exit=x['exit'], cue=x['cue'], X=x['X'],
            early_exit=bool(x.get('early_exit')), abstain=bool(x.get('is_default')),
            p_early=x.get('p_early'), yt_key=key,
        )
        if x.get('early_exit'):
            n_ee += 1
        if key and x.get('win') and not x.get('is_default'):
            by_yt[key] = x['win']
            ranked_by_yt[key] = rk if rk else [x['win']]
    mp = dict(
        written='2026-11-25 early_exit picker',
        model=f'picker_1125_early_exit (DJ-balanced exit & cue rankers, EARLY_EXIT=1 breakdown shape on early exits, PICKER_INJECT_CS=1), trained on {len(dev)} dev only, applied to {len(te)} protrans pairs',
        diag=diag,
        n_early_exit=n_ee,
        by_yt=by_yt, ranked_by_yt=ranked_by_yt, by_id=by_id,
        do_not='write rules.json or treat this map as a promotion',
    )
    dest1 = os.path.join(W, 'map_early_exit.json')
    dest2 = os.path.join(H, 'picker_early_exit_windows.json')
    json.dump(mp, open(dest1, 'w'), indent=1, default=str)
    json.dump(mp, open(dest2, 'w'), indent=1, default=str)
    print(f'Wrote EARLY_EXIT protrans maps ({len(by_yt)}/{len(te)} non-default, {n_ee} early-exit): {dest2}', flush=True)
    return dest2




def _pinned_ee_worker(payload):
    arm, map_path, i, rec = payload
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    os.environ.setdefault('PROTRANS_SRC2', '/workspace/mixes/src2_pin_n1121')
    src2 = os.environ['PROTRANS_SRC2']
    os.chdir(src2)
    if map_path:
        os.environ['PICKER_STYLE_GATED'] = '1'
        os.environ['PICKER_STYLE_GATED_MAP'] = map_path
        os.environ['PICKER_INJECT_CS'] = '1'
        os.environ['EARLY_EXIT'] = '1'
    else:
        for k in ('PICKER_STYLE_GATED', 'PICKER_STYLE_GATED_MAP', 'PICKER_INJECT_CS', 'EARLY_EXIT'):
            os.environ.pop(k, None)
    import paths, recreate, score, score_v2 as S2, hardcheck as HC
    rules = json.load(open(paths.RULES))
    if map_path:
        rules['PICKER_STYLE_GATED'] = 1
        rules['PICKER_INJECT_CS'] = 1
        rules['EARLY_EXIT'] = 1
        rules['PICKER_STYLE_GATED_MAP'] = map_path
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    try:
        info = recreate.recreate(
            rec['a']['yt'], rec['b']['yt'], sa, sb,
            hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
            rules=rules, tag=f'ee_{arm[:4]}{i}',
        )
        dst = os.path.join(W, 'pinned_renders', arm, rec['id'] + '.mp3')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        import shutil
        shutil.copy(info['ours'], dst)
        v1 = score.score(rec['pro_clip'], dst, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
        r2 = S2.score_v2(rec['pro_clip'], dst, sa, sb, v1=v1)
        hc = HC.check(info['meta_path']) if info.get('meta_path') else None
        st_a = json.load(open(os.path.join(src2, 'st', rec['a']['yt'] + '.json')))
        bpm_a = float(st_a.get('bpm') or 174.0)
        pinfo = info.get('picker') or {}
        meta_saved = os.path.join(W, 'pinned_renders', arm, rec['id'] + '_meta.json')
        if info.get('meta_path') and os.path.exists(info['meta_path']):
            shutil.copy(info['meta_path'], meta_saved)
        return dict(
            id=rec['id'], split=rec['split'], dj=rec['dj'], mix_id=rec.get('mix_id') or rec['id'].rsplit('__', 1)[0],
            arm=arm, fam=info['fam'], win=info['win'], bpm_a=bpm_a,
            injected_cs=bool(pinfo.get('injected_cs')), picker_info=pinfo,
            v1=v1['score'],
            v1_breakdown={k: v1['breakdown'][k] for k in ('stem_curves', 'deck_curves', 'beat_align', 'bass_swap', 'outgoing_cut', 'blend_length')},
            v2=r2['official_v2'], placement=r2['placement'],
            hardcheck=hc, ours=dst, meta_path=meta_saved,
        )
    except Exception:
        import traceback
        return dict(id=rec['id'], split=rec['split'], dj=rec['dj'], arm=arm, error=traceback.format_exc()[-600:])


def run_eval_pinned():
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    import st_pin
    src2 = st_pin.ensure_shadow()
    os.environ['PROTRANS_SRC2'] = src2
    import paths, run_admitted_tune as T, score_v2 as S2
    recs = T.load_recs()

    mpath = os.path.join(H, 'picker_early_exit_windows.json')
    if not os.path.exists(mpath):
        run_protrans_maps(asym_w=float(os.environ.get('EE_ASYM_W', '2.00')))
    mp_tab = json.load(open(mpath))
    by_yt = mp_tab.get('by_yt') or {}

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

    # Render & hardcheck base (for exact fixed hardcheck counts and abstained pairs) + early_exit
    import multiprocessing as mp
    def _run_arm(arm, map_p):
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
            if map_p is not None and key not in by_yt:
                # Copy from base_full once base_full has run
                continue
            todo.append((arm, map_p, i, r))
        if todo:
            with mp.get_context('spawn').Pool(int(os.environ.get('PINW', 3)), maxtasksperchild=4) as pool:
                for row in pool.imap_unordered(_pinned_ee_worker, todo):
                    with open(ck, 'a') as fh:
                        fh.write(json.dumps(row, default=str) + '\n')
                    print(arm, row['id'], row.get('fam'), row.get('win'), 'v1=', row.get('v1'), 'v2=', row.get('v2'),
                          'hc=', (row.get('hardcheck') or {}).get('hard_fail'), row.get('error', '')[-120:], flush=True)
                    if not row.get('error'):
                        have[row['id']] = row
        return have, ck

    have_base, _ = _run_arm('base_hc', None)
    have_ee, ck_ee = _run_arm('early_exit', mpath)

    # Fill abstained pairs in early_exit from base_hc
    for r in recs:
        if r['id'] not in have_ee and r['id'] in have_base:
            b_copy = dict(have_base[r['id']], arm='early_exit', abstained_to_base=True, injected_cs=False)
            with open(ck_ee, 'a') as fh:
                fh.write(json.dumps(b_copy, default=str) + '\n')
            have_ee[r['id']] = b_copy

    rows_base = [have_base[r['id']] for r in recs if r['id'] in have_base]
    rows_ee = [have_ee[r['id']] for r in recs if r['id'] in have_ee]

    def _ci_subset(rows_sub, metric):
        d = [x[metric] - have_base[x['id']][metric] for x in rows_sub]
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

    pro_dec = json.load(open(os.path.join(H, 'protrans_decisions.json')))

    def _summarize(rows_list):
        tr = [x for x in rows_list if x['split'] == 'train']
        te = [x for x in rows_list if x['split'] == 'test']
        hc_fails = [x for x in rows_list if (x.get('hardcheck') or {}).get('hard_fail')]
        ex_entry_err, ex_gone_err, pe, px, ps = [], [], [], [], []
        play_pro, play_arm = [], []
        by_mix_play = collections.defaultdict(lambda: dict(pro=[], arm=[]))
        for x in rows_list:
            pl = x['placement']; pr, ou = pl['pro'], pl['ours']
            bpm = float(x.get('bpm_a') or 174.0)
            pd = pro_dec.get(x['id']) or {}
            pro_eb = pd.get('out_bar_at_entry') or (pr.get('entry') or {}).get('a')
            pro_gb = pd.get('out_bar_at_gone') or (pr.get('gone') or {}).get('a')
            ou_eb = (ou.get('entry') or {}).get('a')
            ou_gb = (ou.get('gone') or {}).get('a')
            win_s = float(x['win'][1] - x['win'][4]) if x.get('win') else ou_eb
            if pro_eb is not None and ou_eb is not None:
                ex_entry_err.append(abs(float(ou_eb) - float(pro_eb)))
            if pro_gb is not None and ou_gb is not None:
                ex_gone_err.append(abs(float(ou_gb) - float(pro_gb)))
            if pl.get('parts'):
                pe.append(pl['parts']['entry']); px.append(pl['parts']['gone']); ps.append(pl['parts']['swap'])
            if pro_eb is not None:
                pt_pro = float(pro_eb) * 240.0 / bpm
                pt_arm = float(win_s) * 240.0 / bpm
                play_pro.append(pt_pro)
                play_arm.append(pt_arm)
                mix = x['id'].rsplit('__', 1)[0]
                by_mix_play[mix]['pro'].append(pt_pro)
                by_mix_play[mix]['arm'].append(pt_arm)
        mix_avgs = {
            m: dict(
                n=len(v['pro']),
                pro_mean_sec=round(float(np.mean(v['pro'])), 1),
                arm_mean_sec=round(float(np.mean(v['arm'])), 1),
                diff_sec=round(float(np.mean(v['arm']) - np.mean(v['pro'])), 1),
            )
            for m, v in sorted(by_mix_play.items())
        }
        return dict(
            n=len(rows_list), n_train=len(tr), n_test=len(te),
            v1_train=round(float(np.mean([x['v1'] for x in tr])), 2),
            v1_test=round(float(np.mean([x['v1'] for x in te])), 2),
            v1_all=round(float(np.mean([x['v1'] for x in rows_list])), 2),
            v2_train=round(float(np.mean([x['v2'] for x in tr])), 2),
            v2_test=round(float(np.mean([x['v2'] for x in te])), 2),
            v2_all=round(float(np.mean([x['v2'] for x in rows_list])), 2),
            hard_fails=len(hc_fails),
            beat_clash=sum(1 for x in hc_fails if x['hardcheck'].get('beat_clash')),
            bass_hole=sum(1 for x in hc_fails if x['hardcheck'].get('bass_hole')),
            pumping=sum(1 for x in hc_fails if x['hardcheck'].get('pumping')),
            hard_fail_ids=[dict(id=x['id'], split=x['split'], win=x['win'], hc={k: x['hardcheck'].get(k) for k in ('beat_clash','bass_hole','pumping','pump_db','lows_dip_db','residual_lag_ms')}) for x in hc_fails],
            exit_entry_bar_mae=round(float(np.mean(ex_entry_err)), 2) if ex_entry_err else None,
            exit_gone_bar_mae=round(float(np.mean(ex_gone_err)), 2) if ex_gone_err else None,
            place_parts=dict(entry=round(float(np.mean(pe)), 1), gone=round(float(np.mean(px)), 1), swap=round(float(np.mean(ps)), 1)),
            play_time_pro_mean_sec=round(float(np.mean(play_pro)), 1),
            play_time_arm_mean_sec=round(float(np.mean(play_arm)), 1),
            play_time_diff_sec=round(float(np.mean(play_arm) - np.mean(play_pro)), 1),
            play_time_per_mix_mean_sec=round(float(np.mean([v['arm_mean_sec'] for v in mix_avgs.values()])), 1),
            play_time_pro_per_mix_mean_sec=round(float(np.mean([v['pro_mean_sec'] for v in mix_avgs.values()])), 1),
            by_mix_play_time=mix_avgs,
            fams=dict(collections.Counter(x['fam'] for x in rows_list)),
            n_early_exit_applied=sum(1 for x in rows_list if len(x.get('win') or []) >= 5 and x['win'][4] >= 36 and not x.get('abstained_to_base')),
        )

    out = dict(
        base=_summarize(rows_base),
        early_exit=dict(
            **_summarize(rows_ee),
            delta_v1_all=_ci_subset(rows_ee, 'v1'),
            delta_v2_all=_ci_subset(rows_ee, 'v2'),
            delta_v1_train=_ci_subset([x for x in rows_ee if x['split'] == 'train'], 'v1'),
            delta_v2_train=_ci_subset([x for x in rows_ee if x['split'] == 'train'], 'v2'),
            delta_v1_test=_ci_subset([x for x in rows_ee if x['split'] == 'test'], 'v1'),
            delta_v2_test=_ci_subset([x for x in rows_ee if x['split'] == 'test'], 'v2'),
        ),
    )
    outp = os.path.join(H, 'picker_1125_early_exit_pinned.json')
    json.dump(out, open(outp, 'w'), indent=2)
    print('EARLY_EXIT_PINNED SUMMARY:', json.dumps(out, indent=2), flush=True)

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'cv'
    aw = float(os.environ.get('EE_ASYM_W', '2.00'))
    if cmd == 'cv':
        run_cv(asym_w=aw)
    elif cmd == 'maps':
        run_protrans_maps(asym_w=aw)
    elif cmd == 'eval_pinned':
        run_eval_pinned()
    else:
        raise SystemExit(f'unknown cmd: {cmd}')
