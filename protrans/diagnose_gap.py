#!/usr/bin/env python3
"""Diagnose why recreations score low vs pro transitions.

Does not change engine rules. Writes results/gap_diagnosis.json and .md.
Scratch oracle wavs live under /tmp/protrans_gap and are deleted at the end.
"""
from __future__ import annotations
import json, os, sys, shutil, tempfile, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, score, version_match, structure as ST

SR = score.SR
HOP = score.HOP
BAR_SEC = score.BAR_SEC
LIB = paths.LIB
SCRATCH = '/tmp/protrans_gap'
CKPT = os.path.join(paths.RESULTS, 'gap_diagnosis_ckpt.json')
OUT_JSON = os.path.join(paths.RESULTS, 'gap_diagnosis.json')
OUT_MD = os.path.join(paths.RESULTS, 'gap_diagnosis.md')
BASE = os.path.join(paths.RESULTS, 'baseline_clean.json')
ADMITTED = os.path.join(paths.RESULTS, 'admitted.json')
TALKOVER = os.path.join(paths.RESULTS, 'talkover.json')

# Feature thresholds (documented, applied after measurement)
SOLO_CORR_BAD = 0.42
SOLO_UNEX_BAD = 0.28
RATE_MIN = 0.012          # ~2% / ~0.2 semitone
RATE_IMPROVE = 0.06
UNEX_EXTRA = 0.25
ORACLE_TECH_GAP = 20.0
ORACLE_LOW = 50.0
UNEX_CLEAN = 0.15


def _load(path, sr=SR, t0=None, dur=None):
    return version_match._load(path, sr=sr, t0=t0, dur=dur)


def _clip_path(row):
    p = row.get('pro_clip')
    if p and os.path.exists(p):
        return p
    return os.path.join(paths.CLIPS, row['split'], row['id'], 'pro.wav')


def _src_path(yt):
    return os.path.join(LIB, f'{yt}.m4a')


def _norm_corr(a, b):
    n = min(len(a), len(b))
    if n < int(0.4 * SR):
        return 0.0
    a = np.asarray(a[:n], float); b = np.asarray(b[:n], float)
    a = a - a.mean(); b = b - b.mean()
    da = np.linalg.norm(a); db = np.linalg.norm(b)
    if da < 1e-9 or db < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (da * db))


def _env_corr(a, b):
    ea = score._rms(a); eb = score._rms(b)
    return _norm_corr(ea.astype(float), eb.astype(float)) if min(len(ea), len(eb)) > 4 else 0.0


def _butter(y, kind, fc):
    return score._butter(y, kind, fc, sr=SR)


def split_bands(y):
    """Complementary split so bass+mids+highs reconstructs y."""
    bass = _butter(y, 'low', 150)
    high = _butter(y, 'high', 4000)
    mid = y - bass - high
    return dict(bass=bass, mids=mid, highs=high)


def _smooth(x, k=5):
    x = np.nan_to_num(np.asarray(x, float), nan=0.0, posinf=0.0, neginf=0.0)
    if len(x) < k:
        return x
    k = k if k % 2 else k + 1
    pad = k // 2
    return np.convolve(np.pad(x, (pad, pad), mode='edge'), np.ones(k) / k, mode='valid')


def resample_rate(y, rate):
    if abs(rate - 1.0) < 1e-4:
        return y
    n = max(8, int(round(len(y) / max(rate, 1e-6))))
    x = np.linspace(0, 1, len(y))
    return np.interp(np.linspace(0, 1, n), x, y).astype(np.float32)


def place_source(src, track_t, mix_t, n_pro, rate=1.0, extra=40.0):
    """Map native source onto the pro clip timeline.

    locate says source[track_t] matches pro[mix_t]. src_t0 is the source
    time that belongs at clip t=0. `rate` > 1 means the source runs fast
    vs the mix (needs to be slowed to line up).
    """
    src_t0 = float(track_t) - float(mix_t) * rate
    # load a padded slice then resample and crop
    pad = extra
    t_load = src_t0 - pad
    lead = 0.0
    if t_load < 0:
        lead = -t_load
        t_load = 0.0
    dur = (n_pro / SR) * rate + pad + extra + lead
    sl = _load(src, t0=t_load, dur=dur) if True else np.zeros(0)
    if rate != 1.0:
        sl = resample_rate(sl, rate)
    # after resample, 1 source-second = 1 mix-second
    # we loaded from t_load, wanted from src_t0 - pad
    # starting sample of clip t=0 in `sl`:
    #   (src_t0 - t_load) / rate  seconds into sl, but sl is already resampled
    # resampled sl starts at t_load (native) which is t_load/rate mix-seconds? 
    # resample_rate(y, rate) shortens when rate>1: output duration = input_dur/rate
    # native slice [t_load, t_load+dur) becomes mix-time duration dur/rate
    # mix-time of sl[0] = t_load / rate  in "source mix-aligned time"
    # we want sample at source native time src_t0, which after resample is at
    # (src_t0 - t_load) / rate seconds into sl
    off_s = (src_t0 - t_load) / max(rate, 1e-9)
    i0 = int(round(off_s * SR))
    if i0 < 0:
        out = np.concatenate([np.zeros(-i0, np.float32), sl])[:n_pro]
    else:
        out = sl[i0:i0 + n_pro]
    if len(out) < n_pro:
        out = np.pad(out, (0, n_pro - len(out)))
    return out.astype(np.float32)


def refine_lag(pro, src, max_s=1.25):
    """Shift src (positive = src delayed) to max kick-env xcorr vs pro."""
    if len(src) < 8 or len(pro) < 8:
        return src, 0
    hop = 256
    ep = score._kick_env(pro, hop, SR)
    eo = score._kick_env(src, hop, SR)
    ep = ep - ep.mean(); eo = eo - eo.mean()
    max_lag = min(int(max_s * SR / hop), max(len(ep), len(eo)) - 2)
    if max_lag < 4:
        return src, 0
    nfft = 1 << int(np.ceil(np.log2(len(ep) + len(eo))))
    cc = np.fft.irfft(np.fft.rfft(ep, nfft) * np.conj(np.fft.rfft(eo, nfft)), nfft)
    vals = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
    lags = np.arange(-max_lag, max_lag + 1)
    i = int(np.argmax(vals))
    lag = int(lags[i]) * hop
    if lag > 0:
        out = np.concatenate([np.zeros(lag, np.float32), src])[:len(pro)]
    elif lag < 0:
        out = src[-lag:]
        if len(out) < len(pro):
            out = np.pad(out, (0, len(pro) - len(out)))
        else:
            out = out[:len(pro)]
    else:
        out = src[:len(pro)]
        if len(out) < len(pro):
            out = np.pad(out, (0, len(pro) - len(out)))
    return out.astype(np.float32), lag


