#!/usr/bin/env python3
"""2026-11-19: PLACE=safe d / e (d + RISKVETO) on the 33-pair protrans cohort, to read the held-out score (34.07 floor) of what the
planner would play. Risk + fit models frozen, trained on ALL dev (no cohort labels). Writes safeplace_work/win_<tag>_cohort.json for
recreate's PICKER_WIN (rank-1 pick; kept-default pairs stay on the engine default) and plan_<tag>_cohort.json.
usage: safeplace_cohort_1119.py <tag>   (env as in run_d.sh / run_e.sh)"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import safeplace_1119 as S, run_admitted_tune as T
tag = sys.argv[1]; B, P = S.B, S.P
REC = {r['id']: r for r in T.load_recs()}
rows = [r for r in B.build(P.rows_all(), P.load_rendered_defaults()) if r['src'] == 'protrans']
for r in rows: r['ya'], r['yb'] = REC[r['id']]['a']['yt'], REC[r['id']]['b']['yt']
dev = S.dev_rows(); Xr, yr, gr, djr, keys = S.risk_data(dev, [v for v in os.environ.get('EXTRA_RV', '').split(',') if v]); m = S.fit_risk(Xr, yr)
tau = float(np.percentile(m.predict_proba(Xr)[:, 1], 80))
mE = B.fit(dev, 'E', False, B.CFGS[0]); mC = B.fit(dev, 'C', False, B.CFGS[0]); out, W = [], {}
for r in rows:
    if not S.st(r['ya']) or not S.st(r['yb']): out.append(dict(id=r['id'], skipped='no st')); continue
    C = S.cands(r); dw = S.default_win(r); C = [c for c in C if c['win'] != dw] + [dict(win=dw, phrase_ok=True, default=True)]
    if os.environ.get('GAPX', '0') == '1': C = S.gap_filter(r, C)
    pr = m.predict_proba(np.array([S.wfeat(r, c['win']) for c in C], float))[:, 1]
    se = mE.predict(np.array([B.fe_exit(r, dict(v=c['win'][1] - c['win'][4] + 1, tags={'default'} if c.get('default') else {'grid'}), False) for c in C], float))
    sc = mC.predict(np.array([B.fe_cue(r, dict(v=c['win'][3] + 1, tags={'default'} if c.get('default') else {'grid'}), False) for c in C], float))
    pct = lambda s: (np.argsort(np.argsort(s)) + 0.5) / len(s); fit = (pct(se) + pct(sc)) / 2; bnd = P.bnd_a(r['sa'])
    offsec = np.array([min((abs((c['win'][1] - c['win'][4] + 1) - v) for v in bnd), default=99) > 4 for c in C])
    pay = np.array([S.payoff_miss(r, c['win']) for c in C]) * float(os.environ.get('PAYPEN', 0))
    score = pr + 0.15 * np.array([not c['phrase_ok'] for c in C]) + 0.1 * (1 - fit) + float(os.environ.get('SECPEN', 0)) * offsec + pay
    di = len(C) - 1; veto_def = False
    if os.environ.get('RISKVETO', '0') == '1':
        vet = pr >= tau; score = score + 10.0 * (vet & (np.arange(len(C)) != di)); veto_def = bool(vet[di]) and bool((~vet[:di]).any())
    o = np.argsort(score); top = [int(j) for j in o if j != di][:2]
    keep = bool(not top or (score[di] <= min(score[j] for j in top) and not veto_def))
    rec = dict(id=r['id'], split=REC[r['id']]['split'], default_win=dw, default_risk=round(float(pr[di]), 3), keep_default=keep, veto_default=veto_def,
               top=[dict(win=C[j]['win'], risk=round(float(pr[j]), 3), score=round(float(score[j]), 3)) for j in top])
    if not keep: W[f"{r['ya']}|{r['yb']}"] = C[top[0]]['win']
    out.append(rec)
json.dump(out, open(os.path.join(S.WK, f'plan_{tag}_cohort.json'), 'w'), indent=1, default=str)
json.dump(W, open(os.path.join(S.WK, f'win_{tag}_cohort.json'), 'w'))
print('cohort pairs', len(out), 'changed', len(W), 'tau', round(tau, 3), 'veto_default', sum(x.get('veto_default', False) for x in out))
