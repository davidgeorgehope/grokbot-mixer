"""Contribution-weighted spectral collision and continuity (diagnostic only).

Implements Daito Manabe, 'On the Measurability of DJ Mix Quality' (March 2026),
https://projects.daito.ws/dj-mix-research-institute/paper/on_measurability_dj_mix_quality_daito_manabe_en.pdf
§§5.2–5.3 (and the contribution ratios in §4.2), plus Banger Lab's 6-band clash()
as a companion per-beat rate.

This is NEVER a failing test or a build gate. It does not read or write
protrans/rules.json and does not change any existing threshold. Higher Scol /
Scty are better (exp(-penalty / scale)); raw penalties are also returned
(higher is worse). Scales, when present, are calibrated on admitted pro
transitions so a penalty equal to the pro median maps to score 0.70.

usage (cwd src2):
  python3 spectral_score.py --meta mix08_r11c_meta.json --out /tmp/spectral.json
  python3 spectral_score.py --meta mix08_r11c_meta.json --blends 12 --plot /tmp/t12.png
"""
from __future__ import annotations
import json, os, sys, subprocess
import numpy as np

SR = 44100
N_FFT = 4096
HOP = 1024
# 24 log-spaced auditory bands, ~30 Hz to 15 kHz (Manabe appendix A)
BAND_EDGES_24 = np.geomspace(30.0, 15000.0, 25)
# Banger Lab clash() bands
BANDS_6 = [(20, 80), (80, 250), (250, 800), (800, 2500), (2500, 7000), (7000, 20000)]
BAND_EDGES_6 = np.array([20.0, 80.0, 250.0, 800.0, 2500.0, 7000.0, 20000.0])
# Default score scales (overwritten by src/calib/spectral_scales.json after calibration)
S_TARGET = 0.70  # score assigned to a penalty equal to the pro median
EPS = 1e-12
HERE = os.path.dirname(os.path.abspath(__file__))
SCALES_PATH = os.path.join(HERE, '..', 'src', 'calib', 'spectral_scales.json')
# Activity thresholds for optional transition detection (Manabe appendix A)
TAU_ON, TAU_OFF = 0.20, 0.10
L_ON_S, L_OFF_S = 0.50, 0.75
GAIN_LAM = 1.0  # temporal smoothness in the contribution fit (eq. 5)
GAIN_MAX = 3.0


def _load_scales(path=SCALES_PATH):
    if path and os.path.exists(path):
        try:
            d = json.load(open(path))
            return dict(s_col=float(d['s_col']), s_cty=float(d['s_cty']),
                        source=path, n_pro=d.get('n_pro'), note=d.get('note'))
        except (KeyError, ValueError, OSError):
            pass
    return dict(s_col=0.02, s_cty=0.30, source='default', n_pro=0,
                note='uncalibrated defaults; run src/calib/spectral_vs_pro.py')


def scales_from_penalties(pcol, pcty, target=S_TARGET):
    """s such that exp(-median(p)/s) == target. Returns None scales if empty."""
    def s(vals):
        v = np.asarray(list(vals), float)
        v = v[np.isfinite(v)]
        if not len(v):
            return None
        med = float(np.median(v))
        return None if med <= 0 else med / -np.log(target)

    return dict(s_col=s(pcol), s_cty=s(pcty), target=target)


def mid(y):
    y = np.asarray(y)
    if y.ndim == 1:
        return y.astype(np.float64, copy=False)
    return (y[:, 0] + y[:, 1]) * (0.5 ** 0.5)


def _mono44(y, sr):
    y = mid(y)
    if int(sr) == SR:
        return np.ascontiguousarray(y, np.float64)
    n = int(round(len(y) * SR / sr))
    if n <= 1 or len(y) <= 1:
        return np.zeros(max(n, 0), np.float64)
    t = np.linspace(0, len(y) - 1, n)
    return np.interp(t, np.arange(len(y)), y).astype(np.float64)


def load_audio(path, sr=SR):
    """Mono float64 at sr. wav/flac via soundfile, otherwise ffmpeg."""
    path = str(path)
    if path.endswith('.wav') or path.endswith('.flac'):
        import soundfile as sf
        x, file_sr = sf.read(path, dtype='float32', always_2d=True)
        return _mono44(x, file_sr) if sr == SR else mid(x)
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def band_edges_from(kind='24'):
    return np.array(BAND_EDGES_24 if kind in ('24', 24, 'manabe') else BAND_EDGES_6, float)


