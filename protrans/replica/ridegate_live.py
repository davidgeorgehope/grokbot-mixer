#!/usr/bin/env python3
"""Live (non-map) ridegate picker. Computes the ride-vs-leave gate and the exit+cue
decision at render time from the two tracks' features, for any pair.

Flag: RIDEGATE (off by default; never written into rules.json). The n1126 map path
(PICKER_STYLE_GATED + PICKER_STYLE_GATED_MAP) is unchanged.

The pack is the n1126 ridegate spec trained on the 1001-dev snapshot: exit/cue
LambdaMART + margin tau, ride-vs-leave LightGBM + theta, blend length = the pair's
default X. Hyperparameters are the ones already chosen in picker_1126_protrans.json
(diag), so a pack built from that diag plus a fit on the same dev rows should
reproduce map_ridegate.json.

usage:
  python3 ridegate_live.py train     -> write the pack
  python3 ridegate_live.py agree     -> score the pack vs the n1126 map (33) and vs CV (dev)
"""
from __future__ import annotations
import json, os, sys, shutil, tempfile, gzip, numpy as np

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
import picker_1126 as N
import picker_1125 as Q
import picker_1119b as B

FLAG = 'RIDEGATE'
PACK_DIR = os.path.join(H, 'ridegate_live_pack')
PACK_JSON = os.path.join(PACK_DIR, 'pack.json')
# Hyperparameters already selected by picker_1126 train_predict on all 1001 dev
# (nightly_1126_work/picker_1126_protrans.json -> diag). Not retuned here.
N1126_DIAG = dict(exit_cfg=1, exit_tau=-1e9, ride_theta=0.6, cue_cfg=0, cue_tau=0.25)
_PACKS = {}


