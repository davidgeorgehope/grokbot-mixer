#!/usr/bin/env python3
"""Flag-gated previews for a live ridegate window. Off by default. Do not write rules.json.

RIDEGATE_LOCK: reject a ride that is not lockable — a near-half-beat residual
on the proposed bars without enough drum-on-drum overlap for halfbeat /
finephase to resolve it. The drum-on-drum floor is the halfbeat code's 4-bar
requirement (pros who actually use the lock have p05=9.8 among dd>=4; using
that as a hard floor would veto passing windows with 5–9 overlap bars).

RIDEGATE_PUMP: reject a ride that lands in a quiet outgoing breakdown under a
thin incoming non-drop ('both thin'). Threshold is the pro p95 of the bar
count, with thinness T calibrated alongside it (T=6 dB, p95=10.80).

RIDEGATE_EE: on a ride (p_leave < theta) that ride_pick would revert to the
(often late) default exit, keep the model's earlier mid exit if it passes
drum_linger. Does not change fresh pairs whose ranked exit is already late.
"""
from __future__ import annotations
import json, math, os, subprocess
import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(H, 'ride_preview_cal.json')
LOCK_FLAG = 'RIDEGATE_LOCK'
PUMP_FLAG = 'RIDEGATE_PUMP'
EE_FLAG = 'RIDEGATE_EE'
HALFBEAT_MIN_DD = 4  # src2/halfbeat.py blend_check: < 4 drum-on-drum bars abstains
THIN_DB_DEFAULT = 6.0
# Near a half-beat at 174 BPM (172.4 ms); 30 ms slack covers 150–190 ms clusters.
HALFBEAT_LAG_SLACK_MS = 30.0
_CAL = None
_ST = {}
_AUDIO = {}


def _on(v):
    return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')


def _flag(name, rules=None, env=None):
    env = env or {}
    rules = rules or {}
    return _on((env or {}).get(name) or (rules or {}).get(name) or os.environ.get(name))


def lock_preview_on(rules=None, env=None):
    return _flag(LOCK_FLAG, rules, env)


def pump_preview_on(rules=None, env=None):
    return _flag(PUMP_FLAG, rules, env)


def early_exit_on(rules=None, env=None):
    return _flag(EE_FLAG, rules, env)


def load_cal():
    global _CAL
    if _CAL is not None:
        return _CAL
    if os.path.exists(CAL):
        _CAL = json.load(open(CAL))
    else:
        _CAL = dict(lock_min_dd=HALFBEAT_MIN_DD, thin_db=THIN_DB_DEFAULT, thin_p95=10.8,
                    thin_threshold=10.8)
    return _CAL


def lock_min_dd():
    return int(load_cal().get('lock_min_dd', HALFBEAT_MIN_DD))


def thin_db():
    return float(load_cal().get('thin_db', THIN_DB_DEFAULT))


def thin_threshold():
    cal = load_cal()
    return float(cal.get('thin_threshold', cal.get('thin_p95', 10.8)))


def _st_path(yt):
    if not yt:
        return None
    for root in (
        os.path.join(os.path.dirname(H), 'src2', 'st') if False else None,
        '/workspace/mixes/src2/st',
        os.path.join(os.path.dirname(H), '..', '..', 'src2', 'st'),
        'st',
    ):
        if not root:
            continue
        p = os.path.join(root, f'{yt}.json')
        if os.path.exists(p):
            return p
    # cwd-relative (recreate chdirs to SRC2)
    p = os.path.join('st', f'{yt}.json')
    return p if os.path.exists(p) else None


def load_st_bar(yt):
    if yt in _ST:
        return _ST[yt]
    path = _st_path(yt)
    if not path:
        _ST[yt] = None
        return None
    g = json.load(open(path))
    bar = g.get('bar') or {}
    _ST[yt] = dict(g=g, downs=np.array(g.get('downs') or [], float),
                   all=np.array(bar.get('all') or bar.get('drums') or [], float),
                   drums=np.array(bar.get('drums') or bar.get('all') or [], float))
    return _ST[yt]


