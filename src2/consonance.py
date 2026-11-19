"""CONSONANCE (2026-11-19 midnight research, off by default).

Small version of Gebhardt, Davies & Seeber, "Psychoacoustic Approaches for Harmonic Music Mixing",
Applied Sciences 6(5):123, May 2016: judge how two overlapping tracks sound together by the *sensory
roughness* between their spectral peaks (Plomp-Levelt curve, Sethares' parameterisation), instead of
key labels. No pitch shifting (the engine has none): we only use the score to rank candidate windows.

Per track, per bar (st/{id}.wav, same bar grid as engine._bars: d0 + k*BAR):
  * magnitude STFT (n_fft 8192 ~ 5.4 Hz bins, hop 2048), loudness-normalised like engine.LazySt (-16 LUFS);
  * median over the frames inside the bar -> sustained (tonal) content; kicks/snares/hats are short
    and mostly vanish under a median (a cheap HPSS stand-in, "ignore drums where possible");
  * mid band only, 150 Hz - 4 kHz (sub bass ignored: the engine's bass swap keeps one bassline anyway);
  * up to NPEAK local maxima within PEAK_DB of the bar's loudest peak.

Window roughness: for each blend bar k, the outgoing peaks are scaled by the equal-power crossfader gain
cos(x*pi/2) and the incoming by sin(x*pi/2), x=(k+0.5)/X; we sum the Sethares dissonance over the
*cross* pairs only (outgoing peak i vs incoming peak j; each track's own roughness is not our doing),
divide by the summed peak amplitude of that bar (scale-free), and average over the bars.

Hook: protrans/recreate.py (CONSONANCE=1, weight CONSONANCE_W) adds W*log(R(win)/R(default pick))
to each family's pick cost, and nominates one extra 'cons_cue' family: the most consonant natural
window with the same outgoing end/blend length as the default pick, if the engine scored it and its
guardrail penalty is not worse than the default's by more than CONS_PEN_SLACK. Nothing else changes.
"""
from __future__ import annotations

import math
import os

import numpy as np

SR = 44100
T = 174.0
BAR = 4 * 60 / T
NFFT = 8192
HOP = 2048
FMIN, FMAX = float(os.environ.get('CONS_FMIN', 150.0)), 4000.0  # CONS_FMIN: research knob (e.g. 400 = above bass harmonics)
NPEAK = 20
PEAK_DB = 30.0
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'protrans', 'cache', 'consonance')
VERSION = 1


def flag_on(v=None) -> bool:
    if v is None:
        v = os.environ.get('CONSONANCE')
    try:
        return bool(int(float(v or 0)))
    except (TypeError, ValueError):
        return str(v).strip().lower() in ('true', 'yes', 'on')


def weight(v=None) -> float:
    if v is None:
        v = os.environ.get('CONSONANCE_W')
    try:
        return float(v) if v not in (None, '') else 0.3
    except (TypeError, ValueError):
        return 0.3


# ---- Plomp-Levelt / Sethares dissonance -------------------------------------------------------------
B1, B2, DSTAR, S1, S2 = 3.5, 5.75, 0.24, 0.0207, 18.96


def pair_dissonance(f1, f2, a1, a2):
    """Sethares (1993/2005) dissonance of two partials (broadcasts). 0 at unison, peak near ~1/4 critical band,
    -> 0 for wide intervals. Amplitude term min(a1, a2)."""
    f1 = np.asarray(f1, float); f2 = np.asarray(f2, float)
    fmin = np.fmin(f1, f2); df = np.abs(f2 - f1)
    s = DSTAR / (S1 * fmin + S2)
    return np.fmin(a1, a2) * (np.exp(-B1 * s * df) - np.exp(-B2 * s * df))


def cross_roughness(fa, aa, fb, ab):
    """Sum of dissonance over cross pairs (peak of A vs peak of B)."""
    fa = np.asarray(fa, float); fb = np.asarray(fb, float)
    if fa.size == 0 or fb.size == 0:
        return 0.0
    aa = np.asarray(aa, float); ab = np.asarray(ab, float)
    return float(pair_dissonance(fa[:, None], fb[None, :], aa[:, None], ab[None, :]).sum())


# ---- spectral peaks per bar ---------------------------------------------------------------------------
def spectrum_peaks(mag, freqs, fmin=FMIN, fmax=FMAX, npeak=NPEAK, peak_db=PEAK_DB):
    """Local maxima of a magnitude spectrum inside [fmin, fmax], within peak_db of the largest, top npeak.
    Returns (freqs, amps) with a parabolic-interpolated frequency."""
    mag = np.asarray(mag, float); freqs = np.asarray(freqs, float)
    band = np.flatnonzero((freqs >= fmin) & (freqs <= fmax))
    if band.size < 3:
        return np.zeros(0), np.zeros(0)
    i = band[1:-1]
    loc = i[(mag[i] > mag[i - 1]) & (mag[i] >= mag[i + 1])]
    if loc.size == 0 or mag[loc].max() <= 0:
        return np.zeros(0), np.zeros(0)
    top = mag[loc].max()
    loc = loc[20 * np.log10(mag[loc] / top + 1e-12) > -peak_db]
    loc = loc[np.argsort(mag[loc])[::-1][:npeak]]
    df = freqs[1] - freqs[0]
    lm = np.log(mag[loc - 1] + 1e-12); l0 = np.log(mag[loc] + 1e-12); lp = np.log(mag[loc + 1] + 1e-12)
    den = lm - 2 * l0 + lp
    off = np.where(np.abs(den) > 1e-12, 0.5 * (lm - lp) / np.where(np.abs(den) > 1e-12, den, 1), 0.0)
    return freqs[loc] + np.clip(off, -0.5, 0.5) * df, mag[loc]