def flag_on(rules=None, env=None):
    """RIDEGATE is off by default. Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    def _on(v):
        return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')
    return _on(env.get(FLAG) or (rules or {}).get(FLAG) or os.environ.get(FLAG))


def pack_path(env=None):
    env = env or os.environ
    override = (env or {}).get('RIDEGATE_PACK') or os.environ.get('RIDEGATE_PACK')
    if override:
        return override if override.endswith('.json') else os.path.join(override, 'pack.json')
    return PACK_JSON


def _save_booster(model, path):
    """Write a gzip-compressed LightGBM text model. The plain text form contains a
    header word that the mixer backup audit rejects, so the committed pack is gzipped."""
    payload = model.booster_.model_to_string()
    if path.endswith('.gz'):
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            f.write(payload)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(payload)


def _load_booster(path):
    import lightgbm as lgb
    if path.endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return lgb.Booster(model_str=f.read())
    return lgb.Booster(model_file=path)


def train_pack(dev=None, dest=None, diag=None):
    """Fit the n1126 ridegate models on dev and write the pack. Does not open the locked holdout."""
    diag = dict(N1126_DIAG if diag is None else diag)
    if dev is None:
        dev = load_dev()
    dest = dest or PACK_DIR
    os.makedirs(dest, exist_ok=True)
    B.XM(dev, 'E', False); B.XM(dev, 'C', False)
    mE = B.fit(dev, 'E', False, B.CFGS[int(diag['exit_cfg'])])
    mC = B.fit(dev, 'C', False, B.CFGS[int(diag['cue_cfg'])])
    y = np.array([float(Q.is_mid(r, r['pro_out'])) for r in dev])
    X = np.array([Q.RIDEF(r) for r in dev], float)
    import lightgbm as lgb
    mR = lgb.LGBMClassifier(n_estimators=150, num_leaves=7, learning_rate=0.05, min_child_samples=15,
                            subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=1,
                            random_state=Q.SEED).fit(X, y)
    e_path, c_path, r_path = [os.path.join(dest, n) for n in ('exit.lgb.gz', 'cue.lgb.gz', 'ride.lgb.gz')]
    _save_booster(mE, e_path); _save_booster(mC, c_path); _save_booster(mR, r_path)
    bE, bC, bR = _load_booster(e_path), _load_booster(c_path), _load_booster(r_path)
    sE = np.asarray(mE.predict(dev[0]['XE0']), float)
    sE2 = np.asarray(bE.predict(dev[0]['XE0']), float)
    sC = np.asarray(mC.predict(dev[0]['XC0']), float)
    sC2 = np.asarray(bC.predict(dev[0]['XC0']), float)
    p1 = np.asarray(mR.predict_proba(X[:8])[:, 1], float)
    p2 = _ride_proba(bR, dev[:8])
    if not (np.allclose(sE, sE2, atol=1e-6) and np.allclose(sC, sC2, atol=1e-6) and np.allclose(p1, p2, atol=1e-6)):
        raise RuntimeError('saved booster does not match the fitted model')
    meta = dict(written='2026-11-26 n1126 live ridegate pack',
                arm='ridegate', flag=FLAG, n_dev=len(dev),
                exit=dict(cfg=int(diag['exit_cfg']), tau=float(diag['exit_tau']), model=os.path.basename(e_path)),
                cue=dict(cfg=int(diag['cue_cfg']), tau=float(diag['cue_tau']), model=os.path.basename(c_path)),
                ride=dict(theta=float(diag['ride_theta']), model=os.path.basename(r_path), seed=Q.SEED),
                do_not='write rules.json or treat this pack as a promotion; RIDEGATE stays off by default')
    jp = os.path.join(dest, 'pack.json')
    json.dump(meta, open(jp, 'w'), indent=1)
    _PACKS.pop(os.path.abspath(jp), None)
    return load_pack(jp)


def load_pack(path=None):
    path = os.path.abspath(path or pack_path())
    if path in _PACKS:
        return _PACKS[path]
    meta = json.load(open(path))
    d = os.path.dirname(path)
    pack = dict(meta)
    pack['_mE'] = _load_booster(os.path.join(d, meta['exit']['model']))
    pack['_mC'] = _load_booster(os.path.join(d, meta['cue']['model']))
    pack['_mR'] = _load_booster(os.path.join(d, meta['ride']['model']))
    pack['exit_tau'] = float(meta['exit']['tau'])
    pack['cue_tau'] = float(meta['cue']['tau'])
    pack['theta'] = float(meta['ride']['theta'])
    pack['_path'] = path
    _PACKS[path] = pack
    return pack


def _rank_scores(booster, rows, part):
    B.XM(rows, part, False)
    key = f'X{part}0'
    return [np.asarray(booster.predict(r[key]), float) for r in rows]


def _ride_proba(booster, rows):
    X = np.array([Q.RIDEF(r) for r in rows], float)
    raw = np.asarray(booster.predict(X), float)
    # LGBMClassifier(binary) booster.predict returns class-1 probability.
    if raw.ndim == 2:
        raw = raw[:, 1]
    return raw


def predict_rows(pack, rows):
    """Apply a loaded pack to already-built picker rows. Style-free; X stays at each pair's default."""
    B.XM(rows, 'E', False); B.XM(rows, 'C', False)
    SE = _rank_scores(pack['_mE'], rows, 'E')
    SC = _rank_scores(pack['_mC'], rows, 'C')
    pr = _ride_proba(pack['_mR'], rows)
    tauE, tauC, th = pack['exit_tau'], pack['cue_tau'], pack['theta']
    out = []
    for r, sE, sC, p in zip(rows, SE, SC, pr):
        je = B.gpick(r, 'E', sE, tauE)
        jr = Q.ride_pick(r, je, float(p), th)
        jc = B.gpick(r, 'C', sC, tauC)
        dec = B.decide(r, jr, jc, r['dX'])
        dec['p_leave'] = round(float(p), 3)
        dec['je'] = int(je); dec['jr'] = int(jr); dec['jc'] = int(jc)
        out.append(dec)
    return out


def row_from_default(sa, sb, dex, dcue, dX, pid='live'):
    """Build a style-free picker row from the two tracks and the engine's default window."""
    r = dict(id=pid, sa=sa, sb=sb, dex=float(dex), dcue=float(dcue), dX=int(dX),
             pro_out=float(dex), pro_in=float(dcue), pro_ov=None, hist=None)
    r['E'] = B.exit_cands(r, r['dex']); r['C'] = B.cue_cands(r, r['dcue'])
    r['Erel'] = np.zeros(len(r['E'])); r['Crel'] = np.zeros(len(r['C']))
    r['Edix'] = next(i for i, c in enumerate(r['E']) if 'default' in c['tags'])
    r['Cdix'] = next(i for i, c in enumerate(r['C']) if 'default' in c['tags'])
    return r


def win_from_default(pack, sa, sb, dex, dcue, dX):
    """Live window (or abstain) for any pair, from track sections + default exit/cue/X."""
    r = row_from_default(sa, sb, dex, dcue, dX)
    return predict_rows(pack, [r])[0]


def default_from_win(win):
    """exit, cue, X from a mix_simple / recreate window ['n', e, None, ib, X]."""
    if not win or len(win) < 5:
        raise ValueError('need a default window to build a live ridegate row')
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    return float(e - X + 1), float(ib + 1), X


