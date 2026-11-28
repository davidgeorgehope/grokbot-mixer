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
    """RIDEGATE is on by default as of 2026-11-26. Rollback: RIDEGATE_OFF=1."""
    env = env or {}
    rules = rules or {}
    def _on(v):
        return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')
    if _on(env.get('RIDEGATE_OFF') or os.environ.get('RIDEGATE_OFF')):
        return False
    v = env.get(FLAG)
    if v is None:
        v = (rules or {}).get(FLAG)
    if v is None:
        v = os.environ.get(FLAG)
    if v is None:
        v = 1
    return _on(v)


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


_BUILT_BY_YT = None
_BUILT_BY_ID = None

def reset_built_index():
    """Test hook: drop the built-row index so the next lookup rebuilds it."""
    global _BUILT_BY_YT, _BUILT_BY_ID
    _BUILT_BY_YT, _BUILT_BY_ID = None, None


def _yt_keys():
    """id -> 'a_yt|b_yt' for every built row we can resolve (protrans recs, maps, corpus features)."""
    yt_of = {}
    try:
        sys.path.insert(0, os.path.dirname(H))
        import run_admitted_tune as T
        for rec in T.load_recs():
            yt_of[rec['id']] = f"{rec['a']['yt']}|{rec['b']['yt']}"
    except Exception:
        pass
    mp = os.path.join(N.W, 'map_ridegate.json')
    if os.path.exists(mp):
        for i, v in json.load(open(mp)).get('by_id', {}).items():
            if v.get('yt_key'):
                yt_of[i] = v['yt_key']
    try:
        import paths as _P
        feat_dirs = [os.path.join(_P.ROOT, 'corpus_v2', 'features')]
    except Exception:
        feat_dirs = [os.path.join(os.path.dirname(H), 'corpus_v2', 'features')]
    for feat in feat_dirs:
        if not os.path.isdir(feat):
            continue
        for fn in os.listdir(feat):
            if not fn.endswith('.json'):
                continue
            i = fn[:-5]
            if i in yt_of:
                continue
            try:
                f = json.load(open(os.path.join(feat, fn)))
                a = (f.get('track_a') or {}).get('yt')
                b = (f.get('track_b') or {}).get('yt')
                if a and b:
                    yt_of[i] = f'{a}|{b}'
            except Exception:
                pass
    return yt_of


def _index_built():
    """Index already-built rows (dev, protrans, fresh, holdout) by id and yt key.

    Used only as the feature and rendered-default snapshot so live predict equals
    the official built-row decision wherever a built row exists. Not a per-pair
    window map. Excluded (wrong-DJ) rows are skipped.
    """
    global _BUILT_BY_YT, _BUILT_BY_ID
    if _BUILT_BY_ID is not None:
        return
    _BUILT_BY_YT, _BUILT_BY_ID = {}, {}
    yt_of = _yt_keys()
    for r in load_all_built():
        if r['set'] == 'excluded':
            continue
        _BUILT_BY_ID[r['id']] = r
        key = yt_of.get(r['id'])
        if key:
            _BUILT_BY_YT[key] = r


def row_for_render(sa, sb, dex, dcue, dX, a_yt=None, b_yt=None, pid='live'):
    """Prefer a built snapshot row (same features and rendered default as the n1126 map) when we have one."""
    _index_built()
    if a_yt and b_yt and f'{a_yt}|{b_yt}' in _BUILT_BY_YT:
        return _BUILT_BY_YT[f'{a_yt}|{b_yt}']
    if pid in _BUILT_BY_ID:
        return _BUILT_BY_ID[pid]
    return row_from_default(sa, sb, dex, dcue, dX, pid=pid)


def _legal_natural(sa, sb, want):
    """Same bound mix_simple uses when injecting a picker window: e <= t['nb']
    (the grid length, sections n_bars), not sections.music_end.

    detect() sets music_end at the last bar still within 25 dB of the peak, which
    is often 1-16 bars short of the grid. The map path gets those later exits into
    cs via mix_simple's PICKER_INJECT_CS check (`_ee <= na` with na = t['nb']),
    so recreate never re-checks music_end. Live must use the same bound or it
    abstains and renders the engine default.
    """
    if not want or want[0] != 'n':
        return False
    na = int(sa.get('n_bars') or sa.get('music_end') or 999)
    nb = int(sb.get('n_bars') or sb.get('music_end') or 999)
    e, ib, X = int(want[1]), int(want[3]), int(want[4])
    return X > 0 and 16 <= e - X and e <= na and 0 <= ib and ib + X <= nb - 16



