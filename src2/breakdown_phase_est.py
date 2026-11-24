"""BREAKDOWN_PHASE_EST (2026-11-23 RCA, research, off by default).

When the outgoing overlap is a post-drop half-time breakdown, official
kick+snare xcorr hops toward a half-beat even when the records are locked
the way a pro mixed them (S.P.Y breakdown kicks sit off a correct
drop-locked grid; snares stay near it). This module measures alignment
from isolated snares and/or on-beat-only kick lags instead.

Activation (outgoing deck only):
  * a known half-time section overlaps the outgoing source bars of the
    blend, and that overlap sits at or after drop 1 / a listed breakdown,
    or
  * the kick-on-1 / snare-on-2-and-4 template on those outgoing bars
    prefers a half-beat shift by the existing HALFBEAT_MARGIN (0.5).

The pass line is the existing 40 ms official median. Changing the
estimator is not loosening that line. Does not write rules.json or
change defaults. Flag off: unused.
"""
from __future__ import annotations
import json, os, sys
import numpy as np

PASS_MS = 40.0          # existing blend_diag / listen-clip line; not loosened
MIN_CONF = 3            # bars needed before a family is usable
KICK_OK_MS = 40.0       # a kick farther than the pass line is not on-beat
KICK_WIN_MS = 80.0      # search, inside a half-beat at 174
PROM = 1.8
HOP = 64
SNARE_BAND = (1500, 5000)
KICK_BAND = (30, 150)


def flag_on(val=None):
    v = os.environ.get('BREAKDOWN_PHASE_EST', '0') if val is None else val
    if v is None:
        return False
    return str(v).strip().lower() not in ('', '0', 'false', 'off', 'no')


def _src2():
    return os.path.dirname(os.path.abspath(__file__))


def _mono(y):
    y = np.asarray(y, float)
    return y.mean(1) if y.ndim > 1 else y


def _flux(y, lo, hi, sr, hop=HOP):
    from scipy.signal import butter, sosfiltfilt
    m = _mono(y)
    sos = butter(4, [lo, hi], 'band', fs=sr, output='sos')
    z = sosfiltfilt(sos, m)
    n = len(z) // hop
    if n < 4:
        return np.zeros(1)
    e = np.sqrt((z[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    return np.maximum(np.diff(e, prepend=e[:1]), 0.0)


def _xcorr_lags(ea, eb, bars, bs, beat, sr, hop=HOP, win_bars=1, prefer_interior=True):
    """Signed lag (ms, + = A late), one entry per crop bar. NaN if unusable."""
    fr = sr / hop
    L = int(beat / 2 * fr)
    half_ms = beat / 2 * 1000
    out = []
    for k in bars:
        i0, i1 = int(k * bs / hop), int((k + win_bars) * bs / hop)
        x, y = ea[i0:i1] - ea[i0:i1].mean(), eb[i0:i1] - eb[i0:i1].mean()
        n = min(len(x), len(y))
        if n < 4 * L:
            out.append(np.nan)
            continue
        x, y = x[:n], y[:n]
        xc = np.array([np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)])
                       for j in range(-L, L + 1)])
        i = int(np.argmax(xc))
        lag = (i - L) * 1000 / fr
        peak = float(xc[i]) or 1e-12
        if prefer_interior and abs(lag) >= 0.4 * half_ms * 2:
            best, best_abs = i, abs(lag)
            for j, v in enumerate(xc):
                if v / peak < 0.75:
                    continue
                ms = (j - L) * 1000 / fr
                if abs(ms) <= PASS_MS and abs(ms) < best_abs:
                    best, best_abs = j, abs(ms)
            i = best
            lag = (i - L) * 1000 / fr
        out.append(float(lag))
    return np.array(out, float)