def spec_unexplained(pro, a, b, win_s=1.0, hop_s=0.5):
    """Phase-invariant unexplained energy: NNLS of STFT mags over short windows."""
    from scipy.signal import stft
    from scipy.optimize import nnls
    n = min(len(pro), len(a), len(b))
    nper = 2048
    _, _, P = stft(pro[:n], SR, nperseg=nper, noverlap=nper - 512, boundary=None, padded=False)
    _, _, A = stft(a[:n], SR, nperseg=nper, noverlap=nper - 512, boundary=None, padded=False)
    _, _, B = stft(b[:n], SR, nperseg=nper, noverlap=nper - 512, boundary=None, padded=False)
    P, A, B = np.abs(P), np.abs(A), np.abs(B)
    # drop very low bins (DC rumble)
    P, A, B = P[2:], A[2:], B[2:]
    T = P.shape[1]
    dt = 512 / SR
    W = max(4, int(round(win_s / dt)))
    Hs = max(1, int(round(hop_s / dt)))
    share = np.zeros(T)
    gA = np.zeros(T); gB = np.zeros(T)
    eP = (P ** 2).sum(0)
    for s in range(0, T, Hs):
        sl = slice(s, min(T, s + W))
        p = P[:, sl]
        if p.shape[1] < 3:
            continue
        X = np.stack([A[:, sl].ravel(), B[:, sl].ravel()], 1)
        try:
            g, _ = nnls(X, p.ravel())
        except Exception:
            g = np.array([0.5, 0.5])
        fit = g[0] * A[:, sl] + g[1] * B[:, sl]
        res = np.maximum(p - fit, 0)
        sh = (res ** 2).sum(0) / ((p ** 2).sum(0) + 1e-12)
        share[sl] = sh
        gA[sl] = g[0]; gB[sl] = g[1]
    # time axis
    t = np.arange(T) * dt
    # ignore near-silent frames
    active = eP > np.percentile(eP, 20)
    overall = float(share[active].mean()) if active.any() else float(share.mean())
    return dict(share=share, gA=gA, gB=gB, t=t, overall=overall, eP=eP, dt=dt, active=active)


def region_mean(share, t, t0, t1, active=None):
    m = (t >= t0) & (t < t1)
    if active is not None:
        m &= active
    if not np.any(m):
        return None
    return float(share[m].mean())


def spec_corr(x, y):
    """Normalized correlation of STFT magnitudes (version similarity)."""
    from scipy.signal import stft
    n = min(len(x), len(y))
    if n < int(0.5 * SR):
        return 0.0
    _, _, X = stft(x[:n], SR, nperseg=2048, noverlap=2048 - 512, boundary=None, padded=False)
    _, _, Y = stft(y[:n], SR, nperseg=2048, noverlap=2048 - 512, boundary=None, padded=False)
    X, Y = np.abs(X[2:]), np.abs(Y[2:])
    # energy-weight frames
    w = (X ** 2).sum(0)
    w = w / (w.sum() + 1e-12)
    xn = X / (np.linalg.norm(X, axis=0, keepdims=True) + 1e-12)
    yn = Y / (np.linalg.norm(Y, axis=0, keepdims=True) + 1e-12)
    c = (xn * yn).sum(0)
    return float(np.clip((c * w).sum(), -1, 1))


def search_rate(pro, src_path, track_t, mix_t, n_pro, region, rates=None):
    """Find a playback rate that maximises spectral corr of src vs pro in region."""
    if rates is None:
        # CDJ-style (tempo+pitch together): about -3% .. +3% plus semitone-ish points
        rates = [0.980, 0.990, 0.994, 1.000, 1.006, 1.010, 1.020]
    t0, t1 = region
    i0, i1 = int(t0 * SR), int(t1 * SR)
    target = pro[i0:i1]
    if len(target) < int(1.5 * SR):
        return 1.0, 0.0, 0.0
    best_r, best_c, c0 = 1.0, -1.0, 0.0
    for r in rates:
        placed = place_source(src_path, track_t, mix_t, n_pro, rate=r, extra=8.0)
        placed, lag = refine_lag(pro, placed, max_s=0.6)
        # a rate that only "wins" after a large extra shift is a false lock
        if abs(lag) > int(0.18 * SR) and abs(r - 1.0) > 1e-6:
            continue
        c = spec_corr(target, placed[i0:i1])
        if abs(r - 1.0) < 1e-6:
            c0 = c
        if c > best_c:
            best_c, best_r = c, r
    return best_r, float(best_c), float(c0)


def band_gains(pro, a, b, hop_s=0.25):
    """Per-band amplitude gains via NNLS on frame spectra. Returns curves + reconstruction.

    Waveform NNLS is unstable when the sources are slightly off-grid (gains go
    infinite / NaN). Fitting non-negative STFT magnitudes is what a fader can
    actually do: scale each source, never invent phase cancellation.
    """
    from scipy.optimize import nnls
    pb, ab, bb = split_bands(pro), split_bands(a), split_bands(b)
    hop = max(64, int(hop_s * SR))
    n = min(len(pro), len(a), len(b))
    n_fr = n // hop
    win = np.hanning(hop).astype(float)
    gains = {k: {'a': np.zeros(n_fr), 'b': np.zeros(n_fr)} for k in list(pb) + ['all']}
    rec = np.zeros(n, np.float32)

    def fit(pv, av, bv):
        if pv.size < 16:
            return np.array([0.0, 0.0])
        P = np.abs(np.fft.rfft(pv * win[:len(pv)]))
        A = np.abs(np.fft.rfft(av * win[:len(av)]))
        B = np.abs(np.fft.rfft(bv * win[:len(bv)]))
        if float(P.sum()) < 1e-10:
            return np.array([0.0, 0.0])
        X = np.stack([A, B], 1)
        try:
            g, _ = nnls(X, P)
        except Exception:
            return np.array([0.0, 0.0])
        return np.clip(np.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0), 0.0, 3.0)

    tmp = {k: {'a': np.zeros(n_fr), 'b': np.zeros(n_fr)} for k in pb}
    for i in range(n_fr):
        sl = slice(i * hop, (i + 1) * hop)
        for k in pb:
            g = fit(pb[k][sl], ab[k][sl], bb[k][sl])
            tmp[k]['a'][i], tmp[k]['b'][i] = g[0], g[1]
        g = fit(pro[sl], a[sl], b[sl])
        gains['all']['a'][i], gains['all']['b'][i] = g[0], g[1]
    for k in list(pb) + ['all']:
        src = tmp[k] if k in tmp else gains['all']
        gains[k]['a'] = _smooth(src['a'] if k in tmp else gains['all']['a'])
        gains[k]['b'] = _smooth(src['b'] if k in tmp else gains['all']['b'])
    # rebuild sample-accurate reconstruction from smoothed per-band gains
    tt = (np.arange(n_fr) + 0.5) * hop / SR
    ts = np.arange(n) / SR
    for k in pb:
        ga = np.interp(ts, tt, gains[k]['a'], left=gains[k]['a'][0], right=gains[k]['a'][-1])
        gb = np.interp(ts, tt, gains[k]['b'], left=gains[k]['b'][0], right=gains[k]['b'][-1])
        rec += (ga * ab[k][:n] + gb * bb[k][:n]).astype(np.float32)
    rec = np.nan_to_num(rec, nan=0.0, posinf=0.0, neginf=0.0)
    return gains, rec, tt, hop