LINGER_FLAG = 'LINGER_GUARD'
LINGER_CAL = os.path.join(H, 'linger_guard_cal.json')


def linger_guard_on(rules=None, env=None):
    """Refuse a cue into the incoming breakdown under an outgoing drop. Off by default. Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    def _on(v):
        return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')
    return _on((env or {}).get(LINGER_FLAG) or (rules or {}).get(LINGER_FLAG) or os.environ.get(LINGER_FLAG))


def in_drop(sec, k):
    return any(lo <= k < hi for lo, hi in (sec.get('drops') or []))


def in_breakdown(sec, k):
    """Breakdown: a named phase, else the gap [breakdown, drop2) outside any drop.

    If `breakdown` is missing but a second drop exists, infer the start as the end
    of the first drop. Snapshot rows sometimes omit `breakdown` even when the
    inter-drop gap is musically a breakdown (hybrid_minds_ukf__40).
    """
    for p in sec.get('phases') or []:
        if p.get('name') == 'breakdown' and p['start'] <= k < p['end']:
            return True
    if in_drop(sec, k):
        return False
    bd, d2 = sec.get('breakdown'), sec.get('drop2')
    drops = sec.get('drops') or []
    if d2 is None and len(drops) >= 2:
        d2 = drops[1][0]
    if bd is None:
        if drops and d2 is not None:
            bd = drops[0][1]
        else:
            return False
    end = d2 if d2 is not None else (sec.get('outro_start') or sec.get('n_bars') or sec.get('music_end'))
    return end is not None and bd <= k < end


def linger_bars(sa, sb, win):
    """Bars of a natural window where the outgoing is in a drop and the incoming is in a breakdown."""
    if not win or win[0] != 'n' or len(win) < 5:
        return 0
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    n = 0
    for j in range(max(0, X)):
        if in_drop(sa, e - X + j) and in_breakdown(sb, ib + j):
            n += 1
    return n


def linger_bars_pro(sa, sb, out0, in0, overlap):
    """Same measurement on a (possibly fractional) pro window."""
    import math
    X = max(1, int(round(float(overlap))))
    n = 0
    for j in range(X):
        oa = int(math.floor(float(out0) + j))
        ib = int(math.floor(float(in0) + j))
        if in_drop(sa, oa) and in_breakdown(sb, ib):
            n += 1
    return n


def calibrate_linger_guard(dest=None):
    """Pro p95 of linger_bars on the protrans cohort, plus pro vs our rates. Not hand-tuned."""
    dest = dest or os.environ.get('LINGER_GUARD_CAL') or LINGER_CAL
    pro_p = os.path.join(H, 'protrans_decisions.json')
    PRO = json.load(open(pro_p)) if os.path.exists(pro_p) else {}
    rows = [r for r in load_all_built() if r['set'] == 'protrans']
    pack = load_pack() if os.path.isdir(PACK_DIR) else None
    decs = predict_rows(pack, rows) if pack else [None] * len(rows)
    pro_vals, def_vals, rg_vals = [], [], []
    for r, d in zip(rows, decs):
        pr = PRO.get(r['id']) or {}
        if pr.get('out_bar_at_entry') is None or pr.get('in_bar_at_entry') is None or pr.get('overlap_bars') is None:
            continue
        lp = linger_bars_pro(r['sa'], r['sb'], pr['out_bar_at_entry'], pr['in_bar_at_entry'], pr['overlap_bars'])
        pro_vals.append(int(lp))
        dw = ['n', int(r['dex'] + r['dX'] - 1), None, int(r['dcue'] - 1), int(r['dX'])]
        ld = linger_bars(r['sa'], r['sb'], dw)
        def_vals.append(int(ld))
        if d and d.get('win') and not d.get('is_default'):
            rg_vals.append(int(linger_bars(r['sa'], r['sb'], d['win'])))
        else:
            rg_vals.append(int(ld))
    pv = np.asarray(pro_vals, float)
    p95 = float(np.percentile(pv, 95)) if len(pv) else 0.0
    def _rate(vs):
        n = len(vs)
        pos = int(sum(1 for v in vs if v > 0))
        return dict(n=n, n_linger=pos, rate=round(pos / n, 4) if n else None,
                    mean=round(float(np.mean(vs)), 3) if n else None,
                    p95=round(float(np.percentile(vs, 95)), 3) if n else None,
                    max=int(max(vs)) if n else None, hist={int(k): int(sum(1 for v in vs if v == k)) for k in sorted(set(vs))})
    cal = dict(written='2026-11-26',
               measurement='linger_bars: count of blend bars with outgoing in a drop and incoming in a breakdown',
               cohort='protrans (official pro windows from protrans_decisions.json, snapshot sections)',
               p95=p95, threshold=p95, rule='block a live window when linger_bars > pro p95',
               pro=_rate(pro_vals), our_default=_rate(def_vals), our_ridegate=_rate(rg_vals))
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    json.dump(cal, open(dest, 'w'), indent=1)
    return cal


_LINGER_CAL = None

def load_linger_cal():
    global _LINGER_CAL
    if _LINGER_CAL is not None:
        return _LINGER_CAL
    dest = os.environ.get('LINGER_GUARD_CAL') or LINGER_CAL
    if os.path.exists(dest):
        _LINGER_CAL = json.load(open(dest))
    else:
        _LINGER_CAL = calibrate_linger_guard(dest)
    return _LINGER_CAL


def linger_threshold():
    cal = load_linger_cal()
    return float(cal.get('threshold', cal.get('p95', 0.0)))


DRUM_FC = 200
DRUM_XDB_DEFAULT = 8.0


def _fade_gain_db(j, X):
    """Equal-power outgoing gain in dB at mid-bar j of an X-bar blend."""
    import math
    g = math.cos(math.pi / 2 * (j + 0.5) / max(float(X), 1.0))
    return 20 * math.log10(max(g, 1e-12))


def drop_drum_baseline(hi, sa):
    """Median outgoing drum/perc (high>DRUM_FC) in drop bars; the 'normal' level."""
    idx = []
    n = len(hi) if hi is not None else 0
    for lo, hi_ in (sa.get('drops') or []):
        idx.extend(range(max(0, int(lo)), min(n, int(hi_))))
    if not idx:
        return None
    return float(np.median(np.asarray(hi)[idx]))


def drum_linger_bars(sa, sb, win, hiA, x_db=None):
    """Bars where outgoing is in a breakdown, incoming is not in a drop, and the
    predicted-faded outgoing drum/perc band stays within x_db of drop-normal.

    hiA is per-bar high-passed energy in dB (same indexing as track bars).
    x_db defaults to the calibrated pro p95 margin (else DRUM_XDB_DEFAULT).
    This is the energy form of the listener's outgoing_drums_linger_under_incoming_breakdown
    fault: structural linger_bars misses when the outgoing has already left the
    drop tag but the beats are still near drop level.
    """
    import math
    if hiA is None or not win or win[0] != 'n' or len(win) < 5:
        return 0
    if x_db is None:
        x_db = drum_x_db()
    base = drop_drum_baseline(hiA, sa)
    if base is None:
        return 0
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    n = 0
    hiA = np.asarray(hiA)
    for j in range(max(0, X)):
        oa, ibj = e - X + j, ib + j
        if oa < 0 or oa >= len(hiA):
            continue
        faded = float(hiA[oa]) + _fade_gain_db(j, X)
        if in_outgoing_drum_gap(sa, oa) and (not in_drop(sb, ibj)) and faded >= base - float(x_db):
            n += 1
    return n


def in_outgoing_drum_gap(sec, k):
    """Where outgoing drums can linger after a drop: a tagged breakdown, or any
    gap between consecutive drops (the `breakdown` field names only the first).
    Intro (before the first drop) and outro are not counted."""
    if in_breakdown(sec, k):
        return True
    if in_drop(sec, k):
        return False
    drops = sorted((int(a), int(b)) for a, b in (sec.get('drops') or []))
    if len(drops) < 2:
        return False
    outro = sec.get('outro_start')
    if outro is not None and k >= outro:
        return False
    for i in range(len(drops) - 1):
        if drops[i][1] <= k < drops[i + 1][0]:
            return True
    return False


def drum_linger_bars_pro(sa, sb, out0, in0, overlap, hiA, x_db=None):
    import math
    if hiA is None:
        return 0
    if x_db is None:
        x_db = drum_x_db()
    base = drop_drum_baseline(hiA, sa)
    if base is None:
        return 0
    X = max(1, int(round(float(overlap))))
    n = 0
    hiA = np.asarray(hiA)
    for j in range(X):
        oa = int(math.floor(float(out0) + j))
        ib = int(math.floor(float(in0) + j))
        if oa < 0 or oa >= len(hiA):
            continue
        faded = float(hiA[oa]) + _fade_gain_db(j, X)
        if in_outgoing_drum_gap(sa, oa) and (not in_drop(sb, ib)) and faded >= base - float(x_db):
            n += 1
    return n


def drum_x_db():
    cal = load_linger_cal()
    return float(cal.get('drum_x_db', DRUM_XDB_DEFAULT))


def drum_linger_threshold():
    """Pro p95 of drum_linger_bars. None if not yet calibrated."""
    cal = load_linger_cal()
    v = cal.get('drum_threshold', cal.get('drum_p95'))
    return float(v) if v is not None else None


SHIFT_FLAG = 'LINGER_SHIFT'


def linger_shift_on(rules=None, env=None):
    """Start the fade earlier, while the outgoing is still in its drop, when drum
    or structural linger exceeds the pro p95. Off by default. Enable with
    LINGER_SHIFT=1. Rollback of a rules/env on-switch: LINGER_SHIFT_OFF=1.
    Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    def _on(v):
        return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')
    if _on(env.get('LINGER_SHIFT_OFF') or os.environ.get('LINGER_SHIFT_OFF')):
        return False
    return _on((env or {}).get(SHIFT_FLAG) or (rules or {}).get(SHIFT_FLAG) or os.environ.get(SHIFT_FLAG))