def _onbeat_one(env, bar_in_crop, bs, sr, win_ms=KICK_WIN_MS):
    fr = sr / HOP
    mid = bar_in_crop * bs / HOP
    rad = win_ms / 1000.0 * fr
    i0, i1 = int(round(mid - rad)), int(round(mid + rad)) + 1
    if i0 < 0 or i1 > len(env) or i1 - i0 < 4:
        return None
    w = env[i0:i1]
    med = float(np.median(w))
    peak = float(w.max())
    if peak < 1e-9 or (med > 0 and peak < PROM * med):
        return None
    j = int(np.argmax(w))
    if j <= 1 or j >= len(w) - 2:
        return None
    if 0 < j < len(w) - 1:
        a, b, c = float(w[j - 1]), float(w[j]), float(w[j + 1])
        den = a - 2 * b + c
        if den != 0:
            j = j + 0.5 * (a - c) / den
    ms = (i0 + j - mid) * 1000.0 / fr
    if abs(ms) > win_ms:
        return None
    return float(ms)


def loud_bars(yA, yB, s0, start, end, bs, pre=8):
    """0-based crop indices where both decks are within 20 dB of the clip ref (blend_diag)."""
    def bar_db(y, k):
        a, b = int(k * bs), int((k + 1) * bs)
        a = max(0, a); b = min(len(y), b)
        if b <= a:
            return -120.0
        m = y[a:b]
        if m.ndim > 1:
            m = m.mean(1)
        return float(20 * np.log10(np.sqrt(np.mean(m ** 2) + 1e-18)))
    n = int(np.floor(min(len(yA), len(yB)) / bs))
    allA = [bar_db(yA, k) for k in range(n)]
    allB = [bar_db(yB, k) for k in range(n)]
    pre_n = max(1, min(int(pre), n))
    post_n = max(1, min(int(pre), n))
    ref = max(float(np.median(allA[:pre_n])), float(np.median(allB[-post_n:])))
    out = []
    for mb in range(int(start), int(end)):
        k = int(mb - s0)
        if 0 <= k < n and allA[k] > ref - 20 and allB[k] > ref - 20:
            out.append(k)
    return out, ref


def _sections(tid):
    here = _src2()
    sys.path.insert(0, here)
    sys.path.insert(0, os.path.join(here, '..', 'protrans', 'replica', 'halftime'))
    try:
        import sections as S
        return S.get(tid) or {}
    except Exception:
        return {}


def _halftime_sections(tid):
    here = _src2()
    sys.path.insert(0, os.path.join(here, '..', 'protrans', 'replica', 'halftime'))
    try:
        import slowdown as SD
        P = SD.profile(tid) or {}
        return list(P.get('sections') or [])
    except Exception:
        return []


def outgoing_is_breakdown_ht(a_id, src_bars, secs=None, ht_sections=None, g=None, wav=None):
    """True when the outgoing overlap is a post-drop half-time breakdown.

    Returns (active, reason_dict).
    """
    src_bars = [int(b) for b in src_bars if b is not None]
    info = dict(a_id=a_id, n_src=len(src_bars),
                src_span=[src_bars[0], src_bars[-1]] if src_bars else None)
    if len(src_bars) < 4:
        return False, dict(info, why='too few outgoing bars')
    secs = secs if secs is not None else _sections(a_id)
    ht_sections = ht_sections if ht_sections is not None else _halftime_sections(a_id)
    drop1 = secs.get('drop1')
    breakdown = secs.get('breakdown')
    post_from = None
    if breakdown is not None:
        post_from = int(breakdown)
    elif drop1 is not None:
        post_from = int(drop1)
    info['drop1'] = drop1
    info['breakdown'] = breakdown
    info['ht_sections'] = [[int(x), int(y)] for x, y in ht_sections]
    post = [b for b in src_bars if post_from is None or b >= post_from]
    if post_from is not None and len(post) < 4:
        return False, dict(info, why='outgoing overlap is not post-drop / post-breakdown', post_from=post_from)
    hit = None
    for x, y in ht_sections:
        if any(x <= b < y for b in (post or src_bars)):
            hit = [int(x), int(y)]
            break
    if hit is not None:
        info.update(why='known half-time section overlaps post-drop outgoing bars', ht_hit=hit, active=True)
        return True, info
    # section-local half-beat template on the outgoing overlap (existing margin 0.5)
    margin = local_halfbeat_margin(a_id, post or src_bars, g=g, wav=wav)
    info['local_margin'] = None if margin is None else round(float(margin), 3)
    import halfbeat as HB
    if margin is not None and margin >= HB.MARGIN:
        info.update(why='section-local half-beat margin >= HALFBEAT_MARGIN', active=True)
        return True, info
    info.update(why='outgoing overlap is not a post-drop half-time breakdown', active=False)
    return False, info


