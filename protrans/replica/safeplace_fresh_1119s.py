#!/usr/bin/env python3
"""2026-11-19 day: score the FROZEN safeplace-b planner once on the isolated fresh mix (fresh_mixes.json for_night
'2026-11-19-day-safeplace', data in fresh_work_s). Models trained on ALL dev (no fresh, no holdout): risk LightGBM with PUMPF=1 and
EXTRA_RV=sp1119a1,sp1119a2; exit/cue fit rankers picker_1119b CFGS[0] style-free; SECPEN 0.1, LAMBDA 0.1 (as in b).
usage: plan (needs gate_ckpt/fdef1119s rendered) | eval"""
import json, os, sys, numpy as np
os.environ.setdefault('PUMPF', '1'); os.environ.setdefault('SECPEN', '0.1'); os.environ.setdefault('EXTRA_RV', 'sp1119a1,sp1119a2')
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import safeplace_1119 as S, picker_1119 as P, picker_1119b as B, final_eval as FE
FW = os.path.join(H, os.environ.get('FRESH_DIR', 'fresh_work_s')); WK = S.WK; LAM = 0.1; FT = os.environ.get('FTAG', 'F'); DEFV = os.environ.get('FDEF', 'fdef1119s')
MIX = [m for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes'] if m.get('for_night') == os.environ.get('FRESH_NIGHT', '2026-11-19-day-safeplace')][-1]
def fresh_rows():
    D = {k: a for k, a in S.load(DEFV).items()}; G = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', DEFV + '.jsonl'))}
    rows = []
    for l in open(os.path.join(FW, 'accepted.jsonl')):
        a = json.loads(l)
        if a['mix_id'] != MIX['mix_id']: continue
        f = json.load(open(os.path.join(FW, 'features', a['id'] + '.json')))
        if f.get('error'): continue
        rows.append(dict(id=a['id'], src='corpus_v2', dj=a['dj'], mix=a['mix_id'], idx=int(a['id'].rsplit('__', 1)[1]), sa=f['track_a']['sections'], sb=f['track_b']['sections'],
                         bpm=(None, None), pro_out=f['cue']['outgoing_bar'], pro_in=f['cue']['incoming_bar'], pro_ov=f.get('overlap_bars'), feat_cands=f.get('candidates') or [],
                         set='fresh', hist=None, ya=f['track_a']['yt'], yb=f['track_b']['yt']))
    good = {k: g for k, g in G.items() if not g.get('error')}
    rows = [r for r in rows if r['id'] in good and r['id'] in D]
    return B.build(rows, good), D
def plan():
    rows, D = fresh_rows(); dev = S.dev_rows()
    Xr, yr, *_ = S.risk_data(dev, os.environ['EXTRA_RV'].split(',')); m = S.fit_risk(Xr, yr)
    mE = B.fit(dev, 'E', False, B.CFGS[0]); mC = B.fit(dev, 'C', False, B.CFGS[0]); out, W1, W2 = [], {}, {}
    for r in rows:
        C = S.cands(r); dw = S.default_win(r); C = [c for c in C if c['win'] != dw] + [dict(win=dw, phrase_ok=True, default=True)]
        if os.environ.get('GAPX', '0') == '1': C = S.gap_filter(r, C)
        pr = m.predict_proba(np.array([S.wfeat(r, c['win']) for c in C], float))[:, 1]
        se = mE.predict(np.array([B.fe_exit(r, dict(v=c['win'][1] - c['win'][4] + 1, tags={'default'} if c.get('default') else {'grid'}), False) for c in C], float))
        sc = mC.predict(np.array([B.fe_cue(r, dict(v=c['win'][3] + 1, tags={'default'} if c.get('default') else {'grid'}), False) for c in C], float))
        pct = lambda s: (np.argsort(np.argsort(s)) + 0.5) / len(s); fit = (pct(se) + pct(sc)) / 2; bnd = P.bnd_a(r['sa'])
        offsec = np.array([min((abs((c['win'][1] - c['win'][4] + 1) - v) for v in bnd), default=99) > 4 for c in C])
        pay = np.array([S.payoff_miss(r, c['win']) for c in C]); paypen = float(os.environ.get('PAYPEN', 0))  # PAYPEN (variant d): placement-quality term
        score = pr + 0.15 * np.array([not c['phrase_ok'] for c in C]) + LAM * (1 - fit) + 0.1 * offsec + paypen * pay; o = np.argsort(score); di = len(C) - 1
        top = [int(j) for j in o if j != di][:2]
        rec = dict(id=r['id'], default_win=dw, default_risk=round(float(pr[di]), 3), top=[dict(win=C[j]['win'], risk=round(float(pr[j]), 3), score=round(float(score[j]), 3)) for j in top],
                   keep_default=bool(not top or score[di] <= min(score[j] for j in top)), pro_out=r['pro_out'], pro_in=r['pro_in'], dex=r['dex'], dcue=r['dcue'],
                   off_sec=[bool(offsec[j]) for j in top], default_offsec=bool(offsec[di]), is_mid=[bool(S.NA(r['sa']) - (C[j]['win'][1] - C[j]['win'][4] + 1) >= 32) for j in top], payoff_miss=[round(float(pay[j]), 2) for j in top], default_payoff_miss=round(float(pay[di]), 2))
        if not rec['keep_default']:
            W1[f"{r['ya']}|{r['yb']}"] = rec['top'][0]['win']
            if len(rec['top']) > 1: W2[f"{r['ya']}|{r['yb']}"] = rec['top'][1]['win']
        out.append(rec)
    json.dump(out, open(os.path.join(WK, f'plan_{FT}.json'), 'w'), indent=1, default=str)
    json.dump(W1, open(os.path.join(WK, f'win_{FT}_r1.json'), 'w')); json.dump(W2, open(os.path.join(WK, f'win_{FT}_r2.json'), 'w'))
    json.dump([x['id'] for x in out if not x['keep_default']], open(os.path.join(WK, f'ids_{FT}.json'), 'w')); print('fresh pairs', len(out), 'changed', len(W1))
def ev():
    plan_ = json.load(open(os.path.join(WK, f'plan_{FT}.json'))); D = S.load(DEFV); R1 = S.load(f'sp1119{FT}1'); R2 = S.load(f'sp1119{FT}2')
    G1 = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', f'sp1119{FT}1.jsonl'))} if R1 else {}
    fl = lambda a: FE.flags(a); bad = lambda a: bool(fl(a)['HC_A'] or fl(a)['HC_B']); rows = []
    for p in plan_:
        k = p['id']; d = D[k]; arm_raw = arm_fin = d; how = 'kept_default'
        if not p['keep_default']:
            if k in R1:
                arm_raw = R1[k]
                if not bad(R1[k]): arm_fin, how = R1[k], 'r1_pass'
                elif k in R2 and not bad(R2[k]): arm_fin, how = R2[k], 'r2_pass'
                else: how = 'both_fail_default'
            else: how = 'no_render_default'
        rows.append(dict(id=k, how=how, default=bad(d), raw=bad(arm_raw), final=bad(arm_fin), fired_default=[x for x, v in fl(d).items() if v and x not in ('HC_A', 'HC_B', 'HC_C')],
                         fired_raw=[x for x, v in fl(arm_raw).items() if v and x not in ('HC_A', 'HC_B', 'HC_C')], applied=(G1.get(k) or {}).get('fam')))
    n = len(rows); res = dict(mix=MIX, n_pairs=n, default_fail=sum(r['default'] for r in rows), raw_fail=sum(r['raw'] for r in rows), final_fail=sum(r['final'] for r in rows),
                              outcomes={h: sum(r['how'] == h for r in rows) for h in {r['how'] for r in rows}}, off_phrase_final=0,
                              off_section_default=sum(p['default_offsec'] for p in plan_), off_section_pick=sum(p['off_sec'][0] for p in plan_ if not p['keep_default']), rows=rows)
    json.dump(res, open(os.path.join(H, f'safeplace_fresh_1119s{"" if FT == "F" else "_" + FT}.json'), 'w'), indent=1, default=str); print(json.dumps({k: v for k, v in res.items() if k != 'rows'}))
if __name__ == '__main__': {'plan': plan, 'eval': ev}[sys.argv[1]]()