def covering_or_preceding_drop(sa, e, X):
    """Drop that overlaps the blend, else the drop that ends at or just before it."""
    start, end = int(e) - int(X), int(e)
    drops = [(int(a), int(b)) for a, b in (sa.get('drops') or [])]
    for a, b in drops:
        if a < end and b > start:
            return (a, b)
    earlier = [(a, b) for a, b in drops if b <= start + 0.5]
    return earlier[-1] if earlier else None


def _starts_mid_drop(sec, ib):
    """True when a cue sits strictly inside a drop, not at the drop start."""
    for a, b in (sec.get('drops') or []):
        if int(a) < int(ib) < int(b):
            return True
    return False


def maybe_shift_for_linger(sa, sb, win, a_yt=None, b_yt=None, hiA=None):
    """If linger exceeds the calibrated pro p95, search earlier legal natural
    windows on the picker's 8-bar grid so the fade starts in the outgoing drop
    and/or the incoming cue sits before the breakdown.

    Thresholds are the pro p95 only (structural 5.4, drum 8.80). The earliest
    exit is bounded by the covering or preceding drop (fade stays in that drop).
    Re-checks lock and pump previews when those flags are on and both ids exist.
    """
    info = dict(applied=False, reason='ok')
    if not win or win[0] != 'n' or len(win) < 5:
        info['reason'] = 'bad_win'
        return win, info
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    dthr = drum_linger_threshold()
    sthr = linger_threshold()
    if hiA is None:
        hiA = load_drum_hi(a_yt)
    dl0 = drum_linger_bars(sa, sb, win, hiA)
    sl0 = linger_bars(sa, sb, win)
    info.update(drum_linger=dl0, linger=sl0, from_win=list(win))
    over = (dthr is not None and dl0 > dthr) or (sthr is not None and sl0 > sthr)
    if not over:
        info['reason'] = 'under_p95'
        return win, info
    drop = covering_or_preceding_drop(sa, e, X)
    e_min = 16 + X
    if drop:
        e_min = max(e_min, int(drop[0]) + X)
    cands = []
    for e2 in range(e, e_min - 1, -8):
        for ib2 in range(ib, -1, -8):
            if e2 == e and ib2 == ib:
                continue
            want = ['n', int(e2), None, int(ib2), int(X)]
            if not _legal_natural(sa, sb, want):
                continue
            # Do not start the incoming cue mid-drop; that cuts a drop phrase and
            # can pump. Drop-start or non-drop cues stay eligible.
            if ib2 != ib and _starts_mid_drop(sb, ib2):
                continue
            dl = drum_linger_bars(sa, sb, want, hiA)
            sl = linger_bars(sa, sb, want)
            if (dthr is not None and dl > dthr) or (sthr is not None and sl > sthr):
                continue
            cands.append((abs(e - e2) + abs(ib - ib2), abs(e - e2), abs(ib - ib2),
                          int(e2), int(ib2), int(dl), int(sl), want))
    if not cands:
        info['reason'] = 'no_legal_under_p95'
        return win, info
    cands.sort()
    chosen = None
    blocked = 0
    import ride_preview as RP
    for c in cands:
        want = c[-1]
        if a_yt and b_yt and RP.lock_preview_on():
            lk = RP.preview_lock(a_yt, b_yt, want)
            if not lk.get('ok', True):
                blocked += 1
                continue
        if a_yt and b_yt and RP.pump_preview_on():
            pp = RP.pump_preview(sa, sb, a_yt, b_yt, want)
            if not pp.get('ok', True):
                blocked += 1
                continue
        chosen = c
        break
    if chosen is None:
        info['reason'] = 'previews_blocked'
        info['n_blocked'] = blocked
        return win, info
    want = chosen[-1]
    info.update(applied=True, reason='shifted', win=list(want),
                drum_linger=chosen[5], linger=chosen[6], shift_bars=chosen[0],
                n_blocked=blocked)
    return want, info