def band_weights(edges, mode='collision'):
    """ω_b: double weight below ~200 Hz, mild emphasis up to ~1 kHz (appendix A).
    Continuity uses flatter ν_b (still a little low-band emphasis)."""
    lo, hi = edges[:-1], edges[1:]
    fc = np.sqrt(lo * hi)
    w = np.ones(len(fc))
    if mode == 'collision':
        w = np.where(fc < 200.0, 2.0, np.where(fc < 1000.0, 1.5, 1.0))
    else:
        w = np.where(fc < 200.0, 1.5, np.where(fc < 1000.0, 1.2, 1.0))
    return w


def stft_mag(y, sr=SR, n_fft=N_FFT, hop=HOP):
    from scipy.signal import stft
    y = np.ascontiguousarray(np.asarray(y, float), float)
    if len(y) < n_fft:
        y = np.pad(y, (0, n_fft - len(y)))
    freqs, times, Z = stft(y, fs=sr, window='hann', nperseg=n_fft,
                           noverlap=n_fft - hop, boundary=None, padded=False)
    return freqs, times, np.abs(Z.T)  # frames x bins


def band_energy(freqs, mag, edges):
    E = np.zeros((mag.shape[0], len(edges) - 1), float)
    for b, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (freqs >= lo) & (freqs < hi)
        if m.any():
            E[:, b] = np.sum(mag[:, m] ** 2, axis=1)
    return E


def analysis(y, sr=SR, edges=None, n_fft=N_FFT, hop=HOP):
    edges = BAND_EDGES_24 if edges is None else np.asarray(edges, float)
    freqs, times, mag = stft_mag(y, sr, n_fft, hop)
    return dict(freqs=freqs, times=times, mag=mag, energy=band_energy(freqs, mag, edges),
                edges=edges, sr=sr, hop=hop, n_fft=n_fft)


def _nnls(A, b):
    from scipy.optimize import nnls
    try:
        g, _ = nnls(A, b)
    except Exception:
        return np.zeros(A.shape[1])
    return np.clip(np.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0), 0.0, GAIN_MAX)


def fit_band_gains(mag_c, mag_a, mag_b, freqs, edges, lam=GAIN_LAM):
    """Smooth non-negative per-band amplitude gains (Manabe eq. 5, causal)."""
    n_fr = mag_c.shape[0]
    n_b = len(edges) - 1
    gA = np.zeros((n_fr, n_b))
    gB = np.zeros((n_fr, n_b))
    eye = np.sqrt(lam) * np.eye(2)
    for b, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (freqs >= lo) & (freqs < hi)
        if not m.any():
            continue
        A, B, C = mag_a[:, m], mag_b[:, m], mag_c[:, m]
        prev = np.zeros(2)
        for i in range(n_fr):
            X = np.vstack([np.stack([A[i], B[i]], 1), eye])
            y = np.concatenate([C[i], np.sqrt(lam) * prev])
            prev = _nnls(X, y)
            gA[i, b], gB[i, b] = prev
    return gA, gB


def occupancies(E, eps=EPS):
    denom = E.sum(axis=1, keepdims=True) + eps
    return E / denom


def contributed(energy, gain=None):
    """Band energy after amplitude gain: e' = (g * source)^2 energy."""
    if gain is None:
        return np.asarray(energy, float)
    return np.asarray(gain, float) ** 2 * np.asarray(energy, float)


def ratios(eA, eB, eps=EPS):
    tot = eA + eB + eps
    return eA / tot, eB / tot


def activity(rA, rB, pi=None):
    """Frame-level transition activity μ = min(r̄A, r̄B) (eq. 9)."""
    if pi is None:
        pi = np.full(rA.shape[1], 1.0 / rA.shape[1])
    pi = pi / (pi.sum() + EPS)
    rA_bar = rA @ pi
    rB_bar = rB @ pi
    return np.minimum(rA_bar, rB_bar), rA_bar, rB_bar


def detect_span(mu, times, tau_on=TAU_ON, tau_off=TAU_OFF, l_on=L_ON_S, l_off=L_OFF_S):
    """ms, me as times (seconds). None, None if no activation run is long enough."""
    if len(mu) == 0:
        return None, None
    hop = float(times[1] - times[0]) if len(times) > 1 else 1.0 / SR * HOP
    n_on, n_off = max(1, int(round(l_on / hop))), max(1, int(round(l_off / hop)))
    on = mu > tau_on
    start = None
    run = 0
    for i, v in enumerate(on):
        run = run + 1 if v else 0
        if run >= n_on:
            start = i - n_on + 1
            break
    if start is None:
        return None, None
    end = len(mu) - 1
    run = 0
    for i in range(start + n_on, len(mu)):
        run = run + 1 if mu[i] < tau_off else 0
        if run >= n_off:
            end = i - n_off + 1
            break
    return float(times[start]), float(times[min(end, len(times) - 1)])