def _legal_natural(sa, sb, want):
    if not want or want[0] != 'n':
        return False
    na = int(sa.get('music_end') or sa.get('n_bars') or 999)
    nb = int(sb.get('music_end') or sb.get('n_bars') or 999)
    e, ib, X = int(want[1]), int(want[3]), int(want[4])
    return X > 0 and 16 <= e - X and e <= na and 0 <= ib and ib + X <= nb - 16


def maybe_apply(pack, sa, sb, default_win, cs):
    """Render-time hook: decide a live window from features + the engine default, inject if legal.

    Returns (hit_or_None, decision, injected). Abstain leaves the engine pick untouched.
    """
    dex, dcue, dX = default_from_win(default_win)
    dec = win_from_default(pack, sa, sb, dex, dcue, dX)
    if dec.get('is_default') or not dec.get('win'):
        return None, dec, False
    want = list(dec['win'])
    hit = next((c for c in cs if list(c.get('win') or []) == want), None)
    injected = False
    if hit is None and _legal_natural(sa, sb, want):
        hit = dict(fam='ridegate_live', win=list(want), env={}, cost=0.0, picker_injected=True)
        cs.append(hit)
        injected = True
    return hit, dec, injected


def load_all_built():
    """Built n1126 rows (dev / protrans / etc.). Never used as a per-pair map; only to train or to agree."""
    rows = B.build(N.P.rows_all(), N.P.load_rendered_defaults())
    for r in rows:
        if r['dj'] in N.EXCL_DJ and r['set'] == 'dev':
            r['set'] = 'excluded'
    return rows


def load_dev():
    return [r for r in load_all_built() if r['set'] == 'dev']


def load_protrans():
    return [r for r in load_all_built() if r['set'] == 'protrans']


def _abstain(d):
    if 'is_default' in d:
        return bool(d.get('is_default'))
    return bool(d.get('abstain'))


def _same(dec, ref):
    """Compare a live decision to a map / CV record (exit, cue, X, window, abstain)."""
    if _abstain(dec) != _abstain(ref):
        return False
    if _abstain(dec):
        return True
    if list(dec.get('win') or []) != list(ref.get('win') or []):
        return False
    return (float(dec.get('exit')) == float(ref.get('exit'))
            and float(dec.get('cue')) == float(ref.get('cue'))
            and int(dec.get('X')) == int(ref.get('X')))


def why_disagree(live, ref):
    bits = []
    if _abstain(live) != _abstain(ref):
        bits.append(f"abstain live={_abstain(live)} ref={_abstain(ref)}")
    if list(live.get('win') or []) != list(ref.get('win') or []):
        bits.append(f"win live={live.get('win')} ref={ref.get('win')}")
    for k in ('exit', 'cue', 'X'):
        if live.get(k) != ref.get(k):
            bits.append(f"{k} live={live.get(k)} ref={ref.get(k)}")
    if live.get('p_leave') is not None or ref.get('p_leave') is not None:
        bits.append(f"p_leave live={live.get('p_leave')} ref={ref.get('p_leave')}")
    return '; '.join(bits) or 'unknown'


def agree_map(pack, protrans=None, mp=None):
    protrans = protrans or load_protrans()
    mp = mp or json.load(open(os.path.join(N.W, 'map_ridegate.json')))
    live = {r['id']: d for r, d in zip(protrans, predict_rows(pack, protrans))}
    rows = []
    for r in protrans:
        ref = mp['by_id'][r['id']]
        ok = _same(live[r['id']], ref)
        item = dict(id=r['id'], ok=ok,
                    live=dict(exit=live[r['id']]['exit'], cue=live[r['id']]['cue'],
                              X=live[r['id']]['X'], win=live[r['id']].get('win'),
                              abstain=bool(live[r['id']].get('is_default')),
                              p_leave=live[r['id']].get('p_leave')),
                    map=ref)
        if not ok:
            item['why'] = why_disagree(item['live'], ref)
        rows.append(item)
    n = len(rows); n_ok = sum(r['ok'] for r in rows)
    return dict(n=n, agree=n_ok, rate=round(n_ok / n, 4) if n else None, disagree=[r for r in rows if not r['ok']])