def local_halfbeat_margin(tid, src_bars, g=None, wav=None):
    """kick/snare template margin (half - whole) on the given source bars, or None."""
    src_bars = [int(b) for b in src_bars]
    if len(src_bars) < 4:
        return None
    here = _src2()
    cwd = os.getcwd()
    try:
        os.chdir(here)
        import halfbeat as HB
        if g is None:
            path = f'st/{tid}.json'
            if not os.path.exists(path):
                return None
            g = json.load(open(path))
        downs = np.array(g['downs'], float)
        mask = np.zeros(len(downs), bool)
        for b in src_bars:
            if 0 <= b < len(downs):
                mask[b] = True
        if mask.sum() < 4:
            return None
        if wav is None:
            import soundfile as sf
            wp = f'st/{tid}.wav'
            if not os.path.exists(wp):
                return None
            y, sr = sf.read(wp, dtype='float32', always_2d=True)
            wav = y.mean(1)
            if sr != HB.SR:
                return None
        K, S = HB.drum_envs(wav)
        fK, n = HB.fold(K, downs, mask)
        fS, _ = HB.fold(S, downs, mask)
        if n < 4:
            return None
        ph = HB.phase_from_folds(fK, fS)
        return float(ph['margin'])
    except Exception:
        return None
    finally:
        os.chdir(cwd)


