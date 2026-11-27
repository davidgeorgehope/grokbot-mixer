#!/usr/bin/env python3
"""Joint placement picker (JOINT_PICKER, opt-in; 2026-11-27, docs/DROP_BLEND_2026-11-27.md).

Scores (exit, cue, length) triples together instead of two independent rankers plus a fixed
16-bar length. Candidates are the existing exit/cue menus (picker_1119b) crossed with
X in {8, 16, 32}; nothing about style is hand-coded. Features describe what BOTH tracks
contain across the whole overlap (section at every quarter of the blend, drop/intro/
breakdown/outro fractions, where each deck's next boundary falls relative to the blend end,
section bass/energy levels on each side) plus the old per-part features.

Labels: relevance vs the pro placement (exit rel + cue rel + length match), from dev rows only.
Listener verdicts (listener_prefs.jsonl) enter as extra groups with weight
PREF_W * ramp(n_verdicts), ramp 0 below 3 verdicts -> 1 at 6, so one verdict has no effect.
Ensemble: K LambdaMART seeds (different bagging draws) averaged -> stable argmax.
Abstain: keep the engine default unless the best triple beats it by tau (chosen on dev
leave-DJ-group-out CV). Locked holdout rows are never featurized.

  joint_picker.py export  -> joint_work/train.npz (+ eval features)   [box]
  joint_picker.py train   -> joint_work/models/*.txt                 [home Mac or box]
  joint_picker.py cv      -> tau + CV placement error                [home Mac or box]
"""
from __future__ import annotations
import json, os, sys, gzip
import numpy as np
H = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(H, 'joint_work')
XS = (8, 16, 32)
K_SEEDS = int(os.environ.get('JOINT_K', 12))
PREF_W = 5.0
PREF_MIN, PREF_FULL = 3, 6
SECN = ('intro', 'build', 'drop', 'breakdown', 'outro')


def pref_weight(n):
    if n < PREF_MIN:
        return 0.0
    return PREF_W * min(1.0, (n - PREF_MIN + 1) / (PREF_FULL - PREF_MIN + 1))


# ---------------- features (box side; needs section dicts) ----------------
def _sec(s, bar):
    for p in s.get('phases') or []:
        if p['start'] <= bar < p['end']:
            return p['name']
    if any(d[0] <= bar < d[1] for d in (s.get('drops') or [])):
        return 'drop'
    return 'outro' if bar >= (s.get('outro_start') or 1e9) else 'intro' if bar < (s.get('drop1') or 0) else 'breakdown'


def _fracs(s, a, b):
    n = max(1, b - a); c = dict.fromkeys(SECN, 0)
    for x in range(a, b):
        k = _sec(s, x); c[k if k in c else 'breakdown'] += 1
    return [c[k] / n for k in SECN]


def _bounds(s):
    v = {0, int(s.get('music_end') or s.get('n_bars') or 0)}
    for p in s.get('phases') or []:
        v.add(int(p['start'])); v.add(int(p['end']))
    return sorted(v)


def _next_b(bnd, x):
    after = [b for b in bnd if b >= x]
    return (after[0] - x) if after else 99


def _prev_b(bnd, x):
    before = [b for b in bnd if b <= x]
    return (x - before[-1]) if before else 99


def _lvl(s, name, key):
    v = ((s.get('bass_by_section') or {}).get(name) or {}).get(key)
    return np.nan if v is None else float(v)