def classify_fader(g_out, t, blend, bar_sec=BAR_SEC):
    """Infer outgoing fader shape over the blend window."""
    t0, t1 = blend
    m = (t >= t0) & (t <= t1)
    if m.sum() < 4:
        return dict(shape='unknown', drop_bars=None, eq_swap_bars=None)
    x = np.linspace(0, 1, int(m.sum()))
    y = np.asarray(g_out[m], float)
    y = np.clip(y, 0, None)
    if y.max() > 1e-6:
        y = y / (np.percentile(y, 90) + 1e-9)
    y = np.clip(y, 0, 1.2)
    # 80-20 drop width
    try:
        i80 = next(i for i, v in enumerate(y) if v < 0.8)
        i20 = next(i for i, v in enumerate(y) if v < 0.2)
        drop_s = (i20 - i80) / max(len(y) - 1, 1) * (t1 - t0)
        drop_bars = drop_s / bar_sec
    except StopIteration:
        drop_bars = None
    models = {
        'linear': 1 - x,
        'equal_power': np.cos(np.pi / 2 * x),
        'curve': (1 - x) ** 2,
    }
    # cut: high then sudden drop near the end
    cut = np.ones_like(x)
    cut[int(0.75 * len(x)):] = np.linspace(1, 0, len(x) - int(0.75 * len(x)))
    models['cut'] = cut
    best, best_mse = 'linear', 1e9
    for name, pred in models.items():
        mse = float(np.mean((y[:len(pred)] - pred) ** 2))
        if mse < best_mse:
            best, best_mse = name, mse
    if drop_bars is not None and drop_bars < 2.0 and (y[: max(1, len(y)//2)].mean() > 0.7):
        best = 'cut'
    return dict(shape=best, drop_bars=None if drop_bars is None else round(float(drop_bars), 2),
                mse=round(best_mse, 4))


def half_cross(g, t, side='out'):
    """Time when outgoing drops below 0.5 of early level / incoming rises above 0.5 of late."""
    g = np.asarray(g, float)
    if side == 'out':
        ref = np.percentile(g[: max(2, len(g)//6)], 75) if len(g) else 0
        thr = 0.5 * max(ref, 1e-6)
        for i, v in enumerate(g):
            if t[i] < 4:
                continue
            if v < thr:
                return float(t[i])
        return None
    ref = np.percentile(g[int(len(g)*0.7):], 75) if len(g) else 0
    thr = 0.5 * max(ref, 1e-6)
    for i, v in enumerate(g):
        if v > thr and t[i] > 6:
            return float(t[i])
    return None


def detect_loop(pro, src_path, track_t, mix_t, n_pro, rate, active_mask, t_share, bar_sec=BAR_SEC):
    """Look for an outgoing phrase repeat (8/16/32 bars back) during the blend."""
    here = place_source(src_path, track_t, mix_t, n_pro, rate=rate, extra=8)
    backs = {sh: place_source(src_path, track_t - sh * bar_sec * rate, mix_t, n_pro,
                              rate=rate, extra=8)
             for sh in (8, 16, 32)}
    hits = []
    windows = (12.0, 24.0, 36.0)
    for shift, back in backs.items():
        better = 0
        compared = 0
        for t0 in windows:
            i0, i1 = int(t0 * SR), int((t0 + 6.0) * SR)
            if i1 > n_pro:
                continue
            win = pro[i0:i1]
            c0 = spec_corr(win, here[i0:i1])
            cb = spec_corr(win, back[i0:i1])
            compared += 1
            if cb > c0 + 0.15 and cb > 0.50:
                better += 1
        if compared and better >= 2:
            hits.append(shift)
    return hits


def detect_echo(pro, a, gA, t, bar_sec=BAR_SEC):
    """After outgoing gain collapses, does pro still correlate with delayed A?"""
    if gA is None or len(gA) < 4:
        return False
    # find fade end
    ref = np.percentile(gA[: max(2, len(gA)//6)], 75)
    end_t = None
    for i, v in enumerate(gA):
        if t[i] > 8 and v < 0.15 * max(ref, 1e-6):
            end_t = float(t[i]); break
    if end_t is None or end_t > 56:
        return False
    i0 = int(end_t * SR)
    i1 = min(len(pro), i0 + int(6 * SR))
    if i1 - i0 < int(1.5 * SR):
        return False
    beat = 60.0 / 174.0
    base = spec_corr(pro[i0:i1], a[i0:i1])
    best = base
    for d in (0.5, 1.0, 2.0, 4.0):
        lag = int(d * beat * SR)
        if i0 + lag >= len(a):
            continue
        c = spec_corr(pro[i0:i1], a[i0 + lag:i1 + lag] if i1 + lag <= len(a)
                      else np.pad(a[i0 + lag:], (0, max(0, (i1 - i0) - (len(a) - i0 - lag)))))
        best = max(best, c)
    return bool(best > base + 0.10 and best > 0.35)


def blend_window(gA, gB, t):
    """Approximate [start, end] of the two-track overlap from fullband gains."""
    gA = np.asarray(gA, float); gB = np.asarray(gB, float)
    a_ref = np.percentile(gA[: max(2, len(gA)//8)], 75) if len(gA) else 1
    b_ref = np.percentile(gB[int(len(gB)*0.75):], 75) if len(gB) else 1
    a_on = gA > 0.25 * max(a_ref, 1e-6)
    b_on = gB > 0.25 * max(b_ref, 1e-6)
    both = a_on & b_on
    if not np.any(both):
        # fallback: incoming rise to outgoing fall
        tb = half_cross(gB, t, 'in') or 20.0
        ta = half_cross(gA, t, 'out') or 36.0
        return [max(0.0, tb - 4), min(64.0, max(ta + 4, tb + 8))]
    idx = np.where(both)[0]
    return [float(t[idx[0]]), float(t[idx[-1]])]


def write_wav(path, y):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import subprocess
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1',
         '-i', '-', '-ac', '1', '-ar', str(SR), path],
        input=np.asarray(y, np.float32).tobytes(), check=True)


def phase_info(row, loc_a, loc_b, rate_a, rate_b, blend):
    try:
        sta = os.path.join(paths.SRC2, 'st', f"{row['a']['yt']}.json")
        stb = os.path.join(paths.SRC2, 'st', f"{row['b']['yt']}.json")
        ba = ST.load_bar(sta); bb = ST.load_bar(stb)
        la = ST.label_phases(ba); lb = ST.label_phases(bb)
        bpm_a = float((row.get('gate') or {}).get('a', {}).get('bpm', {}).get('bpm') or 174)
        bpm_b = float((row.get('gate') or {}).get('b', {}).get('bpm', {}).get('bpm') or 174)
        src_t0_a = float(loc_a['track_t']) - float(loc_a['mix_t']) * rate_a
        src_t0_b = float(loc_b['track_t']) - float(loc_b['mix_t']) * rate_b
        def bar_at(src_t0, t, bpm):
            return (src_t0 + t * (bpm / 174.0 if False else 1) * 1) * bpm / 240.0
        # incoming drop after B is present in the clip
        b_start = max(0.0, -src_t0_b)  # clip time when B's file starts
        drop_b = ST.first_drop_bar(lb, after=max(0, int(bar_at(src_t0_b, 0.0, bpm_b))))
        in_drop_t = None
        if drop_b is not None:
            # mix time of that source bar
            src_time = drop_b * 240.0 / bpm_b
            in_drop_t = (src_time - src_t0_b) / max(rate_b, 1e-9)
            if in_drop_t < 0 or in_drop_t > 64:
                drop_b2 = ST.first_drop_bar(lb, after=int(bar_at(src_t0_b, 8.0, bpm_b)))
                if drop_b2 is not None:
                    src_time = drop_b2 * 240.0 / bpm_b
                    in_drop_t = (src_time - src_t0_b) / max(rate_b, 1e-9)
                    drop_b = drop_b2
        out_phase = None
        if in_drop_t is not None and 0 <= in_drop_t <= 64:
            out_bar = bar_at(src_t0_a, in_drop_t * rate_a, bpm_a)
            out_phase = ST.phase_at(la, out_bar)
        # outgoing phase at blend start
        mix_phase = ST.phase_at(la, bar_at(src_t0_a, blend[0] * rate_a, bpm_a)) if blend else None
        return dict(
            incoming_drop_clip_s=None if in_drop_t is None else round(float(in_drop_t), 2),
            outgoing_phase_at_in_drop=out_phase,
            outgoing_phase_at_blend_start=mix_phase,
        )
    except Exception as e:
        return dict(error=str(e)[-180:])


def analyse_clip(row, base_row, talk):
    cid = row['id']
    pro_p = _clip_path(row)
    sa, sb = _src_path(row['a']['yt']), _src_path(row['b']['yt'])
    if not os.path.exists(pro_p):
        return dict(id=cid, error='missing pro clip')
    if not os.path.exists(sa) or not os.path.exists(sb):
        return dict(id=cid, error='missing source')
    pro = _load(pro_p)
    n = len(pro)
    gate = row.get('gate') or {}
    loc_a = dict(gate.get('a', {}).get('locate') or {})
    loc_b = dict(gate.get('b', {}).get('locate') or {})
    if loc_a.get('mix_t') is None or loc_a.get('track_t') is None:
        ya = _load(sa); hit = version_match.locate_in(pro, ya); loc_a = hit
    if loc_b.get('mix_t') is None or loc_b.get('track_t') is None:
        yb = _load(sb); hit = version_match.locate_in(pro, yb); loc_b = hit

    # rate search in likely-solo regions
    mix_tb = float(loc_b.get('mix_t') or 24.0)
    ra_found, ca_best, ca0 = search_rate(pro, sa, loc_a['track_t'], loc_a['mix_t'], n,
                                   region=(1.0, min(16.0, max(8.0, mix_tb - 6))))
    rb_found, cb_best, cb0 = search_rate(pro, sb, loc_b['track_t'], loc_b['mix_t'], n,
                                   region=(max(mix_tb + 8, 40.0), 62.0))
    use_ra = abs(ra_found - 1.0) >= 0.005 and (ca_best - ca0) >= RATE_IMPROVE
    use_rb = abs(rb_found - 1.0) >= 0.005 and (cb_best - cb0) >= RATE_IMPROVE
    ra = ra_found if use_ra else 1.0
    rb = rb_found if use_rb else 1.0

    A = place_source(sa, loc_a['track_t'], loc_a['mix_t'], n, rate=ra)
    B = place_source(sb, loc_b['track_t'], loc_b['mix_t'], n, rate=rb)
    A, lag_a = refine_lag(pro, A, max_s=0.9)
    B, lag_b = refine_lag(pro, B, max_s=0.9)

    su = spec_unexplained(pro, A, B)
    gains, rec, gt, hop = band_gains(pro, A, B)
    blend = blend_window(gains['all']['a'], gains['all']['b'], gt)

    # version: spectral corr in pre/post blend (outside overlap)
    pre_t1 = max(6.0, min(blend[0] - 1.0, 20.0))
    post_t0 = min(56.0, max(blend[1] + 1.0, 48.0))
    pre0, pre1 = 1.0, pre_t1
    post0, post1 = post_t0, min(63.0, n / SR - 0.3)
    if pre1 - pre0 < 4:
        pre0, pre1 = 1.0, 10.0
    if post1 - post0 < 4:
        post0, post1 = max(48.0, n / SR - 14), n / SR - 0.3
    i_pre = slice(int(pre0 * SR), int(pre1 * SR))
    i_post = slice(int(post0 * SR), int(post1 * SR))
    ver_a = spec_corr(pro[i_pre], A[i_pre])
    ver_b = spec_corr(pro[i_post], B[i_post])
    unex_pre = region_mean(su['share'], su['t'], pre0, pre1, su['active'])
    unex_post = region_mean(su['share'], su['t'], post0, post1, su['active'])
    unex_blend = region_mean(su['share'], su['t'], blend[0], blend[1], su['active'])
    unex_all = su['overall']

    # waveform residual (after per-band gains) — secondary, phase-sensitive
    nn = min(len(pro), len(rec))
    e_p = float(np.mean(pro[:nn] ** 2) + 1e-12)
    e_r = float(np.mean((pro[:nn] - rec[:nn]) ** 2))
    wav_res = e_r / e_p

    # technique from curves
    x_bass = half_cross(gains['bass']['a'], gt, 'out')
    x_mids = half_cross(gains['mids']['a'], gt, 'out')
    x_high = half_cross(gains['highs']['a'], gt, 'out')
    in_bass = half_cross(gains['bass']['b'], gt, 'in')
    eq_diffs = [d for d in (x_high, x_mids, x_bass) if d is not None]
    eq_swap = None
    if x_bass is not None and x_high is not None:
        eq_swap = round((x_high - x_bass) / BAR_SEC, 2)
    fader = classify_fader(gains['all']['a'], gt, blend)
    filter_sweep = bool(x_high is not None and x_bass is not None and (x_high + 2 * BAR_SEC) < x_bass)
    loops = detect_loop(pro, sa, loc_a['track_t'], loc_a['mix_t'], n, ra, None, None)
    echo = detect_echo(pro, A, gains['all']['a'], gt)
    blend_bars = round((blend[1] - blend[0]) / BAR_SEC, 2)
    phase = phase_info(row, loc_a, loc_b, ra, rb, blend)

    # events from fitted bass curves (same helper the scorer uses)
    ev = score.events_from_pair(
        score._db(score._rms(gains['bass']['a'][0] * 0 + _butter(A, 'low', 150) * 0 + A * 0 + 
                             np.interp(np.arange(n) / SR, gt, gains['bass']['a'], left=gains['bass']['a'][0], right=gains['bass']['a'][-1]) * np.abs(_butter(A, 'low', 150)))),
        score._db(score._rms(
            np.interp(np.arange(n) / SR, gt, gains['bass']['b'], left=gains['bass']['b'][0], right=gains['bass']['b'][-1]) * np.abs(_butter(B, 'low', 150))))
    ) if False else None
    # simpler event estimate from gain times
    ev_fit = dict(
        bass_swap_s=None if in_bass is None or x_bass is None else round(in_bass, 2),
        outgoing_half_s=None if x_bass is None else round(x_bass, 2),
        outgoing_half_high_s=None if x_high is None else round(x_high, 2),
        blend_s=round(blend[1] - blend[0], 2),
        blend_bars=blend_bars,
    )

    # oracle reconstruction + score
    oracle_p = os.path.join(SCRATCH, f'{cid}_oracle.wav')
    # mild peak normalize to avoid clipping but keep relative level
    rec_w = rec.copy()
    peak = float(np.max(np.abs(rec_w)) + 1e-9)
    if peak > 1.0:
        rec_w = rec_w / peak * 0.98
    write_wav(oracle_p, rec_w)
    sc = score.score(pro_p, oracle_p, sa, sb, use_demucs=False, cache=os.path.join(SCRATCH, 'scorecache'))
    try:
        os.remove(oracle_p)
    except OSError:
        pass

    current = (base_row or {}).get('score')
    cur_bd = (base_row or {}).get('breakdown') or {}
    ora_bd = sc.get('breakdown') or {}

    # flags
    version_bad = ((ver_a < SOLO_CORR_BAD and (unex_pre or 0) > SOLO_UNEX_BAD) or
                   (ver_b < SOLO_CORR_BAD and (unex_post or 0) > SOLO_UNEX_BAD))
    pitch_a = abs(ra_found - 1.0) >= RATE_MIN and (ca_best - ca0) >= RATE_IMPROVE
    pitch_b = abs(rb_found - 1.0) >= RATE_MIN and (cb_best - cb0) >= RATE_IMPROVE
    extra = unex_all >= UNEX_EXTRA
    tech_gap = None if current is None else round(sc['score'] - current, 2)
    def _implied(bd):
        if not bd or bd.get('stem_curves') is None:
            return None
        W = score.W
        audio = (W['stem_curves'] * float(bd.get('stem_curves') or 0)
                 + W['deck_curves'] * float(bd.get('deck_curves') or 0)
                 + W['beat_align'] * float(bd.get('beat_align') or 0))
        gate = 0.35 + 0.65 * (float(bd.get('stem_curves') or 0) / 100.0)
        ev_w = W['bass_swap'] + W['outgoing_cut'] + W['blend_length']
        return round(audio + ev_w * 100.0 * gate, 2)
    implied = _implied(ora_bd)
    event_drag = None if implied is None else round(implied - sc['score'], 2)

    rec_out = dict(
        id=cid, dj=row.get('dj'), split=row.get('split'), pair=row.get('pair'),
        current_score=current,
        current_breakdown={k: cur_bd.get(k) for k in
                           ('stem_curves', 'deck_curves', 'beat_align', 'bass_swap',
                            'outgoing_cut', 'blend_length', 'beat_off_ms')},
        current_events=cur_bd.get('events_ours'),
        pro_events_scorer=cur_bd.get('events_pro'),
        current_align=cur_bd.get('align'),
        oracle_score=sc['score'],
        oracle_breakdown={k: ora_bd.get(k) for k in
                          ('stem_curves', 'deck_curves', 'beat_align', 'bass_swap',
                           'outgoing_cut', 'blend_length', 'beat_off_ms', 'stems')},
        oracle_events=ora_bd.get('events_pro') and dict(events_oracle=ora_bd.get('events_ours'),
                                                         events_pro=ora_bd.get('events_pro')),
        oracle_align=ora_bd.get('align'),
        technique_gap=tech_gap,
        oracle_if_events_perfect=implied,
        scorer_event_drag=event_drag,
        residual=dict(
            stft_unexplained=round(unex_all, 4),
            unexplained_pre=None if unex_pre is None else round(unex_pre, 4),
            unexplained_blend=None if unex_blend is None else round(unex_blend, 4),
            unexplained_post=None if unex_post is None else round(unex_post, 4),
            waveform_residual=round(wav_res, 4),
        ),
        version=dict(
            solo_corr_a=round(ver_a, 4), solo_corr_b=round(ver_b, 4),
            solo_window_a=[round(pre0, 2), round(pre1, 2)],
            solo_window_b=[round(post0, 2), round(post1, 2)],
            locate_a=loc_a, locate_b=loc_b,
        ),
        tempo_pitch=dict(
            rate_a=round(float(ra_found), 4), rate_b=round(float(rb_found), 4),
            corr_a_at_best=round(float(ca_best), 4), corr_a_at_1=round(float(ca0), 4),
            corr_b_at_best=round(float(cb_best), 4), corr_b_at_1=round(float(cb0), 4),
            cents_a=float(round(1200 * np.log2(max(ra_found, 1e-9)), 1)),
            cents_b=float(round(1200 * np.log2(max(rb_found, 1e-9)), 1)),
            flagged_a=bool(pitch_a), flagged_b=bool(pitch_b),
            rate_applied_a=bool(use_ra), rate_applied_b=bool(use_rb),
            refine_lag_a=int(lag_a), refine_lag_b=int(lag_b),
        ),
        technique=dict(
            blend_window_s=[round(blend[0], 2), round(blend[1], 2)],
            blend_bars=blend_bars,
            fader_outgoing=fader,
            eq_swap_high_minus_bass_bars=eq_swap,
            filter_sweep=filter_sweep,
            loop_shift_bars=loops,
            echo_out=echo,
            half_cross_s=dict(out_bass=x_bass, out_mids=x_mids, out_high=x_high, in_bass=in_bass),
            events_from_gains=ev_fit,
            phase=phase,
        ),
        talkover=None if not talk else {k: talk.get(k) for k in
                                        ('talk_s', 'talk_frac', 'loose_s', 'mean_unexplained', 'flagged')},
        flags=dict(version_mismatch=bool(version_bad), tempo_pitch=bool(pitch_a or pitch_b),
                   extra_material=bool(extra)),
    )
    return rec_out


def bucket_clip(r):
    cur = r.get('current_score')
    ora = r.get('oracle_score')
    if ora is None or r.get('error'):
        return 'error'
    unex = (r.get('residual') or {}).get('stft_unexplained') or 0
    ver = r.get('version') or {}
    va, vb = ver.get('solo_corr_a') or 0, ver.get('solo_corr_b') or 0
    unex_pre = (r.get('residual') or {}).get('unexplained_pre') or 0
    unex_post = (r.get('residual') or {}).get('unexplained_post') or 0
    version_bad = ((va < SOLO_CORR_BAD and unex_pre > SOLO_UNEX_BAD) or
                   (vb < SOLO_CORR_BAD and unex_post > SOLO_UNEX_BAD))
    pitch = bool((r.get('flags') or {}).get('tempo_pitch'))
    extra = unex >= UNEX_EXTRA
    gap = (ora - cur) if cur is not None else 0
    unach = 100.0 - ora
    if gap >= ORACLE_TECH_GAP:
        return 'technique'
    if version_bad:
        return 'version_mismatch'
    if pitch:
        return 'tempo_pitch'
    if extra:
        return 'extra_material'
    if ora < ORACLE_LOW and unex < UNEX_CLEAN and min(va, vb) >= SOLO_CORR_BAD:
        return 'scorer_limit'
    if gap >= 8:
        return 'technique'
    if extra or unex >= 0.18:
        return 'extra_material'
    if version_bad or min(va, vb) < 0.48:
        return 'version_mismatch'
    if pitch:
        return 'tempo_pitch'
    if unach > gap and unex < UNEX_CLEAN:
        return 'scorer_limit'
    return 'technique'


def attribute_costs(r):
    cur = r.get('current_score')
    ora = r.get('oracle_score')
    if cur is None or ora is None:
        return {}
    tech = max(0.0, ora - cur)
    rest = max(0.0, 100.0 - ora)
    unex = (r.get('residual') or {}).get('stft_unexplained') or 0
    ver = r.get('version') or {}
    vmin = min(ver.get('solo_corr_a') or 0, ver.get('solo_corr_b') or 0)
    w_ver = max(0.0, (0.55 - vmin) / 0.55)
    w_ex = float(np.clip(unex / 0.40, 0, 1))
    w_pi = 1.0 if (r.get('flags') or {}).get('tempo_pitch') else 0.0
    w_sc = 0.35 if (unex < UNEX_CLEAN and vmin > 0.50) else 0.08
    ws = dict(version_mismatch=w_ver, extra_material=w_ex, tempo_pitch=w_pi, scorer_limit=w_sc)
    s = sum(ws.values()) or 1.0
    out = {k: rest * (v / s) for k, v in ws.items()}
    out['technique'] = tech
    # finer technique split from breakdown deltas
    W = score.W
    cb = r.get('current_breakdown') or {}
    ob = r.get('oracle_breakdown') or {}
    parts = {}
    for k in W:
        c = cb.get(k); o = ob.get(k)
        if c is None or o is None:
            continue
        parts[k] = W[k] * max(0.0, o - c)
    out['technique_parts'] = {k: round(v, 3) for k, v in parts.items()}
    return {k: (round(v, 3) if not isinstance(v, dict) else v) for k, v in out.items()}


def load_ckpt():
    if os.path.exists(CKPT):
        return json.load(open(CKPT))
    return {'rows': []}


def save_ckpt(ck):
    os.makedirs(paths.RESULTS, exist_ok=True)
    tmp = CKPT + '.tmp'
    json.dump(ck, open(tmp, 'w'), indent=2)
    os.replace(tmp, CKPT)


def summarize(rows):
    ok = [r for r in rows if r.get('oracle_score') is not None and not r.get('error')]
    for r in ok:
        r['bucket'] = bucket_clip(r)
        r['costs'] = attribute_costs(r)
    from collections import Counter
    buckets = Counter(r['bucket'] for r in ok)
    cur = [r['current_score'] for r in ok if r.get('current_score') is not None]
    ora = [r['oracle_score'] for r in ok]
    gaps = [r['technique_gap'] for r in ok if r.get('technique_gap') is not None]
    # mean costs
    keys = ['technique', 'version_mismatch', 'extra_material', 'tempo_pitch', 'scorer_limit']
    mean_costs = {k: float(np.mean([r['costs'].get(k, 0) for r in ok])) for k in keys}
    # technique parts
    tparts = {}
    for k in score.W:
        vals = [(r['costs'].get('technique_parts') or {}).get(k) for r in ok]
        vals = [v for v in vals if v is not None]
        if vals:
            tparts[k] = round(float(np.mean(vals)), 3)
    # by split
    def stats(rs):
        if not rs:
            return None
        return dict(
            n=len(rs),
            current_mean=round(float(np.mean([r['current_score'] for r in rs if r.get('current_score') is not None])), 2),
            oracle_mean=round(float(np.mean([r['oracle_score'] for r in rs])), 2),
            technique_gap_mean=round(float(np.mean([r['technique_gap'] for r in rs if r.get('technique_gap') is not None] or [0])), 2),
            unexplained_mean=round(float(np.mean([(r.get('residual') or {}).get('stft_unexplained') or 0 for r in rs])), 4),
            version_corr_mean=round(float(np.mean([
                0.5 * ((r.get('version') or {}).get('solo_corr_a') or 0) +
                0.5 * ((r.get('version') or {}).get('solo_corr_b') or 0) for r in rs])), 4),
        )
    by_split = {sp: stats([r for r in ok if r.get('split') == sp]) for sp in ('train', 'test')}
    # technique flags
    n = max(len(ok), 1)
    tech_flags = dict(
        eq_swap_ge2bars=sum(1 for r in ok if abs((r.get('technique') or {}).get('eq_swap_high_minus_bass_bars') or 0) >= 2),
        filter_sweep=sum(1 for r in ok if (r.get('technique') or {}).get('filter_sweep')),
        echo_out=sum(1 for r in ok if (r.get('technique') or {}).get('echo_out')),
        loop=sum(1 for r in ok if (r.get('technique') or {}).get('loop_shift_bars')),
        fader_shapes=dict(Counter((r.get('technique') or {}).get('fader_outgoing', {}).get('shape') for r in ok)),
        blend_bars_mean=round(float(np.mean([(r.get('technique') or {}).get('blend_bars') or 0 for r in ok])), 2),
        pitched_incoming=sum(1 for r in ok if (r.get('tempo_pitch') or {}).get('flagged_b')),
        pitched_outgoing=sum(1 for r in ok if (r.get('tempo_pitch') or {}).get('flagged_a')),
        drop_on_breakdown=sum(1 for r in ok if ((r.get('technique') or {}).get('phase') or {}).get('outgoing_phase_at_in_drop') == 'breakdown'),
        drop_on_drop=sum(1 for r in ok if ((r.get('technique') or {}).get('phase') or {}).get('outgoing_phase_at_in_drop') == 'drop'),
        drop_on_outro=sum(1 for r in ok if ((r.get('technique') or {}).get('phase') or {}).get('outgoing_phase_at_in_drop') == 'outro'),
    )
    # estimated gains
    # engine perfect-gain: lift every clip to its oracle
    gain_technique = float(np.mean(gaps)) if gaps else 0.0
    # version: lift version-bucket oracles to median oracle of clean clips
    clean = [r for r in ok if r['bucket'] not in ('version_mismatch', 'extra_material')]
    clean_ora = float(np.median([r['oracle_score'] for r in clean])) if clean else float(np.median(ora))
    ver_rows = [r for r in ok if r['bucket'] == 'version_mismatch']
    gain_version = float(sum(max(0.0, clean_ora - r['oracle_score']) for r in ver_rows) / n)
    extra_rows = [r for r in ok if r['bucket'] == 'extra_material']
    cost_extra = float(sum(max(0.0, 100.0 - r['oracle_score']) for r in extra_rows) / n)
    pitch_rows = [r for r in ok if r['bucket'] == 'tempo_pitch']
    gain_pitch = float(sum(max(0.0, (r['oracle_score'] - (r['current_score'] or 0))) for r in pitch_rows) / n)
    scorer_rows = [r for r in ok if r['bucket'] == 'scorer_limit']
    cost_scorer = float(np.mean([r['costs'].get('scorer_limit', 0) for r in ok]))

    # ranking of engine-fixable subcauses
    sub = sorted(tparts.items(), key=lambda kv: -kv[1])

    return dict(
        n=len(ok), n_error=sum(1 for r in rows if r.get('error')),
        bucket_counts=dict(buckets),
        current_mean=round(float(np.mean(cur)), 2) if cur else None,
        oracle_mean=round(float(np.mean(ora)), 2),
        oracle_if_events_perfect_mean=round(float(np.mean([r.get('oracle_if_events_perfect') or r['oracle_score'] for r in ok])), 2),
        scorer_event_drag_mean=round(float(np.mean([r.get('scorer_event_drag') or 0 for r in ok])), 2),
        oracle_median=round(float(np.median(ora)), 2),
        oracle_p25=round(float(np.percentile(ora, 25)), 2),
        oracle_p75=round(float(np.percentile(ora, 75)), 2),
        technique_gap_mean=round(gain_technique, 2),
        unexplained_mean=round(float(np.mean([(r.get('residual') or {}).get('stft_unexplained') or 0 for r in ok])), 4),
        by_split=by_split,
        mean_attributed_cost= {k: round(v, 2) for k, v in mean_costs.items()},
        technique_term_gains=tparts,
        technique_flags=tech_flags,
        estimated_gain=dict(
            technique_perfect_gains=round(gain_technique, 2),
            better_versions=round(gain_version, 2),
            tempo_pitch_matching=round(gain_pitch, 2),
            extra_material_unfixable_cost=round(cost_extra, 2),
            scorer_limit_cost=round(cost_scorer, 2),
        ),
        thresholds=dict(SOLO_CORR_BAD=SOLO_CORR_BAD, SOLO_UNEX_BAD=SOLO_UNEX_BAD,
                        RATE_MIN=RATE_MIN, RATE_IMPROVE=RATE_IMPROVE,
                        UNEX_EXTRA=UNEX_EXTRA, ORACLE_TECH_GAP=ORACLE_TECH_GAP,
                        ORACLE_LOW=ORACLE_LOW, UNEX_CLEAN=UNEX_CLEAN),
    )


def write_md(summary, rows):
    b = summary['bucket_counts']
    g = summary['estimated_gain']
    lines = []
    lines.append('# Pro-transition gap diagnosis')
    lines.append('')
    lines.append(f"Admitted clips analysed: **{summary['n']}** "
                 f"(train { (summary['by_split']['train'] or {}).get('n') }, "
                 f"test { (summary['by_split']['test'] or {}).get('n') }).")
    lines.append('')
    lines.append('## Ceiling vs current')
    lines.append('')
    lines.append(f"- Current recreation mean: **{summary['current_mean']}** / 100 "
                 f"(held-out test { (summary['by_split']['test'] or {}).get('current_mean') }).")
    lines.append(f"- Oracle mean (perfect per-band gains of our studio copies): "
                 f"**{summary['oracle_mean']}** / 100 "
                 f"(median {summary['oracle_median']}, IQR {summary['oracle_p25']}–{summary['oracle_p75']}).")
    lines.append(f"- Mean technique gap (oracle − current): **{summary['technique_gap_mean']}** points.")
    if summary.get('oracle_if_events_perfect_mean') is not None:
        lines.append(f"- Oracle if the event detectors agreed (perfect bass-swap / cut / length terms, gated as in score.py): "
                     f"**{summary['oracle_if_events_perfect_mean']}** / 100 "
                     f"(mean event-term drag **{summary.get('scorer_event_drag_mean')}** points).")
    lines.append(f"- Mean unexplained energy after the gain fit: **{summary['unexplained_mean']:.1%}**.")
    lines.append('')
    lines.append('The oracle fits time-varying bass/mid/high gains of the two aligned studio')
    lines.append('tracks to the pro clip, then runs the same scorer used for recreations')
    lines.append('(band proxies, fixed weights). It is the realistic ceiling for an engine')
    lines.append('that can only fade and EQ our copies — not invent a third track or a different master.')
    lines.append('')
    lines.append('## Primary-cause buckets')
    lines.append('')
    order = ['technique', 'version_mismatch', 'extra_material', 'tempo_pitch', 'scorer_limit', 'error']
    for k in order:
        if k in b:
            lines.append(f"- **{k}**: {b[k]}")
    lines.append('')
    lines.append('A clip is `technique` when a perfect gain-curve of our sources would beat')
    lines.append('the current recreation by 20+ points (or 8+ after other flags are ruled out).')
    lines.append('`version_mismatch` is a weak match between a studio copy and the pro clip')
    lines.append('outside the blend. `extra_material` is leftover energy the two sources cannot')
    lines.append('explain (third track, acapella, samples, FX, MC). `tempo_pitch` is a CDJ-style')
    lines.append('rate offset of about 2% or more. `scorer_limit` is a clean fit whose oracle')
    lines.append('score is still low — the metric itself is leaving points on the table.')
    lines.append('')
    lines.append('## What each cause costs')
    lines.append('')
    lines.append('Mean points of the 100 − current gap attributed to each cause:')
    lines.append('')
    for k, v in summary['mean_attributed_cost'].items():
        lines.append(f"- {k}: {v}")
    lines.append('')
    lines.append('Estimated lift of the corpus mean if we fixed that cause:')
    lines.append('')
    lines.append(f"- Perfect gain-curves / EQ fades (engine): **+{g['technique_perfect_gains']}**")
    lines.append(f"- Better matching source versions (data): **+{g['better_versions']}**")
    lines.append(f"- Tempo/pitch matching (engine): **+{g['tempo_pitch_matching']}**")
    lines.append(f"- Extra material left unexplained (unfixable): costs **{g['extra_material_unfixable_cost']}** vs 100")
    lines.append(f"- Scorer ceiling (metric): **{g['scorer_limit_cost']}**")
    lines.append('')
    lines.append('Engine-fixable scorer terms (mean weighted points, oracle vs current):')
    lines.append('')
    for k, v in sorted(summary['technique_term_gains'].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}: +{v}")
    lines.append('')
    tf = summary['technique_flags']
    lines.append('## Technique observations on the pro clips')
    lines.append('')
    lines.append(f"- Mean fitted blend length: {tf['blend_bars_mean']} bars")
    lines.append(f"- Outgoing fader shapes: {tf['fader_shapes']}")
    lines.append(f"- EQ swap (high vs bass half-cross ≥ 2 bars): {tf['eq_swap_ge2bars']} / {summary['n']}")
    lines.append(f"- Filter sweep (highs out well before bass): {tf['filter_sweep']}")
    lines.append(f"- Echo-out after the outgoing fade: {tf['echo_out']}")
    lines.append(f"- Possible outgoing loop (8/16/32-bar jump): {tf['loop']}")
    lines.append(f"- Pitched incoming / outgoing: {tf['pitched_incoming']} / {tf['pitched_outgoing']}")
    lines.append(f"- Incoming drop lands on outgoing breakdown / drop / outro: "
                 f"{tf['drop_on_breakdown']} / {tf['drop_on_drop']} / {tf['drop_on_outro']}")
    lines.append('')
    lines.append('## Recommended next steps')
    lines.append('')
    lines.append(summary.get('plan_text') or '')
    lines.append('')
    lines.append('## Per-clip table')
    lines.append('')
    lines.append('| id | split | current | oracle | gap | unexplained | ver A | ver B | bucket |')
    lines.append('|---|---|---:|---:|---:|---:|---:|---:|---|')
    for r in sorted(rows, key=lambda x: (-((x.get('oracle_score') or 0) - (x.get('current_score') or 0)), x.get('id') or '')):
        if r.get('error'):
            lines.append(f"| {r.get('id')} | {r.get('split')} |  |  |  |  |  |  | error |")
            continue
        res = (r.get('residual') or {})
        ver = (r.get('version') or {})
        lines.append(
            f"| {r['id']} | {r.get('split')} | {r.get('current_score')} | {r.get('oracle_score')} | "
            f"{r.get('technique_gap')} | {res.get('stft_unexplained')} | "
            f"{ver.get('solo_corr_a')} | {ver.get('solo_corr_b')} | {r.get('bucket')} |"
        )
    lines.append('')
    return '\n'.join(lines)


def plan_from_summary(summary):
    g = summary['estimated_gain']
    parts = summary['technique_term_gains']
    top_terms = sorted(parts.items(), key=lambda kv: -kv[1])[:3]
    buckets = summary['bucket_counts']
    steps = []
    steps.append('Do not change scoring weights. The oracle uses the same fixed metric,')
    steps.append('so a higher recreation score from here on would be a real engine gain.')
    steps.append('')
    if g['technique_perfect_gains'] >= 10:
        steps.append('1. Engine (biggest lever): treat the oracle gap as the hill-climb target.')
        if top_terms:
            steps.append('   The scorer terms that move the most when gains match the pro are: '
                         + ', '.join(f"{k} (+{v})" for k, v in top_terms) + '.')
        steps.append('   Next rule trials should copy what the fitted curves actually do:')
        steps.append('   independent bass / mid / high handoffs (EQ swaps), fader shape')
        steps.append('   (many outgoing fades are cuts or equal-power, not a long linear tail),')
        steps.append('   and blend length that follows the outgoing phase rather than a flat 32-bar preference.')
        steps.append('   Keep the existing train/test-by-DJ rule: only keep a change if held-out does not drop.')
    else:
        steps.append('1. Engine technique is not the main ceiling — oracle is close to current.')
    steps.append('')
    if g['better_versions'] >= 1.5 or buckets.get('version_mismatch', 0) >= 3:
        steps.append('2. Data: replace studio copies on version_mismatch clips (different edit,')
        steps.append('   radio cut, or YouTube master). Re-admit those pairs after the version gate.')
    else:
        steps.append('2. Data: source versions are mostly fine; do not spend a cycle re-ripping the library.')
    steps.append('')
    if g['tempo_pitch_matching'] >= 1.0 or buckets.get('tempo_pitch', 0) >= 2:
        steps.append('3. Engine: allow a small CDJ-style pitch/rate offset on the incoming track')
        steps.append('   (search ±3%) before blending. Several clips line up better that way.')
    else:
        steps.append('3. Engine: incoming pitch-up is rare here; a rate search is optional, not the next hill-climb.')
    steps.append('')
    if buckets.get('extra_material', 0):
        steps.append(f"4. Unfixable: {buckets.get('extra_material', 0)} clips have leftover energy")
        steps.append('   (third track, sample, FX). Keep them out of “did we match the pro?”')
        steps.append('   targets, or down-weight them, like the talkover filter.')
    if buckets.get('scorer_limit', 0):
        steps.append('')
        steps.append(f"5. Metric: {buckets.get('scorer_limit', 0)} clips reconstruct cleanly but still")
        steps.append('   score low. Kick-envelope alignment of ours-vs-pro already shows weak peaks')
        steps.append('   and ±24 s false locks on the current recreations; if that also shows up on')
        steps.append('   oracles it is worth fixing the aligner before more rule tuning.')
    return '\n'.join(steps)


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    admitted = json.load(open(ADMITTED))
    base = json.load(open(BASE))
    by_id = {r['id']: r for r in base.get('rows') or []}
    talk = json.load(open(TALKOVER)) if os.path.exists(TALKOVER) else {}
    ck = load_ckpt()
    done = {r['id']: r for r in ck.get('rows') or []}
    print(f'admitted {len(admitted)} already {len(done)}', flush=True)
    for i, row in enumerate(admitted):
        cid = row['id']
        if cid in done and not done[cid].get('error'):
            print(f'skip {cid}', flush=True)
            continue
        print(f'[{i+1}/{len(admitted)}] {cid}', flush=True)
        try:
            rec = analyse_clip(row, by_id.get(cid), talk.get(cid))
        except Exception as e:
            rec = dict(id=cid, split=row.get('split'), dj=row.get('dj'),
                       error=f'{type(e).__name__}: {e}'[-300:],
                       trace=traceback.format_exc()[-800:])
            print('ERROR', cid, rec['error'], flush=True)
        done[cid] = rec
        ck['rows'] = list(done.values())
        save_ckpt(ck)
        if rec.get('oracle_score') is not None:
            print(f"  current={rec.get('current_score')} oracle={rec.get('oracle_score')} "
                  f"unex={rec['residual']['stft_unexplained']} "
                  f"ver={rec['version']['solo_corr_a']}/{rec['version']['solo_corr_b']} "
                  f"rateB={rec['tempo_pitch']['rate_b']}", flush=True)

    rows = [done[r['id']] for r in admitted if r['id'] in done]
    summary = summarize(rows)
    summary['plan_text'] = plan_from_summary(summary)
    out = dict(
        generated='2026-11-08',
        method=(
            'For each admitted clip, studio A/B are located in the 64 s pro extract, '
            'optionally rate-matched (±3% CDJ-style), then fitted as time-varying '
            'bass/mid/high gains (NNLS per 250 ms). Unexplained energy is the leftover '
            'STFT magnitude after a 1 s NNLS mix of the two sources. The reconstruction '
            'is scored with score.py (use_demucs=False) against the pro clip; that score '
            'is the oracle ceiling for an engine that can only fade/EQ our copies. '
            'Current scores come from results/baseline_clean.json. Engine rules were not changed.'
        ),
        summary=summary,
        clips=rows,
    )
    def _enc(o):
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(type(o))
    json.dump(out, open(OUT_JSON, 'w'), indent=2, default=_enc)
    md = write_md(summary, rows)
    open(OUT_MD, 'w').write(md)
    print('wrote', OUT_JSON, OUT_MD, flush=True)
    print(json.dumps(summary['bucket_counts'], indent=2), flush=True)
    print('current', summary['current_mean'], 'oracle', summary['oracle_mean'],
          'gap', summary['technique_gap_mean'], flush=True)
    # cleanup scratch (keep nothing)
    shutil.rmtree(SCRATCH, ignore_errors=True)
    try:
        os.remove(CKPT)
    except OSError:
        pass


if __name__ == '__main__':
    main()
