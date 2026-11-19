#!/usr/bin/env python3
"""Nightly 2026-11-19: learned section picker (LightGBM LambdaMART) over a full candidate set, judged on pro decisions only.
Candidates per pair (rule generators only, the model decides): default (rendered engine window when available, else the
outro-intro proxy), outro-intro, DROPCAND drop-exit / drop-cue, replica-style breakdown exits, and a section/phrase grid of
exits (8-bar steps) x cues (phrase grid 0..80 + section anchors) x blend length X in {8,16,32}.
Exit = e - X + 1 (incoming entry bar on the outgoing grid), cue = ib + 1 (as in gate_ckpt rows).
Labels = acceptable sets (pro bar + any section boundary within 8 bars, policy.acc_err) -> graded relevance.
Online DJ-style features from earlier transitions of the same mix (index < t only). A style-free model is trained too.
Data: corpus_v2 accepted snapshot (dev = not holdout DJs; holdout = Liquicity + Hospital Records, opened only for the keep
decision) + 33 protrans pairs (eval-only, never trained on).
usage: picker_1119.py cv | protrans | holdout | fresh <mix_id>"""
import json, os, sys, collections, math, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); W = os.path.join(H, 'nightly_1119_work')
sys.path.insert(0, H); sys.path.insert(0, P)
import lightgbm as lgb
HOLD = json.load(open(os.path.join(H, 'holdout.json')))['final_holdout_djs']
SPENT_FRESH = {m['mix_id'] for m in json.load(open(os.path.join(H, 'fresh_mixes.json')))['mixes'] if m.get('for_night') == '2026-11-19'}

def ph(x, q=8): return int(round(x / q) * q)
def bnd_a(s):
    return sorted({int(x) for x in ([s.get('drop1'), s.get('breakdown'), s.get('drop2'), s.get('outro_start'), s.get('music_end')] + [y for d in (s.get('drops') or []) for y in d]) if x is not None})
def bnd_b(s):
    return sorted({int(x) for x in ([0, s.get('drop1'), s.get('breakdown'), s.get('drop2'), s.get('outro_start')] + [y for d in (s.get('drops') or []) for y in d]) if x is not None})
def acc_err(ours, pro, bnd, tol=8):
    S = [pro] + [x for x in bnd if abs(x - pro) <= tol]; return min(abs(ours - s) for s in S)
SEC = dict(intro=0, build=1, drop=2, breakdown=3, outro=4)
def sec_at(s, bar):
    for p in s.get('phases') or []:
        if p['start'] <= bar < p['end']: return SEC.get(p['name'], 5)
    if bar < (s.get('drop1') or 0): return 0
    if bar >= (s.get('outro_start') or 1e9): return 4
    return 2 if any(d[0] <= bar < d[1] for d in (s.get('drops') or [])) else 3
def ndist(x, L):
    L = [v for v in L if v is not None]
    if not L: return 99.
    return min((x - v for v in L), key=abs)

def load_rendered_defaults():
    import analyze as A
    out = {}
    for v in ('default', 'kush_default', 'fresh_default', 'ndef1119', 'fdef1119'):
        p = os.path.join(H, 'gate_ckpt', v + '.jsonl')
        if os.path.exists(p):
            for k, r in A.load(v).items():
                if not r.get('error'): out.setdefault(k, r)
    return out