def drums_on(yt):
    st = load_st_bar(yt)
    if st is None or len(st['drums']) == 0:
        return None
    dr = st['drums']
    return dr > np.percentile(dr, 75) - 8


def drum_on_drum_bars(a_yt, b_yt, out0, in0, X):
    dA, dB = drums_on(a_yt), drums_on(b_yt)
    if dA is None or dB is None:
        return None
    n = 0
    for j in range(int(round(float(X)))):
        oa = int(math.floor(float(out0) + j))
        ib = int(math.floor(float(in0) + j))
        if 0 <= oa < len(dA) and 0 <= ib < len(dB) and dA[oa] and dB[ib]:
            n += 1
    return n


def drop_baseline(arr, sec):
    idx = []
    n = len(arr)
    for lo, hi in (sec.get('drops') or []):
        idx.extend(range(max(0, int(lo)), min(n, int(hi))))
    return float(np.median(arr[idx])) if idx else None


def both_thin_bars(sa, sb, a_yt, b_yt, win, t_db=None):
    """Bars of a natural window where outgoing is in a breakdown, incoming is
    not in a drop, and both source tracks sit at least t_db below their drop median."""
    import ridegate_live as RG
    if not win or win[0] != 'n' or len(win) < 5:
        return 0
    stA, stB = load_st_bar(a_yt), load_st_bar(b_yt)
    if stA is None or stB is None or len(stA['all']) == 0 or len(stB['all']) == 0:
        return 0
    t_db = thin_db() if t_db is None else float(t_db)
    ba, bb = drop_baseline(stA['all'], sa), drop_baseline(stB['all'], sb)
    if ba is None or bb is None:
        return 0
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    n = 0
    for j in range(max(0, X)):
        oa, ibj = e - X + j, ib + j
        if oa < 0 or oa >= len(stA['all']) or ibj < 0 or ibj >= len(stB['all']):
            continue
        if (RG.in_breakdown(sa, oa) and (not RG.in_drop(sb, ibj))
                and (stA['all'][oa] - ba) <= -t_db and (stB['all'][ibj] - bb) <= -t_db):
            n += 1
    return n


def _near_halfbeat(lag_ms, beat_ms=344.82758620689657):
    if lag_ms is None or not np.isfinite(lag_ms):
        return False
    half = 0.5 * beat_ms
    return abs(abs(float(lag_ms)) - half) < HALFBEAT_LAG_SLACK_MS


def _find_src(yt):
    if not yt:
        return None
    for root in ('/tmp/ridegate_fresh_src',
                 os.path.join(os.path.dirname(H), 'cache', 'protrans_dl'),
                 os.path.join(os.path.dirname(H), 'lib'),
                 '/workspace/mixes/protrans/cache/protrans_dl',
                 '/workspace/mixes/protrans/lib'):
        for ext in ('.m4a', '.wav', '.mp3'):
            p = os.path.join(root, str(yt) + ext)
            if os.path.exists(p):
                return p
    return None


def _load_audio(yt):
    if yt in _AUDIO:
        return _AUDIO[yt]
    path = _find_src(yt)
    st = load_st_bar(yt)
    if not path or st is None:
        _AUDIO[yt] = None
        return None
    try:
        raw = subprocess.check_output(
            ['ffmpeg', '-v', 'error', '-i', path, '-ac', '2', '-ar', '44100', '-f', 'f32le', '-'])
        y = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
    except Exception:
        _AUDIO[yt] = None
        return None
    _AUDIO[yt] = dict(y=y, downs=st['downs'])
    return _AUDIO[yt]


def _bar_slice(tr, k, sr=44100):
    d, y = tr['downs'], tr['y']
    if k < 0 or k + 1 >= len(d):
        return None
    s, e = int(round(d[k] * sr)), int(round(d[k + 1] * sr))
    if s < 0 or e > len(y) or e <= s:
        return None
    return y[s:e]