def triple_feats(r, ex, cue, X):
    """ex/cue are 1-based starts (picker convention); overlap A [ex-1, ex-1+X), B [cue-1, cue-1+X)."""
    sa, sb = r['sa'], r['sb']
    na = int(sa.get('music_end') or sa.get('n_bars')); nb = int(sb.get('music_end') or sb.get('n_bars'))
    a0, b0 = int(ex) - 1, int(cue) - 1
    a1, b1 = a0 + X, b0 + X
    fa, fb = _fracs(sa, a0, a1), _fracs(sb, b0, b1)
    q = [0, X // 4, X // 2, 3 * X // 4, X - 1]
    seqA = [SECN.index(_sec(sa, a0 + k)) if _sec(sa, a0 + k) in SECN else 3 for k in q]
    seqB = [SECN.index(_sec(sb, b0 + k)) if _sec(sb, b0 + k) in SECN else 3 for k in q]
    ba, bb = _bounds(sa), _bounds(sb)
    secA_mid, secB_mid = _sec(sa, a0 + X // 2), _sec(sb, b0 + X // 2)
    secB_after = _sec(sb, b1)
    f = [X, ex, cue, na - a1, a0 / na, b0 / nb, nb - b1,
         _next_b(ba, a1), _prev_b(ba, a1), _next_b(bb, b1), _prev_b(bb, b1), _prev_b(bb, b0), _next_b(bb, b0), _prev_b(ba, a0),
         SECN.index(secB_after) if secB_after in SECN else 3,
         b0 - float(sb.get('drop1') or 0), a1 - float((sa.get('drops') or [[0, 0]])[-1][1]),
         _lvl(sa, secA_mid, 'bass'), _lvl(sb, secB_mid, 'bass'), _lvl(sa, secA_mid, 'energy'), _lvl(sb, secB_mid, 'energy'),
         _lvl(sa, secA_mid, 'energy') - _lvl(sb, secB_mid, 'energy')]
    f += fa + fb + seqA + seqB + [fa[i] * fb[j] for i in (2, 4) for j in (0, 2, 3)]
    import picker_1119b as B
    f += B.base_feats(r)
    return f


def triples(r):
    """Candidate triples from the existing exit/cue menus x XS; legal on the engine's bounds; default first."""
    import picker_1119b as B
    sa, sb = r['sa'], r['sb']
    na = int(sa.get('music_end') or sa.get('n_bars')); nb = int(sb.get('music_end') or sb.get('n_bars'))
    out, seen = [], set()
    def add(ex, cue, X, is_def=False):
        e = int(round((ex + X - 1) / 8) * 8) if not is_def else int(ex + X - 1)
        ib = int(round(cue - 1))
        if not is_def and not (e <= na and e - X >= 16 and ib >= 0 and ib + X <= nb - 16):
            return
        key = (e, ib, X)
        if key in seen:
            return
        seen.add(key)
        out.append(dict(win=['n', e, None, ib, X], ex=e - X + 1, cue=ib + 1, X=X, default=is_def))
    add(r['dex'], r['dcue'], int(r['dX']), True)
    for c in r['E']:
        for d in r['C']:
            for X in XS:
                add(c['v'], d['v'], X)
    return out


def rel_triple(r, t):
    import picker_1119 as P, picker_1119b as B
    re = B.rel(P.acc_err(t['ex'], r['pro_out'], P.bnd_a(r['sa'])))
    rc = B.rel(P.acc_err(t['cue'], r['pro_in'], P.bnd_b(r['sb'])))
    ov = float(r.get('pro_ov') or 16)
    px = 8 if ov <= 11 else 16 if ov <= 23 else 32
    return re + rc + 2 * int(t['X'] == px)


def featurize(rows):
    Xs, ys, grp, meta = [], [], [], []
    for r in rows:
        T = triples(r)
        Xs.append(np.array([triple_feats(r, t['ex'], t['cue'], t['X']) for t in T], float))
        ys.append(np.array([rel_triple(r, t) for t in T], float) if r.get('pro_ov') is not None else np.zeros(len(T)))
        grp.append(len(T))
        meta.append(dict(id=r['id'], set=r['set'], dj=r.get('dj'), T=T, pro=[r['pro_out'], r['pro_in'], r.get('pro_ov')]))
    return Xs, ys, grp, meta


def export(dest=WORK):
    sys.path.insert(0, H)
    import ridegate_live as R, listener_prefs as LP
    os.makedirs(dest, exist_ok=True)
    rows = [r for r in R.load_all_built() if r['set'] in ('dev', 'fresh', 'protrans')]  # holdout never featurized
    by = {r['id']: r for r in rows}
    prefs = LP.load(); pr = LP.pref_rows(by, prefs)
    for p in pr:
        p['pro_ov'] = float(p['pro_ov'])
    Xs, ys, grp, meta = featurize(rows + pr)
    w_pref = pref_weight(len([p for p in prefs if p.get('preferred') == 'ours']))
    gw = np.array([w_pref if m['set'] == 'pref' else 1.0 for m in meta])
    np.savez_compressed(os.path.join(dest, 'feats.npz'), X=np.vstack(Xs), y=np.concatenate(ys), grp=np.array(grp),
                        gw=gw, sets=np.array([m['set'] for m in meta]), djs=np.array([str(m['dj']) for m in meta]))
    json.dump([dict(id=m['id'], set=m['set'], dj=m['dj'], pro=m['pro'], T=[dict(win=t['win'], default=t['default']) for t in m['T']]) for m in meta],
              open(os.path.join(dest, 'meta.json'), 'w'))
    print('exported', len(meta), 'groups', int(np.sum(grp)), 'triples; pref weight', w_pref, flush=True)


# ---------------- training (home Mac or box; numpy + lightgbm only) ----------------
def _load(src=WORK):
    # Materialize once. NpzFile re-decompresses the whole array on every z['X'] access; slicing it
    # per group inside a loop is what blew the 11-27 home-Mac run up to ~20 GB per worker.
    z0 = np.load(os.path.join(src, 'feats.npz'), allow_pickle=False)
    z = {k: z0[k] for k in z0.files if k != 'X'}
    xm = os.path.join(src, 'X32.npy')
    if not os.path.exists(xm):
        np.save(xm, z0['X'].astype(np.float32))
    z['X'] = np.load(xm, mmap_mode='r')  # shared page cache across workers
    off = np.concatenate([[0], np.cumsum(z['grp'])])
    return z, off


def _fit(z, off, gids, seed, n_jobs=1):
    import lightgbm as lgb
    X = np.vstack([z['X'][off[g]:off[g + 1]] for g in gids]); y = np.concatenate([z['y'][off[g]:off[g + 1]] for g in gids])
    w = np.concatenate([np.full(off[g + 1] - off[g], z['gw'][g]) for g in gids])
    keep = w > 0
    if not keep.all():
        gkeep = [g for g in gids if z['gw'][g] > 0]
        return _fit(z, off, gkeep, seed, n_jobs)
    m = lgb.LGBMRanker(objective='lambdarank', n_estimators=250, num_leaves=15, learning_rate=0.05, min_child_samples=40,
                       subsample=0.7, subsample_freq=1, colsample_bytree=0.7, random_state=seed, verbose=-1, n_jobs=n_jobs,
                       label_gain=list(range(0, 32)))
    m.fit(X, y, group=[off[g + 1] - off[g] for g in gids], sample_weight=w)
    return m.booster_


def _ens_fit(args):
    src, gids, seeds = args
    z, off = _load(src)
    return [_fit(z, off, gids, s).model_to_string() for s in seeds]


def train_ensemble(gids, src=WORK, k=K_SEEDS, workers=None):
    from concurrent.futures import ProcessPoolExecutor
    workers = workers or int(os.environ.get('JOINT_WORKERS', 4))
    seeds = [20261127 + i for i in range(k)]
    chunks = [seeds[i::workers] for i in range(workers) if seeds[i::workers]]
    with ProcessPoolExecutor(workers) as ex:
        out = [s for part in ex.map(_ens_fit, [(src, gids, c) for c in chunks]) for s in part]
    import lightgbm as lgb
    return [lgb.Booster(model_str=s) for s in out]


def ens_scores(models, Xg):
    S = np.mean([m.predict(Xg) for m in models], axis=0)
    return S


def train(src=WORK, extra_dup=None):
    z, off = _load(src)
    sets = z['sets']
    gids = [g for g in range(len(sets)) if sets[g] in ('dev', 'pref')]
    if extra_dup is not None:
        pass
    models = train_ensemble(gids, src)
    d = os.path.join(src, 'models'); os.makedirs(d, exist_ok=True)
    for i, m in enumerate(models):
        with gzip.open(os.path.join(d, f'm{i:02d}.txt.gz'), 'wt') as f:
            f.write(m.model_to_string())
    print('trained', len(models), 'on', len(gids), 'groups', flush=True)


def cv(src=WORK, folds=5):
    """Grouped-by-DJ CV on dev: out-of-fold ensemble scores -> tau grid. Writes cv.json."""
    z, off = _load(src)
    meta = json.load(open(os.path.join(src, 'meta.json')))
    sets, djs = z['sets'], z['djs']
    dev = [g for g in range(len(sets)) if sets[g] == 'dev']
    udj = sorted({djs[g] for g in dev}); rng = np.random.RandomState(7); rng.shuffle(udj)
    fold_of = {d: i % folds for i, d in enumerate(udj)}
    oof = {}
    for f in range(folds):
        tr = [g for g in dev if fold_of[djs[g]] != f] + [g for g in range(len(sets)) if sets[g] == 'pref']
        te = [g for g in dev if fold_of[djs[g]] == f]
        ms = train_ensemble(tr, src)
        for g in te:
            oof[g] = ens_scores(ms, z['X'][off[g]:off[g + 1]]).tolist()
        print('fold', f, len(te), flush=True)
    json.dump(dict(oof={str(g): s for g, s in oof.items()}), open(os.path.join(src, 'cv_oof.json'), 'w'))


def stab(src=WORK, n=3):
    """Retrain with one duplicated dev group (n random) and count changed fresh argmax picks vs the base ensemble."""
    z, off = _load(src)
    sets = z['sets']
    base = [g for g in range(len(sets)) if sets[g] in ('dev', 'pref')]
    fresh = [g for g in range(len(sets)) if sets[g] == 'fresh']
    def picks(ms):
        return [int(np.argmax(ens_scores(ms, z['X'][off[g]:off[g + 1]]))) for g in fresh]
    p0 = picks(train_ensemble(base, src))
    rng = np.random.RandomState(3); out = []
    for d in rng.choice([g for g in base if sets[g] == 'dev'], n, replace=False):
        p1 = picks(train_ensemble(base + [int(d)], src))
        out.append(int(sum(a != b for a, b in zip(p0, p1))))
        print('dup', int(d), 'fresh flips', out[-1], 'of', len(fresh), flush=True)
    json.dump(dict(flips=out, n_fresh=len(fresh), k=K_SEEDS), open(os.path.join(src, f'stab_k{K_SEEDS}.json'), 'w'))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'export':
        export()
    elif cmd == 'train':
        train(sys.argv[2] if len(sys.argv) > 2 else WORK)
    elif cmd == 'cv':
        cv(sys.argv[2] if len(sys.argv) > 2 else WORK)
    elif cmd == 'stab':
        stab(sys.argv[2] if len(sys.argv) > 2 else WORK)
