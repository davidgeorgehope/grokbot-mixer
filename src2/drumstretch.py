"""Transient-preserving drum timestretch (Tero Parviainen, 2026-11-11).

Cut at every drum hit, copy each hit sample-for-sample, and stretch only the
decays between hits. Decays are split into a tonal ("ring") part and a noise
("percussive residue") part with median-filter HPSS (Fitzgerald 2010;
Driedger, Müller and Ewert 2014) via libtsm.hps. The noise part is stretched
with overlap-add (libtsm.wsola_tsm, tol=0) and the tonal part with a phase
vocoder with identity phase locking (libtsm.pv_tsm).

This is the explicit-onset variant of the HPTSM idea: hits stay unstretched
and unrelocated relative to themselves; only the gaps move. Prep still uses
Rubber Band (`rubberband -3 -F -T ratio -q`); this module is the prototype
to A/B against that, ahead of per-bar pitch-ride.
"""
from __future__ import annotations
import numpy as np

SR_DEFAULT = 44100
HIT_PRE_MS = 4.0
HIT_POST_MS = 16.0
FADE_MS = 1.0
MIN_TSM = 64
# Driedger 2014 / libtsm.hps_tsm defaults
PV_SYN_HOP, PV_WIN, PV_BETA = 512, 2048, 2
OLA_SYN_HOP, OLA_WIN, OLA_BETA = 128, 256, 2
HPS_HOP, HPS_WIN, HPS_BETA = 256, 1024, 2
HPS_FILT = 10

def _mono(y):
    y = np.asarray(y)
    if y.ndim == 2:
        return np.mean(y, axis=1 if y.shape[1] <= 8 else 0)
    return y.reshape(-1)

def as_nc(y):
    """Return (n, c) float64 and a tag so the original layout can be restored."""
    y = np.asarray(y)
    if y.ndim == 1:
        return y.reshape(-1, 1).astype(np.float64, copy=False), '1d'
    if y.ndim == 2 and y.shape[0] < y.shape[1] and y.shape[0] <= 8:
        return y.T.astype(np.float64, copy=False), 'cn'
    return y.astype(np.float64, copy=False), 'nc'

def from_nc(y, layout, like=None):
    if layout == '1d':
        y = np.asarray(y).reshape(-1)
    elif layout == 'cn':
        y = np.asarray(y).T
    else:
        y = np.asarray(y)
    if like is not None:
        y = y.astype(np.asarray(like).dtype, copy=False)
    return y

def _fit_len(y, n):
    y = np.asarray(y)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    if y.shape[0] == n:
        return y
    out = np.zeros((n, y.shape[1]), dtype=y.dtype)
    m = min(n, y.shape[0])
    out[:m] = y[:m]
    return out

def _resample(y, nout):
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    n = y.shape[0]
    if nout == n:
        return y
    if n <= 1:
        return np.repeat(y, nout, axis=0) if n == 1 else np.zeros((nout, y.shape[1]))
    t = np.linspace(0, n - 1, nout)
    idx = np.arange(n, dtype=np.float64)
    return np.column_stack([np.interp(t, idx, y[:, c]) for c in range(y.shape[1])])