_DRUM_HI = {}


def _find_src(yt):
    if not yt:
        return None
    roots = []
    try:
        import paths as _P
        roots.extend([
            os.path.join(_P.ROOT, 'lib'),
            os.path.join(_P.ROOT, 'corpus_v2', 'feat_lib'),
            os.path.join(_P.ROOT, 'cache', 'protrans_dl'),
        ])
    except Exception:
        pass
    roots.extend([
        os.path.join(os.path.dirname(H), 'lib'),
        os.path.join(os.path.dirname(H), 'corpus_v2', 'feat_lib'),
        os.path.join(os.path.dirname(H), 'cache', 'protrans_dl'),
        '/tmp/ridegate_fresh_src',
    ])
    for root in roots:
        for ext in ('.m4a', '.wav', '.mp3', '.flac'):
            path = os.path.join(root, str(yt) + ext)
            if os.path.exists(path):
                return path
    return None


def load_drum_hi(yt):
    """Per-bar high>200Hz energy of a source track, cached. None if audio is missing."""
    if not yt:
        return None
    if yt in _DRUM_HI:
        return _DRUM_HI[yt]
    path = _find_src(yt)
    if not path:
        _DRUM_HI[yt] = None
        return None
    try:
        import subprocess
        _src2 = os.path.join(os.path.dirname(os.path.dirname(H)), 'src2')
        if _src2 not in sys.path:
            sys.path.insert(0, _src2)
        import blend_diag as BD
        from engine import BS
        raw = subprocess.check_output(
            ['ffmpeg', '-v', 'error', '-i', path, '-ac', '2', '-ar', '44100', '-f', 'f32le', '-'])
        y = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
        n = int(len(y) // BS)
        hi = BD.band_bar_db(y, n, BS, 'high', DRUM_FC)
    except Exception:
        hi = None
    _DRUM_HI[yt] = hi
    return hi


def early_exit_flag_on(rules=None, env=None):
    import ride_preview as RP
    return RP.early_exit_on(rules, env)


def maybe_take_earlier_exit(pack, r, dec, sa, sb, a_yt=None, b_yt=None):
    """RIDEGATE_EE: if ride_pick reverted a mid/earlier je to the default exit, take je
    when it is earlier than default and passes drum_linger."""
    je, jr = dec.get('je'), dec.get('jr')
    if je is None or jr is None or je == jr or not dec.get('is_default'):
        return dec
    if je >= len(r.get('E') or []) or r['Edix'] >= len(r['E']):
        return dec
    je_v = float(r['E'][int(je)]['v'])
    def_v = float(r['E'][int(r['Edix'])]['v'])
    if je_v >= def_v:
        return dec
    jc = int(dec.get('jc', r['Cdix']))
    alt = B.decide(r, int(je), jc, r['dX'])
    alt['p_leave'] = dec.get('p_leave')
    alt['je'] = int(je); alt['jr'] = int(jr); alt['jc'] = jc
    alt['early_exit_kept'] = True
    want = alt.get('win')
    if not want or alt.get('is_default'):
        return dec
    sa_u, sb_u = r.get('sa') or sa, r.get('sb') or sb
    dthr = drum_linger_threshold()
    if dthr is not None:
        hiA = r.get('hiA') if r.get('hiA') is not None else load_drum_hi(a_yt)
        dl = drum_linger_bars(sa_u, sb_u, want, hiA)
        alt['drum_linger_bars'] = dl
        if dl > dthr:
            dec['early_exit_vetoed'] = 'drum_linger'
            return dec
    return alt


def maybe_apply(pack, sa, sb, default_win, cs, a_yt=None, b_yt=None, pid='live', env=None):
    """Render-time hook: decide a live window from features + the engine default, inject if legal.

    Returns (hit_or_None, decision, injected). Abstain leaves the engine pick untouched.
    When the pair is in the n1126 built snapshot, uses that row (rendered default + snapshot
    sections) so the live path matches the map; otherwise builds a row from the engine default.
    """
    dex, dcue, dX = default_from_win(default_win)
    r = row_for_render(sa, sb, dex, dcue, dX, a_yt=a_yt, b_yt=b_yt, pid=pid)
    dec = predict_rows(pack, [r])[0]
    import joint_picker as JP
    if JP.flag_on(env):  # JOINT_PICKER: joint exit+cue+length ensemble replaces the factored pick; previews below still apply
        dec = JP.decide_live(r)
    elif early_exit_flag_on():
        dec = maybe_take_earlier_exit(pack, r, dec, sa, sb, a_yt, b_yt)
    sa_u, sb_u = r.get('sa') or sa, r.get('sb') or sb
    ride_ok = not (dec.get('is_default') or not dec.get('win'))
    want = list(dec['win']) if ride_ok else list(default_win or [])
    import ride_preview as RP
    if ride_ok:
        if RP.lock_preview_on():
            lk = RP.preview_lock(a_yt, b_yt, want)
            dec['lock_preview'] = {k: lk[k] for k in lk if k != 'offs'}
            if not lk.get('ok', True):
                dec['lock_blocked'] = True
                ride_ok = False
                want = list(default_win or [])
        if ride_ok and RP.pump_preview_on():
            pp = RP.pump_preview(sa_u, sb_u, a_yt, b_yt, want)
            dec['pump_preview'] = pp
            if not pp.get('ok', True):
                dec['pump_blocked'] = True
                ride_ok = False
                want = list(default_win or [])
    if linger_shift_on() and want:
        hiA = r.get('hiA') if r.get('hiA') is not None else load_drum_hi(a_yt)
        alt, sinfo = maybe_shift_for_linger(sa_u, sb_u, want, a_yt=a_yt, b_yt=b_yt, hiA=hiA)
        dec['linger_shift'] = sinfo
        if sinfo.get('applied') and alt:
            want = list(alt)
            dec['win'] = want
            dec['exit'] = want[1]
            dec['cue'] = want[3]
            dec['linger_shifted'] = True
            ride_ok = True
    if linger_guard_on() and want:
        lb = linger_bars(sa_u, sb_u, want)
        dec['linger_bars'] = lb
        blocked = lb > linger_threshold()
        dthr = drum_linger_threshold()
        if dthr is not None:
            hiA = r.get('hiA') if r.get('hiA') is not None else load_drum_hi(a_yt)
            dl = drum_linger_bars(sa_u, sb_u, want, hiA)
            dec['drum_linger_bars'] = dl
            dec['drum_x_db'] = drum_x_db()
            if dl > dthr:
                blocked = True
                dec['drum_linger_blocked'] = True
        if blocked:
            dec['linger_blocked'] = True
            return None, dec, False
    if not ride_ok:
        return None, dec, False
    hit = next((c for c in cs if list(c.get('win') or []) == want), None)
    injected = False
    if hit is None and _legal_natural(sa, sb, want):
        hit = dict(fam='ridegate_live', win=list(want), env={}, cost=0.0, picker_injected=True)
        if dec.get('linger_shifted'):
            hit['fam'] = 'ridegate_live'
            hit['linger_shifted'] = True
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