def _resample(x, n):
    if len(x) == n:
        return x
    t = np.linspace(0, 1, len(x))
    t2 = np.linspace(0, 1, n)
    return np.stack([np.interp(t2, t, x[:, c]) for c in range(x.shape[1])], 1).astype(np.float32)


def preview_lock(a_yt, b_yt, win):
    """Return {ok, reason, lag_ms, dd, n_use, ...}. ok=True if the ride is lockable
    or if we cannot measure (missing audio/st): never block on a missing preview."""
    import fade_long as FL
    import finephase as FP
    from engine import BS, BEAT
    info = dict(ok=True, reason=None, lag_ms=None, dd=None, n_use=0)
    if not win or win[0] != 'n' or len(win) < 5:
        return info
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    out0 = e - X
    dd = drum_on_drum_bars(a_yt, b_yt, out0, ib, X)
    info['dd'] = dd
    A, B = _load_audio(a_yt), _load_audio(b_yt)
    if A is None or B is None:
        return info
    bs = int(round(BS))
    chunksA, chunksB, evA, evB, gmin = [], [], [], [], []
    for j in range(max(0, X)):
        sa, sb = _bar_slice(A, out0 + j), _bar_slice(B, ib + j)
        if sa is None or sb is None:
            continue
        sa, sb = _resample(sa, bs), _resample(sb, bs)
        x = FL.xlong((j + 0.5) / X, X)
        gA, gB = math.cos(math.pi / 2 * x), math.sin(math.pi / 2 * x)
        fa, fb = sa * gA, sb * gB
        evA.append(10 * np.log10(np.mean(fa ** 2) + 1e-12))
        evB.append(10 * np.log10(np.mean(fb ** 2) + 1e-12))
        gmin.append(min(gA, gB))
        chunksA.append(fa)
        chunksB.append(fb)
    if len(chunksA) < 2:
        return info
    yA = np.concatenate(chunksA)
    yB = np.concatenate(chunksB)
    # Measure only the mid-blend shelf: both faded decks audible (>-35 dB) and
    # both faders substantially up. Edge bars of an xlong fade dilute the
    # official confident cluster (source |d|<6 also drops __09's 154-159 bars,
    # which sit 6-10 dB apart on the sources but were loud on the rendered decks).
    mid = [k for k in range(len(evA)) if evA[k] > -35 and evB[k] > -35 and gmin[k] >= 0.45]
    use = mid if len(mid) >= 2 else [k for k in range(len(evA)) if evA[k] > -35 and evB[k] > -35]
    if len(use) < 2:
        use = list(range(len(evA)))
    run = FP.longest_run(use)
    if len(run) >= 2:
        use = run
    lag, offs = FP.loud_lag_ms(yA, yB, list(range(len(evA))), bs, BEAT, use)
    # Official lock / hardcheck only act on a confident cluster (finephase.confident_lag).
    # robust_lag of a messy set invented half-beat residuals on passing rides (__06/__11/__14)
    # whose official measure_blend_lag was None.
    used = lag
    info.update(lag_ms=None if used is None else round(float(used), 1),
                n_use=len(use), offs=offs)
    # Official lock_decks leaves the residual to halfbeat only when |lag| > LOCK_MAX_MS (150).
    # A 149 ms cluster is still a finephase lock, not an un-lockable half-beat.
    near = bool(used is not None and np.isfinite(used) and abs(float(used)) > FP.LOCK_MAX_MS)
    info['near_halfbeat'] = bool(near)
    need = lock_min_dd()
    if near and (dd is not None) and dd < need:
        info['ok'] = False
        info['reason'] = f'near-half-beat lag {info["lag_ms"]} ms with {dd} drum-on-drum bars (< {need})'
    return info


def pump_preview(sa, sb, a_yt, b_yt, win):
    """Both-thin gate. ok=False when both_thin_bars > pro p95."""
    n = both_thin_bars(sa, sb, a_yt, b_yt, win)
    thr = thin_threshold()
    ok = not (n > thr)
    return dict(ok=ok, both_thin=n, thin_db=thin_db(), threshold=thr,
                reason=None if ok else f'both_thin {n} > pro p95 {thr:.2f}')