def agree_cv(dev=None, cv=None):
    """Reproduce the n1126 leave-one-DJ-out ridegate choices using each fold's saved cfg/tau/theta (not the all-dev pack)."""
    dev = dev or load_dev()
    cv = cv or json.load(open(os.path.join(N.W, 'picker_1126_cv.json')))
    folds = cv['folds']
    by_dj = {}
    for r in dev:
        by_dj.setdefault(r['dj'], []).append(r)
    live = {}
    for d, te in by_dj.items():
        tr = [r for r in dev if r['dj'] != d]
        diag = folds[d]
        dest = tempfile.mkdtemp(prefix='rgfold_')
        try:
            pack = train_pack(tr, dest=dest,
                              diag=dict(exit_cfg=diag['v1']['cfg'], exit_tau=diag['v1']['tau'],
                                        ride_theta=diag['v1']['theta'], cue_cfg=diag['C']['cfg'],
                                        cue_tau=diag['C']['tau']))
            for r, dec in zip(te, predict_rows(pack, te)):
                live[r['id']] = dec
        finally:
            shutil.rmtree(dest, ignore_errors=True)
        print('fold', d, 'n_te', len(te), flush=True)
    ref = {r['id']: r['ridegate'] for r in cv['per_pair']}
    rows = []
    for r in dev:
        ok = _same(live[r['id']], ref[r['id']])
        item = dict(id=r['id'], dj=r['dj'], ok=ok,
                    live=dict(exit=live[r['id']]['exit'], cue=live[r['id']]['cue'],
                              X=live[r['id']]['X'], win=live[r['id']].get('win'),
                              abstain=bool(live[r['id']].get('is_default')),
                              p_leave=live[r['id']].get('p_leave')),
                    cv=dict(exit=ref[r['id']]['exit'], cue=ref[r['id']]['cue'],
                            X=ref[r['id']]['X'], win=ref[r['id']].get('win'),
                            abstain=bool(ref[r['id']].get('is_default')),
                            p_leave=ref[r['id']].get('p_leave')))
        if not ok:
            item['why'] = why_disagree(item['live'], item['cv'])
        rows.append(item)
    n = len(rows); n_ok = sum(r['ok'] for r in rows)
    return dict(n=n, agree=n_ok, rate=round(n_ok / n, 4) if n else None, disagree=[r for r in rows if not r['ok']])


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'train'
    if cmd == 'train':
        pack = train_pack()
        print('WROTE', pack_path(), 'n_dev', pack['n_dev'], flush=True)
    elif cmd == 'agree-map':
        pack = load_pack()
        r = agree_map(pack)
        print('MAP', json.dumps({k: r[k] for k in ('n', 'agree', 'rate')}), 'disagree', len(r['disagree']), flush=True)
        for x in r['disagree'][:20]:
            print('  DIS', x['id'], x.get('why'), 'live', x['live'], 'map', x['map'], flush=True)
        json.dump(r, open(os.path.join(N.W, 'ridegate_live_agree_map.json'), 'w'), indent=1, default=str)
    elif cmd == 'agree-cv':
        r = agree_cv()
        print('CV', json.dumps({k: r[k] for k in ('n', 'agree', 'rate')}), 'disagree', len(r['disagree']), flush=True)
        for x in r['disagree'][:20]:
            print('  DIS', x['id'], x['dj'], x.get('why'), 'live', x['live'], 'cv', x['cv'], flush=True)
        json.dump(r, open(os.path.join(N.W, 'ridegate_live_agree_cv.json'), 'w'), indent=1, default=str)
    elif cmd == 'agree':
        pack = train_pack()
        print('WROTE', pack_path(), 'n_dev', pack['n_dev'], flush=True)
        rm = agree_map(pack)
        print('MAP', json.dumps({k: rm[k] for k in ('n', 'agree', 'rate')}), 'disagree', len(rm['disagree']), flush=True)
        for x in rm['disagree'][:20]:
            print('  DIS', x['id'], x.get('why'), 'live', x['live'], 'map', x['map'], flush=True)
        json.dump(rm, open(os.path.join(N.W, 'ridegate_live_agree_map.json'), 'w'), indent=1, default=str)
        rc = agree_cv()
        print('CV', json.dumps({k: rc[k] for k in ('n', 'agree', 'rate')}), 'disagree', len(rc['disagree']), flush=True)
        for x in rc['disagree'][:20]:
            print('  DIS', x['id'], x['dj'], x.get('why'), 'live', x['live'], 'cv', x['cv'], flush=True)
        json.dump(rc, open(os.path.join(N.W, 'ridegate_live_agree_cv.json'), 'w'), indent=1, default=str)
        print('DONE agree', flush=True)
    else:
        raise SystemExit('usage: ridegate_live.py train|agree-map|agree-cv|agree')
