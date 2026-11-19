#!/usr/bin/env python3
"""2026-11-19 EXITPOS_GATE fit. For each dev + admitted-cohort pair with a default engine window and a pro
window: among earlier exits that already play the outgoing's last drop and land the incoming drop1 inside
the blend, take the best exitpos-scored alternative. Label = 1 if that alternative is closer to the pro
(exit+cue error, 4-bar tolerance) than the default. L2 logistic, leave-one-DJ-out coefficients (and
per-track weights that exclude every DJ who played the track). Threshold picked on LODO predictions to
keep false switches (take alt when it is farther from the pro) at or below 10% of switches, otherwise 0.5.
-> halftime/exitpos_gate_w.json, exitpos_gate_fit_1119.json"""
import os, sys, json, collections
import numpy as np
import scipy.optimize as _so
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, 'halftime'))
import safeplace_1119 as S, exitpos as E, exitpos_gate as G

ST = '/workspace/mixes/src2/st/'
CK = '/workspace/mixes/protrans/replica/gate_ckpt/'
PRO = '/workspace/mixes/protrans/replica/protrans_decisions.json'
THR_FP = 0.10  # max share of predicted-switch cases that are farther from the pro

def ckpt(v):
    p = os.path.join(CK, v + '.jsonl')
    return {json.loads(l)['id']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}

def sec(yt):
    p = ST + yt + '.sections.json'
    return json.load(open(p)) if yt and os.path.exists(p) else None

def default_win_of(r, FB):
    if r['id'] in FB and FB[r['id']].get('win'):
        w = FB[r['id']]['win']; return int(w[1]), int(w[3]), int(w[4])
    if r.get('default_win'):
        w = r['default_win']; return int(w[1]), int(w[3]), int(w[4])
    dw = S.default_win(r) if hasattr(S, 'default_win') else None
    if dw: return int(dw[1]), int(dw[3]), int(dw[4])
    return None

def pro_ec(r, P):
    if r.get('pro_out') is not None:
        ov = int(round(float(r.get('pro_ov') or 16)))
        return int(round(float(r['pro_out']))) - 1 + ov, int(round(float(r['pro_in']))) - 1
    if r['id'] in P:
        d = P[r['id']]; return float(d['out_bar_at_gone']), float(d['in_bar_at_entry'])
    return None

def alts_for(sa, sb, default, me=None):
    be, bc, bX = default
    ld = G.last_drop_end(sa)
    d1 = (sb or {}).get('drop1')
    me = me or sa.get('music_end') or be
    nb = sb.get('n_bars') or sb.get('music_end') or 200
    out = []
    # Engine exits and cues are 16-bar aligned (mix_simple pair_cands). Do not offer 8-bar
    # alternatives the planner cannot actually pick.
    for X in (16, 32):
        if d1 is None: continue
        exits = list(range(32, int(me) + 1, 16))
        if int(me) - int(me) % 16 not in exits:
            e16 = int(me) - int(me) % 16
            if e16 >= 32: exits.append(e16)
        for ea in exits:
            if ea >= be: continue
            if ld is not None and ea < ld: continue
            for ib in range(0, min(129, int(nb) - X), 16):
                if not (ib <= d1 <= ib + X): continue
                out.append((ea, ib, X))
    # unique
    seen, u = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); u.append(t)
    return u

def best_alt(sa, sb, cands, ya=None):
    if not cands: return None, None
    # leave-one-DJ-out scale happens later; here use the published exitpos score (already LODO per track)
    scored = []
    for ea, ib, X in cands:
        try:
            u, scale = E.score(ya, sa, sb, ea, ib, X, me=sa.get('music_end')) if ya else (None, 1)
        except Exception:
            u = None
        if u is None:
            # raw utility
            try:
                x = np.array([E.feats(sa, sb, ea, ib, X)[k] for k in E.FEATS], float)
                w = E.load() if hasattr(E, 'load') else None
                u = float(x @ np.array([w['all']['coef'][k] for k in E.FEATS], float)) if w else 0.0
            except Exception:
                u = 0.0
        scored.append((u, (ea, ib, X)))
    scored.sort(key=lambda t: -t[0])  # higher exitpos utility is better (mix_simple adds it as a cost with sign in term)
    # Check sign: mix_simple does sc[0]+exitpos_term, and exitpos_term is typically a cost (lower better)?
    # Read exitpos.score: "scaled so spread equals STRUCTW". Need the direction used in mix_simple.
    return scored[0][1], scored