def collision_frame(rA, rB, qA, qB, omega):
    """Per-frame collision term (the inner sum of eq. 16)."""
    shared = np.minimum(qA, qB)
    return np.sum(omega * rA * rB * shared, axis=1)


def collision_penalty(rA, rB, qA, qB, omega, mask=None):
    term = collision_frame(rA, rB, qA, qB, omega)
    if mask is None:
        used = term
    else:
        used = term[np.asarray(mask, bool)]
    return float(np.mean(used)) if len(used) else 0.0, term


def log_band(E, eps=EPS):
    return np.log(np.asarray(E, float) + eps)


def continuity_templates(logE, mask):
    mask = np.asarray(mask, bool)
    if mask.sum() < 2:
        return None
    return np.median(logE[mask], axis=0)


def continuity_penalty(logC, uA, uB, nu, mask=None):
    """pcty (eq. 22) and the per-frame mean absolute log-band error."""
    n = logC.shape[0]
    idx = np.flatnonzero(mask) if mask is not None else np.arange(n)
    if len(idx) == 0 or uA is None or uB is None:
        return 0.0, np.full(n, np.nan)
    alpha = np.zeros(n)
    a0, a1 = idx[0], idx[-1]
    span = max(a1 - a0, 1)
    alpha[a0:a1 + 1] = np.arange(a1 - a0 + 1) / span
    ustar = (1.0 - alpha[:, None]) * uA + alpha[:, None] * uB
    err = np.abs(logC - ustar) @ (nu / max(len(nu), 1))
    return float(np.mean(err[idx])), err


def continuity_fallback(logC, logA, logB, rA, rB, nu, mask=None):
    """Contemporaneous contribution-weighted trajectory (paper §5.3 fallback)."""
    rA_b, rB_b = rA, rB
    ustar = rA_b * logA + rB_b * logB
    err = np.abs(logC - ustar) @ (nu / max(len(nu), 1))
    if mask is not None:
        m = np.asarray(mask, bool)
        return (float(np.mean(err[m])) if m.any() else 0.0), err
    return float(np.mean(err)) if len(err) else 0.0, err


def _to_score(penalty, scale):
    if scale is None or scale <= 0 or not np.isfinite(penalty):
        return None
    return float(np.exp(-float(penalty) / scale))


def banger_clash(eA, eB, times, beat_s, floor_db=-40.0, rel_db=20.0):
    """Fraction of (beat, band) cells where both decks fill the band.

    A deck 'fills' a band on a beat when that beat's energy is within rel_db of
    the deck's own peak in the band, and above floor_db vs the clip peak.
    Low and low-mid bands (the first two of BANDS_6) are double-weighted.
    """
    if beat_s <= 0 or len(times) < 2:
        return dict(rate=0.0, per_beat=np.zeros(0), n_beats=0)
    t1 = float(times[-1] + (times[1] - times[0]))
    n_beats = int(np.floor(t1 / beat_s + 1e-9))
    if n_beats <= 0:
        return dict(rate=0.0, per_beat=np.zeros(0), n_beats=0)
    n_b = eA.shape[1]
    w = np.array([2.0 if b < 2 else 1.0 for b in range(n_b)])
    peak = max(float(eA.max()), float(eB.max()), EPS)
    abs_floor = peak * 10 ** (floor_db / 10.0)
    rel_a = (eA.max(axis=0) + EPS) * 10 ** (-rel_db / 10.0)
    rel_b = (eB.max(axis=0) + EPS) * 10 ** (-rel_db / 10.0)
    per = np.zeros(n_beats)
    hits = weight_sum = 0.0
    for k in range(n_beats):
        m = (times >= k * beat_s) & (times < (k + 1) * beat_s)
        if not m.any():
            continue
        a, b = eA[m].mean(0), eB[m].mean(0)
        fill_a = (a >= abs_floor) & (a >= rel_a)
        fill_b = (b >= abs_floor) & (b >= rel_b)
        clash = fill_a & fill_b
        per[k] = float(np.dot(clash, w) / (w.sum() + EPS))
        hits += float(np.dot(clash, w))
        weight_sum += float(w.sum())
    rate = hits / weight_sum if weight_sum else 0.0
    return dict(rate=float(rate), per_beat=per, n_beats=n_beats)