def measure(yA, yB, s0, start, end, bs, sr, beat, loud=None, force=False,
            a_id=None, src_bars=None, secs=None, ht_sections=None):
    """Deck-to-deck alignment on a cropped overlap.

    If the flag is off and force is false, returns official-style kick+snare
    median (does not activate). If the flag is on (or force) and the outgoing
    overlap is a post-drop half-time breakdown (or force), uses isolated
    snares and on-beat-only kicks.

    Returns a dict with median_ms, pass_ms, ok, active, family, rows, reason.
    """
    import halfbeat as HB
    beat = float(beat if beat is not None else HB.BEAT)
    start, end, s0 = int(start), int(end), int(s0)
    crop_all = list(range(int(start - s0), int(end - s0)))
    if loud is None:
        loud, ref = loud_bars(yA, yB, s0, start, end, bs)
    else:
        ref = None
    bars = loud if loud else crop_all

    def official():
        import blend_diag as D
        offs = D.bar_offsets(yA, yB, bars, bs, beat, hop=HOP, sr=sr, win_bars=2)
        med = None if not np.isfinite(offs).any() else float(np.nanmedian(offs))
        return dict(
            active=False, family='kick+snare', official=True,
            median_ms=None if med is None else round(med, 1),
            n=int(np.isfinite(offs).sum()),
            pass_ms=PASS_MS,
            ok=bool(med is not None and abs(med) <= PASS_MS),
            usable=bool(med is not None),
            bars=[s0 + k for k in bars],
            values=[None if not np.isfinite(v) else round(float(v), 1) for v in offs],
            ref=ref,
        )

    use = bool(force or flag_on())
    reason = dict(forced=bool(force), flag=flag_on())
    if use and a_id is not None and src_bars is not None and not force:
        active, rec = outgoing_is_breakdown_ht(a_id, src_bars, secs=secs, ht_sections=ht_sections)
        reason.update(rec)
        if not active:
            out = official()
            out['reason'] = reason
            out['why'] = rec.get('why')
            return out
    elif use and not force and (a_id is None or src_bars is None):
        # flag on but no structure given: do not silently switch
        out = official()
        out['reason'] = dict(reason, why='no outgoing structure; left official kick+snare')
        return out
    elif not use:
        out = official()
        out['reason'] = dict(reason, why='flag off')
        return out
    else:
        reason['why'] = 'forced'
        reason['active'] = True

    sa = _flux(yA, *SNARE_BAND, sr)
    sb = _flux(yB, *SNARE_BAND, sr)
    sn = _xcorr_lags(sa, sb, bars, bs, beat, sr, win_bars=1, prefer_interior=True)
    ka = _flux(yA, *KICK_BAND, sr)
    kb = _flux(yB, *KICK_BAND, sr)
    kick_rows = []
    for k in bars:
        a = _onbeat_one(ka, k, bs, sr)
        b = _onbeat_one(kb, k, bs, sr)
        have = a is not None and b is not None
        on = have and abs(a) <= KICK_OK_MS and abs(b) <= KICK_OK_MS
        kick_rows.append(dict(mix_bar=s0 + k,
                              a_ms=None if a is None else round(a, 1),
                              b_ms=None if b is None else round(b, 1),
                              residual_ms=None if not have else round(a - b, 1),
                              conf=bool(on)))
    # prefer_interior already takes a strong in-±40 ms peak when the argmax
    # hops to the edge. Remaining near-half lags are a real half-beat wreck
    # and must be kept so known trainwrecks still fail.
    sn_keep = [float(v) for v in sn if np.isfinite(v)]
    kick_keep = [r['residual_ms'] for r in kick_rows if r['conf']]

    family, used = None, []
    if len(sn_keep) >= MIN_CONF and len(kick_keep) >= MIN_CONF:
        family, used = 'snare+onbeat_kick', sn_keep + kick_keep
    elif len(sn_keep) >= MIN_CONF:
        family, used = 'snare', sn_keep
    elif len(kick_keep) >= MIN_CONF:
        family, used = 'onbeat_kick', kick_keep
    else:
        family, used = 'insufficient', []

    med = None if not used else float(np.median(used))
    ok = bool(used and abs(med) <= PASS_MS)
    return dict(
        active=True, official=False, family=family,
        median_ms=None if med is None else round(med, 1),
        n=len(used), n_snare=len(sn_keep), n_kick=len(kick_keep),
        pass_ms=PASS_MS, ok=ok, usable=bool(used),
        bars=[s0 + k for k in bars],
        snare_ms=[round(v, 1) for v in sn_keep],
        snare_raw=[None if not np.isfinite(v) else round(float(v), 1) for v in sn],
        kick_rows=kick_rows,
        kick_ms=[round(v, 1) for v in kick_keep],
        used_ms=[round(v, 1) for v in used],
        reason=reason, ref=ref,
    )


def outgoing_src_bars(M, i=0):
    """Source bars of the outgoing deck across trans[i]."""
    t = M['trans'][i]
    A = M['decks'][i]
    s, e = int(t['start_bar']), int(t['end_bar'])
    out = []
    for k in range(s, e):
        j = k - int(A['start_bar'])
        fm = A.get('full_map') or A.get('map') or []
        if 0 <= j < len(fm) and fm[j][1] == 'mix':
            out.append(int(fm[j][0]))
    return A['id'], out


def measure_meta(M, yA, yB, s0, i=0, force=False):
    t = M['trans'][i]
    a_id, src = outgoing_src_bars(M, i)
    import engine as E
    return measure(yA, yB, s0, t['start_bar'], t['end_bar'], E.BS, E.SR, E.BEAT,
                   a_id=a_id, src_bars=src, force=force)