def edge_fade(y, sr, ms=FADE_MS):
    y = np.asarray(y, dtype=np.float64).copy()
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    nfade = int(round(ms * 1e-3 * sr))
    nfade = min(nfade, max(0, y.shape[0] // 2))
    if nfade <= 0:
        return y
    w = np.linspace(0, 1, nfade, dtype=np.float64)
    y[:nfade] *= w[:, None]
    y[-nfade:] *= w[::-1][:, None]
    return y

def detect_hits(y, sr, hop=64, wait_ms=20.0, delta=0.07, refine_ms=6.0):
    """Onset sample indices, refined to a local high-passed peak."""
    import librosa
    from scipy.signal import butter, filtfilt
    mono = np.asarray(_mono(y), dtype=np.float64)
    if mono.size < hop * 4:
        return np.zeros(0, dtype=int)
    oe = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=hop)
    wait = max(1, int(round(wait_ms * 1e-3 * sr / hop)))
    frames = librosa.onset.onset_detect(
        onset_envelope=oe, sr=sr, hop_length=hop, backtrack=True,
        units='frames', pre_max=wait, post_max=wait, wait=wait, delta=delta)
    if len(frames) == 0:
        return np.zeros(0, dtype=int)
    samples = librosa.frames_to_samples(frames, hop_length=hop)
    # high-pass so the peak is the click, not a slow kick body
    b, a = butter(2, 800 / (sr / 2), btype='high')
    try:
        hp = filtfilt(b, a, mono)
    except ValueError:
        hp = np.diff(mono, prepend=mono[:1])
    rad = int(round(refine_ms * 1e-3 * sr))
    refined = []
    n = len(mono)
    for s in samples:
        lo, hi = max(0, int(s) - rad), min(n, int(s) + rad + 1)
        if hi <= lo:
            continue
        refined.append(lo + int(np.argmax(np.abs(hp[lo:hi]))))
    return np.unique(np.asarray(refined, dtype=int))

def out_onset(onset, alpha):
    return int(round(int(onset) * float(alpha)))

def allocate_windows(onsets, n, sr, alpha, pre_ms=HIT_PRE_MS, post_ms=HIT_POST_MS):
    """Hit windows that stay the same length in input and output, without overlap."""
    pre0 = max(1, int(round(pre_ms * 1e-3 * sr)))
    post0 = max(1, int(round(post_ms * 1e-3 * sr)))
    nout = int(round(n * alpha))
    hits = []
    for o in onsets:
        o = int(o)
        if o < 0 or o >= n:
            continue
        pre, post = pre0, post0
        pre = min(pre, o)
        post = min(post, n - o)
        if pre + post <= 0:
            continue
        hits.append(dict(onset=o, pre=pre, post=post))
    if not hits:
        return [], nout

    def pack():
        wins = []
        for h in hits:
            o, pre, post = h['onset'], h['pre'], h['post']
            oo = out_onset(o, alpha)
            wins.append(dict(
                onset=o, pre=pre, post=post,
                in_start=o - pre, in_end=o + post,
                out_onset=oo, out_start=oo - pre, out_end=oo + post))
        return wins

    # shrink neighbouring hits until input and output ranges do not overlap
    changed = True
    guard = 0
    while changed and guard < 1000:
        changed = False
        guard += 1
        wins = pack()
        for i in range(len(wins) - 1):
            a, b = wins[i], wins[i + 1]
            overlap_in = a['in_end'] - b['in_start']
            overlap_out = a['out_end'] - b['out_start']
            need = max(0, overlap_in, overlap_out)
            if need <= 0:
                continue
            # take samples from the facing sides, keep at least 1 sample on a hit
            take_a = min(need // 2 + need % 2, max(0, hits[i]['post'] - 1))
            take_b = min(need - take_a, max(0, hits[i + 1]['pre'] - 1))
            take_a = min(need - take_b, max(0, hits[i]['post'] - 1))
            if take_a == 0 and take_b == 0:
                continue
            hits[i]['post'] -= take_a
            hits[i + 1]['pre'] -= take_b
            changed = True
    wins = pack()
    # drop hits that would sit entirely outside the output buffer
    kept = []
    for w in wins:
        if w['out_end'] <= 0 or w['out_start'] >= nout:
            continue
        kept.append(w)
    return kept, nout

def stretch_parts(harm, perc, sr, length):
    """Stretch tonal (PV) and noise (OLA) parts to an exact sample length."""
    import libtsm
    harm = np.asarray(harm, dtype=np.float64)
    perc = np.asarray(perc, dtype=np.float64)
    if harm.ndim == 1:
        harm = harm.reshape(-1, 1)
    if perc.ndim == 1:
        perc = perc.reshape(-1, 1)
    n = harm.shape[0]
    length = int(length)
    if length <= 0:
        return np.zeros((0, harm.shape[1]), dtype=np.float64)
    if n == 0:
        return np.zeros((length, harm.shape[1]), dtype=np.float64)
    if length == n:
        return harm + perc
    if n < MIN_TSM or length < MIN_TSM:
        return _resample(harm + perc, length)
    alpha = length / n
    y_h = libtsm.pv_tsm(
        harm, alpha, syn_hop=PV_SYN_HOP, win_length=PV_WIN, win_beta=PV_BETA,
        Fs=sr, phase_locking=True)
    y_p = libtsm.wsola_tsm(
        perc, alpha, syn_hop=OLA_SYN_HOP, win_length=OLA_WIN, win_beta=OLA_BETA, tol=0)
    y = np.asarray(y_h, dtype=np.float64) + np.asarray(y_p, dtype=np.float64)
    return libtsm.normalize_length(y, length)

def _hps(y, sr):
    import libtsm
    harm, perc = libtsm.hps(
        y, ana_hop=HPS_HOP, win_length=HPS_WIN, win_beta=HPS_BETA, Fs=sr,
        fil_len_harm=HPS_FILT, fil_len_perc=HPS_FILT, masking_mode='binary')
    n = y.shape[0]
    return _fit_len(harm, n), _fit_len(perc, n)

def _emit_stretch(out, harm, perc, sr, in0, in1, out0, out1):
    nout, _ = out.shape
    if out1 <= out0:
        return
    L = out1 - out0
    if in1 <= in0:
        return
    stretched = stretch_parts(harm[in0:in1], perc[in0:in1], sr, L)
    stretched = edge_fade(stretched, sr, FADE_MS)
    a, b = 0, L
    if out0 < 0:
        a = -out0
        out0 = 0
    if out1 > nout:
        b -= (out1 - nout)
        out1 = nout
    if out1 > out0 and b > a:
        out[out0:out1] += stretched[a:b]

def stretch(y, sr, alpha, onsets=None, pre_ms=HIT_PRE_MS, post_ms=HIT_POST_MS):
    """Time-stretch `y` by `alpha` (output length / input length), pitch unchanged.

    Hits at `onsets` (sample indices; detected if omitted) are copied verbatim
    to `round(onset * alpha)`. Returns `(y_out, info)`.
    """
    alpha = float(alpha)
    y_nc, layout = as_nc(y)
    n, c = y_nc.shape
    if n == 0:
        return y.copy() if hasattr(y, 'copy') else y_nc, dict(onsets=[], windows=[], alpha=alpha, n=0, nout=0)
    nout = int(round(n * alpha))
    if abs(alpha - 1.0) < 1e-12:
        info = dict(onsets=[] if onsets is None else list(map(int, onsets)),
                    windows=[], alpha=1.0, n=n, nout=n, identity=True)
        return from_nc(y_nc, layout, y), info
    if onsets is None:
        onsets = detect_hits(y_nc, sr)
    onsets = np.asarray(onsets, dtype=int)
    wins, nout = allocate_windows(onsets, n, sr, alpha, pre_ms=pre_ms, post_ms=post_ms)
    harm, perc = _hps(y_nc, sr)
    out = np.zeros((nout, c), dtype=np.float64)
    if not wins:
        _emit_stretch(out, harm, perc, sr, 0, n, 0, nout)
    else:
        _emit_stretch(out, harm, perc, sr, 0, wins[0]['in_start'], 0, wins[0]['out_start'])
        for i in range(len(wins) - 1):
            _emit_stretch(out, harm, perc, sr,
                          wins[i]['in_end'], wins[i + 1]['in_start'],
                          wins[i]['out_end'], wins[i + 1]['out_start'])
        _emit_stretch(out, harm, perc, sr, wins[-1]['in_end'], n, wins[-1]['out_end'], nout)
        # overwrite hits last so they stay sample-exact
        for w in wins:
            src = y_nc[w['in_start']:w['in_end']]
            o0, o1 = w['out_start'], w['out_end']
            s0, s1 = 0, src.shape[0]
            if o0 < 0:
                s0 = -o0
                o0 = 0
            if o1 > nout:
                s1 -= (o1 - nout)
                o1 = nout
            if o1 > o0 and s1 > s0:
                out[o0:o1] = src[s0:s1]
    info = dict(onsets=[int(w['onset']) for w in wins], windows=wins,
                alpha=alpha, n=n, nout=nout, sr=sr)
    return from_nc(out, layout, y), info

def stretch_tempo(y, sr, from_bpm, to_bpm, **kw):
    """Change tempo from `from_bpm` to `to_bpm` (same idea as rubberband -T to/from)."""
    from_bpm, to_bpm = float(from_bpm), float(to_bpm)
    alpha = from_bpm / to_bpm
    return stretch(y, sr, alpha, **kw)

def expected_length(n, alpha):
    return int(round(int(n) * float(alpha)))