def rows_all():
    """all transitions with pro decisions: corpus_v2 snapshot + protrans 33"""
    rows = []
    for l in open(os.path.join(W, 'accepted_snapshot.jsonl')):
        a = json.loads(l); f = json.load(open(os.path.join(P, 'corpus_v2', 'features', a['id'] + '.json')))
        if f.get('error'): continue
        sw = (f.get('pro_decision') or {}).get('bass_swap_bar')
        rows.append(dict(id=a['id'], src='corpus_v2', dj=a['dj'], mix=a['mix_id'], idx=int(a['id'].rsplit('__', 1)[1]),
                         sa=f['track_a']['sections'], sb=f['track_b']['sections'], bpm=(f['track_a'].get('bpm'), f['track_b'].get('bpm')),
                         pro_out=f['cue']['outgoing_bar'], pro_in=f['cue']['incoming_bar'], pro_ov=f.get('overlap_bars'),
                         feat_cands=f.get('candidates') or []))
    for k, d in json.load(open(os.path.join(H, 'protrans_decisions.json'))).items():
        if d.get('out_bar_at_entry') is None: continue
        rows.append(dict(id=k, src='protrans', dj=d['dj'], mix=k.rsplit('__', 1)[0], idx=int(k.rsplit('__', 1)[1]), sa=d['sec_a'], sb=d['sec_b'],
                         bpm=(None, None), pro_out=d['out_bar_at_entry'], pro_in=d['in_bar_at_entry'], pro_ov=d.get('overlap_bars'), feat_cands=[]))
    for r in rows:
        r['set'] = 'protrans' if r['src'] == 'protrans' else ('fresh' if r['mix'] in SPENT_FRESH else ('holdout' if r['dj'] in HOLD else 'dev'))
    # online history: earlier transitions of the same mix only (strict index < t)
    by = collections.defaultdict(list)
    for r in rows: by[(r['src'], r['mix'])].append(r)
    for r in rows:
        past = [q for q in by[(r['src'], r['mix'])] if q['idx'] < r['idx']]
        if past:
            left = [q['sa'].get('music_end', 0) - q['pro_out'] for q in past]; cr = [q['pro_in'] - (q['sb'].get('drop1') or 0) for q in past]
            r['hist'] = dict(n=len(past), left=float(np.mean(left)), mid=float(np.mean([x > 40 for x in left])), cue_rel=float(np.mean(cr)),
                             cue_in_drop=float(np.mean([c >= -2 for c in cr])), ov=float(np.mean([q['pro_ov'] or 0 for q in past])))
        else: r['hist'] = None
    return rows