def bar_peaks_from_audio(y, d0, nb, sr=SR):
    """y mono float; returns list (per bar) of (freqs, amps) from the median spectrum of the bar's frames."""
    win = np.hanning(NFFT).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    out = []
    for k in range(nb):
        s0 = int(round((d0 + k * BAR) * sr)); s1 = int(round((d0 + (k + 1) * BAR) * sr))
        seg = y[max(0, s0):max(0, s1)]
        if len(seg) < NFFT:
            out.append((np.zeros(0), np.zeros(0))); continue
        idx = np.arange(0, len(seg) - NFFT + 1, HOP)
        fr = np.stack([seg[j:j + NFFT] * win for j in idx])
        mag = np.median(np.abs(np.fft.rfft(fr, axis=1)), axis=0) / (NFFT / 4)
        out.append(spectrum_peaks(mag, freqs))
    return out


_MEM = {}


def track_peaks(yt, st_dir=None):
    """Cached per-bar peaks for st/{yt}.wav (loudness-normalised to -16 LUFS like the engine)."""
    if yt in _MEM:
        return _MEM[yt]
    os.makedirs(CACHE, exist_ok=True)
    cf = os.path.join(CACHE, f'{yt}.v{VERSION}.npz' if FMIN == 150.0 else f'{yt}.v{VERSION}.f{int(FMIN)}.npz')
    st_dir = st_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'st')
    if os.path.exists(cf):
        z = np.load(cf, allow_pickle=True); P = list(z['peaks'])
    else:
        import json
        import soundfile as sf
        import pyloudnorm as pyln
        g = json.load(open(os.path.join(st_dir, f'{yt}.json')))
        y, sr = sf.read(os.path.join(st_dir, f'{yt}.wav'), dtype='float32', always_2d=True)
        gain = 10 ** ((-16 - pyln.Meter(sr).integrated_loudness(y)) / 20)
        P = bar_peaks_from_audio(y.mean(axis=1) * gain, g['downs'][0], len(g['downs']), sr)
        arr = np.empty(len(P), dtype=object); arr[:] = P
        tmp = cf + f'.tmp{os.getpid()}.npz'
        np.savez(tmp, peaks=arr); os.replace(tmp, cf)
    _MEM[yt] = P
    return P


# ---- window score -------------------------------------------------------------------------------------
def window_bars(win):
    """[kind, e, loop_p, ib, X] -> (outgoing bar list, incoming bar list), same layout as mix_simple.pair_cands
    ('lx' uses the plain outgoing bars before e: an approximation, its loop is a drums+bass stem)."""
    kind, e, p, ib, X = win[0], int(win[1]), win[2], int(win[3]), int(win[4])
    wa = [int(p) + (k % 16) for k in range(X)] if kind in ('la', 'ab') and p is not None else list(range(e - X, e))
    wb = [ib + (k % 16) for k in range(X)] if kind in ('lb', 'ab') else list(range(ib, ib + X))
    return wa, wb


def window_roughness(PA, PB, wa, wb, gains=None):
    """Mean over blend bars of crossfaded cross-roughness / summed peak amplitude. None if no usable bar."""
    X = len(wa); vals = []
    for k, (xa, xb) in enumerate(zip(wa, wb)):
        if gains is None:
            x = (k + 0.5) / X; ga, gb = math.cos(x * math.pi / 2), math.sin(x * math.pi / 2)
        else:
            ga, gb = gains[k]
        if not (0 <= xa < len(PA) and 0 <= xb < len(PB)):
            continue
        fa, aa = PA[xa]; fb, ab = PB[xb]
        tot = ga * float(np.sum(aa)) + gb * float(np.sum(ab))
        if tot <= 0:
            continue
        vals.append(cross_roughness(fa, ga * np.asarray(aa), fb, gb * np.asarray(ab)) / tot)
    return float(np.mean(vals)) if vals else None


def win_roughness(a, b, win):
    wa, wb = window_bars(win)
    return window_roughness(track_peaks(a), track_peaks(b), wa, wb)


def cost_term(r, r_ref, w):
    """W * log(R / R_ref); 0 when either is missing."""
    if r is None or r_ref is None or r <= 0 or r_ref <= 0 or not w:
        return 0.0
    return float(w) * math.log(r / r_ref)


def cons_cue(cs, default_win, a, b, pen_slack=15.0):
    """Most consonant natural window with the default pick's outgoing end and blend length, among windows the
    engine scored (cs: blend_bench candidate dicts with 'win' and 'pen'), whose guardrail penalty is within
    pen_slack of the default's. Returns (win, R) or (None, None) when nothing beats the default."""
    if not default_win or default_win[0] != 'n':
        return None, None
    dpen = next((float(c.get('pen', 0)) for c in cs if list(c['win']) == list(default_win)), None)
    if dpen is None:
        return None, None
    r_def = win_roughness(a, b, default_win)
    best, rbest = None, r_def
    for c in cs:
        w = list(c['win'])
        if w[0] != 'n' or w[1] != default_win[1] or w[4] != default_win[4] or w == list(default_win):
            continue
        if c.get('planner_extra') or float(c.get('pen', 0)) > dpen + pen_slack:
            continue
        r = win_roughness(a, b, w)
        if r is not None and (rbest is None or r < rbest):
            best, rbest = w, r
    return (best, rbest) if best is not None else (None, None)