def _frame_mask(times, start_s, end_s):
    return (times >= start_s) & (times < end_s)


def _bar_reduce(times, values, bar_s, t0=0.0, t1=None):
    """Mean of per-frame values in each bar, starting at t0. NaN if a bar is empty."""
    if t1 is None:
        t1 = float(times[-1]) if len(times) else t0
    n = int(np.ceil((t1 - t0) / bar_s - 1e-9)) if bar_s > 0 else 0
    n = max(n, 0)
    out = np.full(n, np.nan)
    if n == 0 or len(times) == 0:
        return out
    for k in range(n):
        m = (times >= t0 + k * bar_s) & (times < t0 + (k + 1) * bar_s)
        if m.any() and np.isfinite(values[m]).any():
            out[k] = float(np.nanmean(values[m]))
    return out


def score_energies(eA, eB, eC, times, bar_s, start_s, end_s,
                   pre_s=None, post_s=None, edges=None, scales=None,
                   beat_s=None, eA6=None, eB6=None, times6=None):
    """Collision / continuity from already-contributed band energies (g already applied)."""
    edges = BAND_EDGES_24 if edges is None else np.asarray(edges, float)
    scales = scales or _load_scales()
    omega, nu = band_weights(edges, 'collision'), band_weights(edges, 'continuity')
    qA, qB = occupancies(eA), occupancies(eB)
    rA, rB = ratios(eA, eB)
    mu, rA_bar, rB_bar = activity(rA, rB)
    t0 = 0.0 if start_s is None else float(start_s)
    t1 = float(times[-1]) if end_s is None and len(times) else (float(end_s) if end_s is not None else 0.0)
    if start_s is None or end_s is None:
        det0, det1 = detect_span(mu, times)
        if start_s is None:
            t0 = det0 if det0 is not None else (float(times[0]) if len(times) else 0.0)
        if end_s is None:
            t1 = det1 if det1 is not None else (float(times[-1]) if len(times) else t0)
    if t1 <= t0 and len(times):
        t1 = float(times[-1])
    mask = _frame_mask(times, t0, t1)
    pcol, col_fr = collision_penalty(rA, rB, qA, qB, omega, mask)
    logA, logB, logC = log_band(eA), log_band(eB), log_band(eC)
    # pre / post windows: prefer a short run of A-only / B-only, else the provided pads
    pre0 = 0.0 if pre_s is None else max(0.0, t0 - float(pre_s))
    post1 = (float(times[-1]) if len(times) else t1) if post_s is None else t1 + float(post_s)
    a_only = (rA_bar > 0.80) & (rB_bar < 0.20) & (times >= pre0) & (times < t0)
    b_only = (rB_bar > 0.80) & (rA_bar < 0.20) & (times >= t1) & (times <= post1)
    # keep at most 4 bars of template
    if beat_s is None:
        beat_s = bar_s / 4.0 if bar_s else 60.0 / 174.0
    max_tpl = 4.0 * bar_s if bar_s else 4.0
    if a_only.any():
        last = times[a_only][-1]
        a_only = a_only & (times >= last - max_tpl)
    if b_only.any():
        first = times[b_only][0]
        b_only = b_only & (times <= first + max_tpl)
    uA, uB = continuity_templates(logA, a_only), continuity_templates(logB, b_only)
    used_fallback = uA is None or uB is None
    if used_fallback:
        pcty, cty_fr = continuity_fallback(logC, logA, logB, rA, rB, nu, mask)
    else:
        pcty, cty_fr = continuity_penalty(logC, uA, uB, nu, mask)
    col_bar = _bar_reduce(times, col_fr, bar_s, 0.0, (float(times[-1]) if len(times) else 0.0) + 1e-9)
    cty_bar = _bar_reduce(times, cty_fr, bar_s, 0.0, (float(times[-1]) if len(times) else 0.0) + 1e-9)
    clash = banger_clash(eA6 if eA6 is not None else eA,
                         eB6 if eB6 is not None else eB,
                         times6 if times6 is not None else times,
                         beat_s)
    scol = _to_score(pcol, scales.get('s_col'))
    scty = _to_score(pcty, scales.get('s_cty'))
    return dict(
        diagnostic_only=True,
        pcol=round(float(pcol), 6),
        pcty=round(float(pcty), 6),
        Scol=None if scol is None else round(scol, 4),
        Scty=None if scty is None else round(scty, 4),
        banger_clash_rate=round(float(clash['rate']), 4),
        start_s=round(float(t0), 3),
        end_s=round(float(t1), 3),
        n_frames=int(mask.sum()),
        continuity_fallback=bool(used_fallback),
        scales=dict(s_col=scales.get('s_col'), s_cty=scales.get('s_cty'),
                    source=scales.get('source'), note=scales.get('note')),
        collision_frame=col_fr,
        continuity_frame=cty_fr,
        collision_bar=col_bar,
        continuity_bar=cty_bar,
        mu=mu,
        times=times,
        banger_per_beat=clash['per_beat'],
        beat_s=float(beat_s),
        bar_s=float(bar_s) if bar_s else None,
    )