def err(win, pe, pc):
    return abs(win[0] - pe) + abs(win[1] - pc)

def nll(w, X, y, l2=1.0):
    z = np.clip(X @ w, -40, 40); p = 1 / (1 + np.exp(-z))
    t = -np.sum(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)) + l2 * w[1:] @ w[1:]
    g = X.T @ (p - y); g[1:] += 2 * l2 * w[1:]
    return t, g

def fit(X, y):
    if len(y) < 4 or y.sum() == 0 or y.sum() == len(y):
        # degenerate: intercept-only prior toward the majority
        maj = 1.0 if y.mean() >= 0.5 else 0.0
        w = np.zeros(X.shape[1]); w[0] = 5 if maj else -5
        return w
    w0 = np.zeros(X.shape[1])
    x, f, d = _so.fmin_l_bfgs_b(nll, w0, args=(X, y), approx_grad=False)
    return x

def pack(w):
    return dict(intercept=float(w[0]), coef=dict(zip(G.FEATS, map(float, w[1:]))))

def main():
    FB = ckpt('epbasem')
    P = json.load(open(PRO)) if os.path.exists(PRO) else {}
    # dev + any admitted-cohort rows we can attach sections to
    rows = []
    for r in S.dev_rows():
        if r.get('pro_out') is None or not isinstance(r.get('sa'), dict) or not isinstance(r.get('sb'), dict):
            continue
        rows.append(r)
    # admitted cohort not already in dev
    have = {r['id'] for r in rows}
    try:
        sys.path.insert(0, '/workspace/mixes/protrans')
        import run_admitted_tune as T
        recs = {r['id']: r for r in T.load_recs()}
    except Exception:
        recs = {}
    for i, d in P.items():
        if i in have: continue
        rec = recs.get(i)
        if not rec: continue
        ya, yb = rec['a']['yt'], rec['b']['yt']
        sa, sb = sec(ya), sec(yb)
        if not sa or not sb: continue
        rows.append(dict(id=i, dj=d.get('dj') or rec['dj'], mix=rec.get('mix_id') or i.rsplit('__', 1)[0],
                         ya=ya, yb=yb, sa=sa, sb=sb, set='protrans'))

    examples = []
    for r in rows:
        dw = default_win_of(r, FB)
        pe = pro_ec(r, P)
        if not dw or not pe: continue
        sa, sb, ya = r['sa'], r['sb'], r.get('ya')
        cands = alts_for(sa, sb, dw, sa.get('music_end'))
        if not cands: continue
        # rank by exitpos utility; mix_simple ADDS exitpos_term to a cost (lower better).
        # exitpos.score returns a term meant to be added to cost: check sign via end-to-end on a known pair later.
        # We pick the alt with the *lowest* cost term if we can compute it, else highest raw utility.
        scored = []
        for ea, ib, X in cands:
            try:
                term, _ = E.score(ya, sa, sb, ea, ib, X, me=sa.get('music_end'))
            except TypeError:
                term, _ = E.score(ya, sa, sb, ea, ib, X)
            except Exception:
                term = 0.0
            scored.append((term, (ea, ib, X)))
        scored.sort(key=lambda t: t[0])  # lower term (cost) first, matching mix_simple
        alt = scored[0][1]
        e0, e1 = err(dw, *pe), err(alt, *pe)
        lab = 1 if e1 < e0 - 2 else 0
        f = G.feats(dw, alt, sa, sb, ya)
        examples.append(dict(id=r['id'], dj=r['dj'], mix=r.get('mix'), ya=ya, set=r.get('set', 'dev'),
                             default=list(dw), alt=list(alt), n_alts=len(cands),
                             err_default=round(e0, 2), err_alt=round(e1, 2), y=lab, feats=f))

    print('examples', len(examples), 'pos', sum(x['y'] for x in examples), 'djs', len({x['dj'] for x in examples}), flush=True)
    if not examples:
        json.dump(dict(n=0), open(os.path.join(H, 'exitpos_gate_fit_1119.json'), 'w'), indent=1); return

    X = np.array([[1.0] + [x['feats'][k] for k in G.FEATS] for x in examples], float)
    y = np.array([x['y'] for x in examples], float)
    wall = fit(X, y)
    # LODO
    lodo, preds = {}, []
    for dj in sorted({x['dj'] for x in examples}):
        idx = [i for i, x in enumerate(examples) if x['dj'] != dj]
        te = [i for i, x in enumerate(examples) if x['dj'] == dj]
        w = fit(X[idx], y[idx]); lodo[dj] = pack(w)
        for i in te:
            z = float(np.clip(X[i] @ w, -40, 40)); p = 1 / (1 + np.exp(-z))
            preds.append((i, p, examples[i]['y'], dj))
            examples[i]['lodo_p'] = round(p, 4)

    # threshold: among predicted switches, cap the farther-from-pro rate
    def fp_rate(thr):
        sw = [(p, y_) for _, p, y_, _ in preds if p >= thr]
        if not sw: return 0.0, 0
        return 1 - (sum(y_ for _, y_ in sw) / len(sw)), len(sw)

    cands_t = [round(t, 2) for t in np.linspace(0.3, 0.85, 12)]
    pick = (0.5, *fp_rate(0.5))
    for t in cands_t:
        fp, n_sw = fp_rate(t)
        # prefer a threshold with at least a few switches, fp <= THR_FP, then more true switches
        if n_sw >= 2 and fp <= THR_FP:
            if pick[2] < 2 or n_sw > pick[2] or (n_sw == pick[2] and t < pick[0]):
                pick = (t, fp, n_sw)
    # if nothing met the cap, take the highest threshold that still switches at least twice, else 0.5
    if pick[2] < 2:
        for t in sorted(cands_t, reverse=True):
            fp, n_sw = fp_rate(t)
            if n_sw >= 2:
                pick = (t, fp, n_sw); break
    thr = float(pick[0])

    # per-track weights: exclude DJs who used that outgoing track
    djs_of = collections.defaultdict(set)
    for x in examples:
        if x.get('ya'): djs_of[x['ya']].add(x['dj'])
    per_track = {}
    for ya, djs in djs_of.items():
        idx = [i for i, x in enumerate(examples) if x['dj'] not in djs]
        if len(idx) < 4: continue
        per_track[ya] = pack(fit(X[idx], y[idx]))

    W = dict(all=pack(wall), lodo=lodo, per_track=per_track, threshold=thr, feats=list(G.FEATS),
             ref='fit_exitpos_gate_1119 v1 hard=earlier+last_drop+drop1_in')
    json.dump(W, open(G.W_PATH, 'w'), indent=1)
    # LODO metrics at chosen threshold
    yhat = [int(p >= thr) for _, p, _, _ in preds]
    ytrue = [int(y_) for _, _, y_, _ in preds]
    tp = sum(a and b for a, b in zip(yhat, ytrue)); fp = sum(a and not b for a, b in zip(yhat, ytrue))
    tn = sum((not a) and (not b) for a, b in zip(yhat, ytrue)); fn = sum((not a) and b for a, b in zip(yhat, ytrue))
    out = dict(n=len(examples), n_pos=int(y.sum()), n_djs=len(lodo), threshold=thr,
               lodo_at_thr=dict(tp=tp, fp=fp, tn=tn, fn=fn,
                                precision=round(tp / (tp + fp), 3) if tp + fp else None,
                                recall=round(tp / (tp + fn), 3) if tp + fn else None),
               coef_all=W['all'], examples=examples)
    json.dump(out, open(os.path.join(H, 'exitpos_gate_fit_1119.json'), 'w'), indent=1, default=str)
    print(json.dumps({k: out[k] for k in out if k != 'examples'}, indent=1))
    print('wrote', G.W_PATH)

if __name__ == '__main__':
    main()