def candidates(r, default_row):
    sa, sb = r['sa'], r['sb']; na = int(sa.get('music_end') or sa.get('n_bars')); nb = int(sb.get('music_end') or sb.get('n_bars'))
    d1b = int(sb.get('drop1') or 0); drops_a = [list(map(int, d)) for d in (sa.get('drops') or [])]
    C = {}
    def add(e, ib, X, tag):
        e, ib, X = int(e), int(ib), int(X)
        if e > na or e - X < 16 or ib < 0 or ib + X > nb - 16: return
        k = (e, ib, X); C.setdefault(k, set()).add(tag)
    cues_base = set(range(0, 81, 16)) | {ph(x) for x in (d1b - 16, d1b - 32, d1b, d1b - 8, sb.get('breakdown'), (sb.get('drop2') or 0)) if x is not None and x >= 0}
    for X in tuple(int(x) for x in os.environ.get('PX', '8,16,32').split(',')):
        cues = cues_base | {ph(max(0, d1b - X))}
        for e in range(ph(na) if ph(na) <= na else ph(na) - 8, 31 + X, -8):
            for ib in cues: add(e, ib, X, 'grid')
        es = (na // 8) * 8
        add(es, max(0, d1b - X), X, 'outro_intro')
        if drops_a:
            e1 = ph(drops_a[0][1]); add(e1, ph(max(0, d1b - X)), X, 'drop_exit'); add(e1, ph(d1b), X, 'drop_cue')
            for d in drops_a[1:]: add(ph(d[1]), ph(max(0, d1b - X)), X, 'dropN_exit')
        if sa.get('breakdown'): add(ph(sa['breakdown']) + 8, ph(max(0, d1b - X)), X, 'replica_bd')
    out = []
    dwin = None
    if default_row is not None:
        w = default_row['win']; dwin = (int(w[1]), int(w[3]), int(w[4]))
        dex, dcue = default_row['ours']['out_bar'], default_row['ours']['in_bar']
    else:
        oi = [c['win'] for c in r['feat_cands'] if c['type'] == 'outro_intro']
        if oi: w = oi[0]; dwin = (int(w[1]), int(w[3]), int(w[4]))
        else: dwin = ((na // 8) * 8, max(0, d1b - 16), 16)
        dex, dcue = dwin[0] - dwin[2] + 1, dwin[1] + 1
    C.setdefault(dwin, set()).add('default')
    for (e, ib, X), tags in C.items():
        if 'default' in tags: ex, cu = dex, dcue
        else: ex, cu = e - X + 1, ib + 1
        out.append(dict(e=e, ib=ib, X=X, tags=tags, exit=ex, cue=cu))
    return out

def featvec(r, c, style):
    sa, sb = r['sa'], r['sb']; na = float(sa.get('music_end') or sa.get('n_bars')); nb = float(sb.get('music_end') or sb.get('n_bars'))
    d1b = float(sb.get('drop1') or 0); drops_a = sa.get('drops') or []
    ex, cu = c['exit'], c['cue']; left = na - ex
    bb = sa.get('bass_by_section') or {}; bbb = sb.get('bass_by_section') or {}
    v = [ex, ex / na, left, c['X'], c['e'], na - c['e'], sec_at(sa, ex), sec_at(sa, c['e'] - 1),
         ndist(ex, [d[1] for d in drops_a]), ndist(ex, [drops_a[0][1]] if drops_a else []), ndist(ex, [sa.get('outro_start')]), ndist(ex, [sa.get('breakdown')]),
         ndist(c['e'], [d[1] for d in drops_a]), ndist(c['e'], [sa.get('outro_start'), sa.get('music_end')]),
         cu, cu / nb, cu - d1b, c['ib'] + c['X'] - d1b, sec_at(sb, cu), ndist(cu, [sb.get('breakdown'), sb.get('drop2')]),
         na, nb, len(drops_a), len(sb.get('drops') or []), sa.get('intro_len') or 0, sb.get('intro_len') or 0, na - (sa.get('outro_start') or na), d1b,
         (bb.get('outro') or {}).get('bass', np.nan), (bbb.get('intro') or {}).get('bass', np.nan), (bb.get('breakdown') or {}).get('bass', np.nan),
         int('default' in c['tags']), int('outro_intro' in c['tags']), int('drop_exit' in c['tags']), int('drop_cue' in c['tags']), int('replica_bd' in c['tags']), int('dropN_exit' in c['tags'])]
    if style:
        h = r['hist']
        if h: v += [h['n'], h['left'], h['mid'], h['cue_rel'], h['cue_in_drop'], h['ov'], left - h['left'], (cu - d1b) - h['cue_rel'], float(left > 40) - h['mid']]
        else: v += [0] + [np.nan] * 8
    return v

def relevance(r, c):
    ea = acc_err(c['exit'], r['pro_out'], bnd_a(r['sa'])); ca = acc_err(c['cue'], r['pro_in'], bnd_b(r['sb'])); m = (ea + ca) / 2
    return 4 if m <= 4 else 3 if m <= 8 else 2 if m <= 16 else 1 if m <= 32 else 0

def build(rows, D):
    for r in rows:
        r['cands'] = candidates(r, D.get(r['id'])); r['def_src'] = 'rendered' if r['id'] in D else 'proxy'
        r['rel'] = np.array([relevance(r, c) for c in r['cands']])
        r['dix'] = next(i for i, c in enumerate(r['cands']) if 'default' in c['tags'])
    return rows

def X_of(rs, style):
    k = 'Xs' if style else 'Xn'
    for r in rs:
        if k not in r: r[k] = np.array([featvec(r, c, style) for c in r['cands']], float)
    return np.vstack([r[k] for r in rs])

def fit(rs, style, cfg):
    X = X_of(rs, style); y = np.concatenate([r['rel'] for r in rs]); g = [len(r['cands']) for r in rs]
    m = lgb.LGBMRanker(objective='lambdarank', n_estimators=cfg['n'], num_leaves=cfg['leaves'], learning_rate=0.05, min_child_samples=cfg['mcs'],
                       subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=20261119, verbose=-1, n_jobs=int(os.environ.get('LGB_JOBS', 1)), lambdarank_truncation_level=20)
    m.fit(X, y, group=g); return m

def predict(m, rs, style):
    out = []
    for r in rs:
        s = m.predict(X_of([r], style)); out.append(s)
    return out

def pick(r, s, tau):
    j = int(np.argmax(s)); use = (s[j] - s[r['dix']]) > tau
    return (j if use else r['dix']), bool(use and j != r['dix'])

def errs(r, c):
    e, q = abs(c['exit'] - r['pro_out']), abs(c['cue'] - r['pro_in'])
    return dict(exit=e, cue=q, exit_cue=(e + q) / 2, exit_acc=acc_err(c['exit'], r['pro_out'], bnd_a(r['sa'])), cue_acc=acc_err(c['cue'], r['pro_in'], bnd_b(r['sb'])), X=c['X'])

CFGS = [dict(n=150, leaves=7, mcs=50), dict(n=300, leaves=15, mcs=100)]
TAUS = [-1e9, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 1e9]

def inner_select(tr, style):
    djs = sorted({r['dj'] for r in tr}); best = None
    for ci, cfg in enumerate(CFGS):
        S = {}
        for d in djs:
            a = [r for r in tr if r['dj'] != d]; b = [r for r in tr if r['dj'] == d]
            m = fit(a, style, cfg)
            for r, s in zip(b, predict(m, b, style)): S[r['id']] = s
        for t in TAUS:
            e = np.mean([errs(r, r['cands'][pick(r, S[r['id']], t)[0]])['exit_cue'] for r in tr])
            if best is None or e < best[0]: best = (e, ci, t)
    return best

def baselines(tr):
    """simple rule = DROPCAND drop-exit (X16) when legal else default; majority = generator tag with the lowest mean train error"""
    def tagpick(r, tag, X=16):
        js = [i for i, c in enumerate(r['cands']) if tag in c['tags'] and c['X'] == X] or [i for i, c in enumerate(r['cands']) if tag in c['tags']]
        return js[0] if js else r['dix']
    tags = ['default', 'outro_intro', 'drop_exit', 'drop_cue', 'replica_bd']
    best = min(tags, key=lambda t: np.mean([errs(r, r['cands'][tagpick(r, t)])['exit_cue'] for r in tr]))
    return (lambda r: tagpick(r, 'drop_exit')), (lambda r: tagpick(r, best)), best

def boot(ids_groups, a, b, n=4000, seed=20261119):
    d = collections.defaultdict(list)
    for g, x, y in zip(ids_groups, a, b): d[g].append(y - x)
    G = list(d); rng = np.random.default_rng(seed); allv = [x for g in G for x in d[g]]
    bs = [np.mean([x for j in rng.choice(len(G), len(G)) for x in d[G[j]]]) for _ in range(n)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(delta=round(float(np.mean(allv)), 2), ci=[round(float(lo), 2), round(float(hi), 2)], n=len(allv), groups=len(G),
                verdict='better' if hi < 0 else ('worse' if lo > 0 else 'no clear difference'))

def summarize(rs, picks, ref='default'):
    out = {}
    for name, P_ in picks.items():
        E = [errs(r, r['cands'][j]) for r, j in zip(rs, P_)]; s = dict(n=len(rs))
        for k in ('exit', 'cue', 'exit_cue', 'exit_acc', 'cue_acc'):
            s[k + '_mean'] = round(float(np.mean([e[k] for e in E])), 2); s[k + '_median'] = round(float(np.median([e[k] for e in E])), 2)
        for t in (4, 8, 16):
            s[f'exit_hit{t}'] = round(float(np.mean([e['exit'] <= t for e in E])), 3); s[f'cue_hit{t}'] = round(float(np.mean([e['cue'] <= t for e in E])), 3)
            s[f'exit_acc_hit{t}'] = round(float(np.mean([e['exit_acc'] <= t for e in E])), 3); s[f'cue_acc_hit{t}'] = round(float(np.mean([e['cue_acc'] <= t for e in E])), 3)
        ovm = {8: 6.0, 16: 10.0, 32: 18.0}  # median audible overlap of our renders per X (gate_ckpt), proxy only
        ob = [abs(ovm[e['X']] - r['pro_ov']) for e, r in zip(E, rs) if r['pro_ov'] is not None]
        s['blendlen_proxy_err_mean'] = round(float(np.mean(ob)), 2) if ob else None
        s['changed_vs_default'] = int(sum(j != r['dix'] for r, j in zip(rs, P_)))
        out[name] = s
    R = picks[ref]; g = [r['mix'] for r in rs]
    for name, P_ in picks.items():
        if name == ref: continue
        out[name]['delta_vs_default'] = {k: boot(g, [errs(r, r['cands'][j])[k] for r, j in zip(rs, R)], [errs(r, r['cands'][j])[k] for r, j in zip(rs, P_)])
                                         for k in ('exit', 'cue', 'exit_cue', 'exit_acc', 'cue_acc')}
        hd = boot(g, [float(errs(r, r['cands'][j])['exit'] <= 16) for r, j in zip(rs, R)], [float(errs(r, r['cands'][j])['exit'] <= 16) for r, j in zip(rs, P_)])
        hd['verdict'] = 'better' if hd['ci'][0] > 0 else ('worse' if hd['ci'][1] < 0 else 'no clear difference'); out[name]['delta_exit_hit16'] = hd
    return out

def _fold(args):
    d, dev = args
    tr = [r for r in dev if r['dj'] != d]; te = [r for r in dev if r['dj'] == d]
    simple, maj, majtag = baselines(tr); pk = collections.defaultdict(list); fd = {}
    for style in (True, False):
        nm = 'style' if style else 'nostyle'
        e, ci, tau = inner_select(tr, style); m = fit(tr, style, CFGS[ci]); S = predict(m, te, style)
        pk[f'model_{nm}_gated'] = [pick(r, s, tau)[0] for r, s in zip(te, S)]
        pk[f'model_{nm}_plain'] = [int(np.argmax(s)) for s in S]
        fd[nm] = dict(cfg=ci, tau=tau, inner_err=round(float(e), 2), used=int(sum(pick(r, s, tau)[1] for r, s in zip(te, S))))
    pk['default'] = [r['dix'] for r in te]; pk['rule_drop_exit'] = [simple(r) for r in te]; pk['majority'] = [maj(r) for r in te]
    pk['oracle'] = [int(np.argmax(-np.array([errs(r, c)['exit_cue'] for c in r['cands']]))) for r in te]
    fd['n'] = len(te); fd['majority_tag'] = majtag; print('fold', d, fd, flush=True)
    return d, [r['id'] for r in te], dict(pk), fd

def run_cv(rows):
    from concurrent.futures import ProcessPoolExecutor
    dev = [r for r in rows if r['set'] == 'dev']; djs = sorted({r['dj'] for r in dev}); byid = {r['id']: r for r in dev}
    X_of(dev, True); X_of(dev, False)
    picks = collections.defaultdict(list); order = []; folds = {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get('CVW', 4))) as ex:
        for d, ids, pk, fd in ex.map(_fold, [(d, dev) for d in djs]):
            for k, v in pk.items(): picks[k] += v
            order += [byid[i] for i in ids]; folds[d] = fd
    res = summarize(order, dict(picks))
    return dict(n=len(order), n_mixes=len({r['mix'] for r in order}), djs=djs, def_src=dict(collections.Counter(r['def_src'] for r in order)),
                n_cands_mean=round(float(np.mean([len(r['cands']) for r in order])), 1), folds=folds, results=res,
                per_pair=[dict(id=r['id'], dj=r['dj'], pro_out=r['pro_out'], pro_in=r['pro_in'], default=errs(r, r['cands'][r['dix']]),
                               style_gated=errs(r, r['cands'][picks['model_style_gated'][i]]), win=[r['cands'][picks['model_style_gated'][i]][k] for k in ('e', 'ib', 'X')],
                               tags=sorted(r['cands'][picks['model_style_gated'][i]]['tags'])) for i, r in enumerate(order)])

def run_final(rows, which):
    """fit on ALL dev (tuning by LODO on dev), evaluate once on `which` (protrans / holdout / fresh)"""
    dev = [r for r in rows if r['set'] == 'dev']; te = [r for r in rows if r['set'] == which]
    simple, maj, majtag = baselines(dev); picks = collections.defaultdict(list); diag = {}
    for style in (True, False):
        nm = 'style' if style else 'nostyle'
        e, ci, tau = inner_select(dev, style); m = fit(dev, style, CFGS[ci]); S = predict(m, te, style)
        picks[f'model_{nm}_gated'] = [pick(r, s, tau)[0] for r, s in zip(te, S)]; picks[f'model_{nm}_plain'] = [int(np.argmax(s)) for s in S]
        diag[nm] = dict(cfg=ci, tau=tau, used=int(sum(pick(r, s, tau)[1] for r, s in zip(te, S))))
        if style: m.booster_.save_model(os.path.join(W, f'picker_1119_{nm}.txt'))
    picks['default'] = [r['dix'] for r in te]; picks['rule_drop_exit'] = [simple(r) for r in te]; picks['majority'] = [maj(r) for r in te]
    picks['oracle'] = [int(np.argmax(-np.array([errs(r, c)['exit_cue'] for c in r['cands']]))) for r in te]
    res = summarize(te, dict(picks))
    return dict(set=which, n=len(te), mixes=sorted({r['mix'] for r in te}), def_src=dict(collections.Counter(r['def_src'] for r in te)), diag=diag, majority_tag=majtag, results=res,
                per_pair=[dict(id=r['id'], default=errs(r, r['cands'][r['dix']]), style_gated=errs(r, r['cands'][picks['model_style_gated'][i]]),
                               nostyle_gated=errs(r, r['cands'][picks['model_nostyle_gated'][i]]), win_style=[r['cands'][picks['model_style_gated'][i]][k] for k in ('e', 'ib', 'X')],
                               default_win=[r['cands'][r['dix']][k] for k in ('e', 'ib', 'X')]) for i, r in enumerate(te)])

if __name__ == '__main__':
    mode = sys.argv[1]; rows = build(rows_all(), load_rendered_defaults())
    print('sets', collections.Counter(r['set'] for r in rows), flush=True)
    out = run_cv(rows) if mode == 'cv' else run_final(rows, mode)
    tag = os.environ.get('TAG', '')
    json.dump(out, open(os.path.join(H, f'picker_1119_{mode}{tag}.json'), 'w'), indent=1, default=str)
    for n, s in out['results'].items():
        d = s.get('delta_vs_default', {}).get('exit_cue', {})
        print(f"{n:22s} exit {s['exit_mean']} cue {s['cue_mean']} ec {s['exit_cue_mean']} d {d.get('delta')} {d.get('ci')} {d.get('verdict')} "
              f"exit@16 {s['exit_hit16']} cue@16 {s['cue_hit16']} accE@8 {s['exit_acc_hit8']} accC@8 {s['cue_acc_hit8']} blendprx {s['blendlen_proxy_err_mean']} changed {s['changed_vs_default']}")