def score_decks(ya, yb, sr=SR, bar_s=None, start_s=None, end_s=None,
                pre_s=None, post_s=None, yc=None, already_gained=True,
                scales=None, bpm=174.0):
    """Score two deck signals. If already_gained, they already include fader/EQ."""
    bar_s = (4.0 * 60.0 / bpm) if not bar_s else float(bar_s)
    a = _mono44(ya, sr)
    b = _mono44(yb, sr)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    c = _mono44(yc, sr)[:n] if yc is not None else (a + b)
    if not already_gained and yc is not None:
        an, bn, cn = analysis(a), analysis(b), analysis(c)
        gA, gB = fit_band_gains(cn['mag'], an['mag'], bn['mag'], an['freqs'], an['edges'])
        eA, eB = contributed(an['energy'], gA), contributed(bn['energy'], gB)
        times, eC = cn['times'], cn['energy']
        a6, b6 = analysis(a, edges=BAND_EDGES_6), analysis(b, edges=BAND_EDGES_6)
        gA6, gB6 = fit_band_gains(analysis(c, edges=BAND_EDGES_6)['mag'],
                                  a6['mag'], b6['mag'], a6['freqs'], a6['edges'])
        eA6, eB6, t6 = contributed(a6['energy'], gA6), contributed(b6['energy'], gB6), a6['times']
    else:
        an, bn, cn = analysis(a), analysis(b), analysis(c)
        eA, eB, eC, times = an['energy'], bn['energy'], cn['energy'], an['times']
        a6, b6 = analysis(a, edges=BAND_EDGES_6), analysis(b, edges=BAND_EDGES_6)
        eA6, eB6, t6 = a6['energy'], b6['energy'], a6['times']
    return score_energies(eA, eB, eC, times, bar_s, start_s, end_s,
                          pre_s=pre_s, post_s=post_s, scales=scales,
                          beat_s=bar_s / 4.0, eA6=eA6, eB6=eB6, times6=t6)


def score_mix_transition(meta, i, pre=8, post=8, scales=None):
    """Render the two decks of blend i (actual signals x gain/EQ) and score them."""
    import blend_diag
    from engine import BAR
    t = meta['trans'][i]
    s, e = float(t['start_bar']), float(t['end_bar'])
    s0, A, B = blend_diag.crop_decks(meta, i, pre=pre, post=post)
    bar_s = float(meta.get('bar_sec') or BAR)
    # crop starts at mix bar s0; blend is [s, e)
    res = score_decks(A, B, sr=SR, bar_s=bar_s,
                      start_s=(s - s0) * bar_s, end_s=(e - s0) * bar_s,
                      pre_s=pre * bar_s, post_s=post * bar_s,
                      already_gained=True, scales=scales)
    res.update(blend=i, a=t['a'], b=t['b'], start_bar=s, end_bar=e,
               crop_start_bar=s0, method='rendered_decks')
    return res, A, B, s0


def compact(res):
    """JSON-safe summary without the per-frame arrays."""
    skip = {'collision_frame', 'continuity_frame', 'mu', 'times', 'banger_per_beat',
            'collision_bar', 'continuity_bar'}
    out = {k: v for k, v in res.items() if k not in skip}
    for k in ('collision_bar', 'continuity_bar'):
        v = res.get(k)
        if v is not None:
            out[k] = [None if not np.isfinite(x) else round(float(x), 5) for x in np.asarray(v)]
    return out


def plot_lanes(res, out_png, title=None, x0_bar=0.0):
    """Standalone per-bar collision / continuity lane (and a μ trace)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bar_s = res.get('bar_s') or 4 * 60 / 174
    col, cty = np.asarray(res['collision_bar'], float), np.asarray(res['continuity_bar'], float)
    xb = x0_bar + np.arange(len(col))
    fig, ax = plt.subplots(2, 1, figsize=(11, 5.2), sharex=True)
    ax[0].step(xb, col, where='post', color='tab:orange', label='collision penalty')
    ax[0].step(xb, cty, where='post', color='tab:purple', label='continuity penalty')
    s0, s1 = res.get('start_s'), res.get('end_s')
    if s0 is not None and s1 is not None and bar_s:
        ax[0].axvspan(x0_bar + s0 / bar_s, x0_bar + s1 / bar_s, color='orange', alpha=0.12, label='blend window')
    ax[0].set_ylabel('penalty (higher=worse)')
    ax[0].legend(fontsize=7, loc='upper right')
    ax[0].grid(alpha=.3)
    scol, scty, br = res.get('Scol'), res.get('Scty'), res.get('banger_clash_rate')
    ax[0].set_title(
        (title or 'spectral scores (diagnostic only)') +
        f"  Scol={scol}  Scty={scty}  pcol={res.get('pcol')}  pcty={res.get('pcty')}  "
        f"banger clash={br}",
        fontsize=9)
    times, mu = res.get('times'), res.get('mu')
    if times is not None and mu is not None:
        ax[1].plot(x0_bar + np.asarray(times) / bar_s, mu, color='k', lw=1, label='activity μ')
        ax[1].axhline(TAU_ON, color='tab:red', ls='--', lw=0.8, label='τon')
        ax[1].set_ylabel('μ')
        ax[1].legend(fontsize=7)
        ax[1].grid(alpha=.3)
    ax[-1].set_xlabel('mix bar')
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png) or '.', exist_ok=True)
    fig.savefig(out_png, dpi=90)
    plt.close(fig)
    return out_png


def add_diag_lane(ax, res, x0_bar=0.0):
    """Draw the collision / continuity lane onto an existing blend_diag axis."""
    bar_s = res.get('bar_s') or 4 * 60 / 174
    col = np.asarray(res.get('collision_bar'), float)
    cty = np.asarray(res.get('continuity_bar'), float)
    xb = x0_bar + np.arange(len(col))
    ax.step(xb, col, where='post', color='tab:orange', label='collision p')
    ax.step(xb, cty, where='post', color='tab:purple', label='continuity p')
    ax.set_ylabel('penalty')
    ax.legend(fontsize=7, loc='upper right')
    ax.grid(alpha=.3)
    ax.set_title(
        f"spectral (diag only, not a gate)  Scol={res.get('Scol')}  Scty={res.get('Scty')}  "
        f"pcol={res.get('pcol')}  pcty={res.get('pcty')}  banger clash={res.get('banger_clash_rate')}",
        fontsize=9)
    return ax


def score_mix(meta_path, blends=None, scales=None, plot_dir=None):
    meta = json.load(open(meta_path)) if isinstance(meta_path, str) else meta_path
    rows = []
    idxs = blends if blends is not None else range(len(meta['trans']))
    for i in idxs:
        t = meta['trans'][i]
        try:
            res, _, _, s0 = score_mix_transition(meta, i, scales=scales)
            if plot_dir:
                os.makedirs(plot_dir, exist_ok=True)
                plot_lanes(res, os.path.join(plot_dir, f"spectral_blend{i:02d}_{t['a']}_{t['b']}.png"),
                           title=f"blend {i}: {t['a']} -> {t['b']}", x0_bar=s0)
            rows.append(compact(res))
        except Exception as ex:
            rows.append(dict(diagnostic_only=True, blend=i, a=t.get('a'), b=t.get('b'),
                             error=f'{type(ex).__name__}: {ex}'[-240:]))
        print(json.dumps({k: rows[-1][k] for k in rows[-1] if k not in ('collision_bar', 'continuity_bar')},
                         default=float)[:400], flush=True)
    return rows


if __name__ == '__main__':
    import argparse
    os.chdir(HERE)
    ap = argparse.ArgumentParser()
    ap.add_argument('--meta', required=True)
    ap.add_argument('--out')
    ap.add_argument('--blends')
    ap.add_argument('--plot')
    a = ap.parse_args()
    blends = [int(x) for x in a.blends.split(',')] if a.blends else None
    rows = score_mix(a.meta, blends, plot_dir=a.plot)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        json.dump(rows, open(a.out, 'w'), indent=1, default=float)
