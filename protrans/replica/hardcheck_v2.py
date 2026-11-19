"""Hard checks v2 (2026-11-18 late). Flag-only research detectors; hardcheck.py (v1) is left as it was.
  bass hole : per-bar deficit of the summed lows (<150 Hz) vs the blend's own body level (median of the bars outside the
              overlap), with a duration term: score = largest sum over one consecutive run of bars of (deficit - T0).
  beat clash: per-bar drum-onset phase. For each bar where both decks are audible, the phase of each deck's onset envelope
              (kick 30-150 Hz + snare/hat 150-6000 Hz spectral flux) at the beat rate, and its clarity; a clash bar is
              both decks clear and |phase A - phase B| > D ms; score = longest run of clash bars.
Thresholds: pro p95 of the same score on the 33 protrans pro clips (pro decks = the sources placed on the pro clip as in
extract_protrans), nothing else. Design constants (T0, D, clarity floor) are chosen on the DEV half of the injected-fault
set only; the HELD-OUT half is scored once (calib_v2.py)."""
import numpy as np
SR = 44100

def bar_db(y, nbars, bs, lo=None, hi=None):
    m = y.mean(1) if y.ndim == 2 else y; out = np.full(nbars, -120.0)
    for k in range(nbars):
        seg = m[int(k*bs):int((k+1)*bs)]
        if len(seg) < 512: continue
        if lo is None: p = np.mean(seg**2)
        else:
            S = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))**2; f = np.fft.rfftfreq(len(seg), 1/SR)
            p = S[(f >= lo) & (f < hi)].sum() / len(seg)**2 * 4
        out[k] = 10*np.log10(p + 1e-12)
    return out

def onset_env(y, hop=256, n=1024):
    m = y.mean(1) if y.ndim == 2 else y
    if len(m) < n: return np.zeros(1), hop
    fr = np.lib.stride_tricks.sliding_window_view(m, n)[::hop] * np.hanning(n)
    S = np.abs(np.fft.rfft(fr, axis=1)); f = np.fft.rfftfreq(n, 1/SR)
    L = np.log1p(100*S); d = np.maximum(0, np.diff(L, axis=0))
    kick = d[:, (f >= 30) & (f < 150)].sum(1); sn = d[:, (f >= 150) & (f < 6000)].sum(1)
    e = kick / (kick.mean() + 1e-9) + sn / (sn.mean() + 1e-9)
    return np.concatenate([[0], e]), hop

def bar_phase(env, hop, nbars, bs, beat_s):
    """per bar: (phase in ms within one beat, clarity 0..1) of the beat-rate component of the onset envelope"""
    fps = SR / hop; ph = np.full(nbars, np.nan); cl = np.zeros(nbars)
    for k in range(nbars):
        i0, i1 = int(k*bs/hop), int((k+1)*bs/hop); seg = env[i0:i1]
        if len(seg) < 8 or seg.sum() <= 0: continue
        t = (np.arange(i0, i0 + len(seg))) / fps
        c = np.sum(seg * np.exp(-2j*np.pi*t/beat_s))
        ph[k] = (np.angle(c) / (2*np.pi)) * beat_s * 1000; cl[k] = abs(c) / seg.sum()
    return ph, cl

def wrap(d, beat_ms):
    return (d + beat_ms/2) % beat_ms - beat_ms/2

def hole_score(lows, s, e, T0, ref=None):
    lows = np.asarray(lows, float); n = len(lows)
    if ref is None:
        out = np.r_[lows[:max(0, s)], lows[min(n, e):]]
        out = out[out > -100]; ref = float(np.median(out)) if len(out) else float(np.percentile(lows, 75))
    d = ref - lows[max(0, s):min(n, e)]; best = run = 0.0
    for x in d:
        run = run + (x - T0) if x > T0 else 0.0; best = max(best, run)
    return float(best)

def clash_score(phA, clA, phB, clB, audible, beat_ms, D, cmin):
    best = run = 0
    for k in range(len(phA)):
        bad = bool(audible[k] and clA[k] >= cmin and clB[k] >= cmin and np.isfinite(phA[k]) and np.isfinite(phB[k])
                   and abs(wrap(phA[k] - phB[k], beat_ms)) > D)
        run = run + 1 if bad else 0; best = max(best, run)
    return int(best)

def deck_feats(A, B, bs, beat_s):
    n = int(len(A) // bs); S = A + B
    lows = bar_db(S, n, bs, 30, 150); allA, allB = bar_db(A, n, bs), bar_db(B, n, bs)
    eA, hop = onset_env(A); eB, _ = onset_env(B)
    pA, cA = bar_phase(eA, hop, n, bs, beat_s); pB, cB = bar_phase(eB, hop, n, bs, beat_s)
    return dict(n=n, lows=lows, allA=allA, allB=allB, pA=pA, cA=cA, pB=pB, cB=cB)

def audible_mask(allA, allB, rel=12.0):
    """both decks within `rel` dB of their own loud level (p90) in that bar"""
    return (allA > np.percentile(allA, 90) - rel) & (allB > np.percentile(allB, 90) - rel)

# ---- v2b clash (22:55): per-bar deck-to-deck cross-correlation of drum-onset envelopes ---------------------------------------
# The single beat-rate Fourier phase (above) had clarity ~0.02 on real DnB (syncopated 2-step kick), so it could not see a
# 110 ms delay (0/103 detected). v2b: per bar, the lag (|lag| <= 150 ms, < half a beat) that best aligns deck B's onset
# envelope to deck A's, and its Pearson r. A clash bar = |lag| > D ms with r >= cmin.
def flat_env(e, hop, beat_s):
    w = max(3, int(beat_s * SR / hop)); k = np.ones(w) / w
    return np.maximum(0, e - np.convolve(e, k, 'same'))

def bar_lag(eA, eB, hop, nbars, bs, max_ms=150.0):
    Lm = int(max_ms / 1000 * SR / hop); lag = np.full(nbars, np.nan); rr = np.zeros(nbars)
    for k in range(nbars):
        i0, i1 = int(k*bs/hop), int((k+1)*bs/hop)
        if i0 - Lm < 0 or i1 + Lm > min(len(eA), len(eB)): continue
        a = eA[i0:i1]; a = a - a.mean(); na = np.linalg.norm(a)
        if na <= 0: continue
        best = (-2, 0)
        for L in range(-Lm, Lm + 1):
            b = eB[i0 + L:i1 + L]; b = b - b.mean(); nb = np.linalg.norm(b)
            if nb <= 0: continue
            r = float(a @ b / (na * nb))
            if r > best[0]: best = (r, L)
        rr[k] = best[0]; lag[k] = best[1] * hop / SR * 1000
    return lag, rr

def clash_score_b(lag, rr, audible, D, cmin):
    best = run = 0
    for k in range(len(lag)):
        bad = bool(audible[k] and np.isfinite(lag[k]) and rr[k] >= cmin and abs(lag[k]) > D)
        run = run + 1 if bad else 0; best = max(best, run)
    return int(best)

def hole_run(lows, s, e, T0, ref=None):
    """duration-only form: longest run of bars with summed-lows deficit > T0 dB"""
    lows = np.asarray(lows, float); n = len(lows)
    if ref is None:
        out = np.r_[lows[:max(0, s)], lows[min(n, e):]]; out = out[out > -100]; ref = float(np.median(out)) if len(out) else float(np.percentile(lows, 75))
    best = run = 0
    for x in ref - lows[max(0, s):min(n, e)]:
        run = run + 1 if x > T0 else 0; best = max(best, run)
    return int(best)

def deck_feats_b(A, B, bs, beat_s):
    f = deck_feats(A, B, bs, beat_s)
    eA, hop = onset_env(A); eB, _ = onset_env(B)
    f['lag'], f['xr'] = bar_lag(flat_env(eA, hop, beat_s), flat_env(eB, hop, beat_s), hop, f['n'], bs)
    return f

# ---- v2c clash (23:25): each deck's per-bar lag against the MIX it plays in, then deck-to-deck difference ----------------------
# Diagnosis of v2b: the pro reference decks (sources placed once on the pro clip) drift against each other (median measured
# deck-to-deck lag on pros 60-75 ms), so pro p95 sat above a 110 ms fault. Measuring each deck against the mix itself removes
# placement/tempo drift on pros, and is defined identically on our renders (mix = A + B).
def clash_feats_c(A, B, M, bs, beat_s, nbars):
    eA, hop = onset_env(A); eB, _ = onset_env(B); eM, _ = onset_env(M)
    fA, fB, fM = (flat_env(x, hop, beat_s) for x in (eA, eB, eM))
    lA, rA = bar_lag(fA, fM, hop, nbars, bs); lB, rB = bar_lag(fB, fM, hop, nbars, bs)
    return dict(lagAM=lA, rAM=rA, lagBM=lB, rBM=rB)

def clash_score_c(f, audible, D, cmin):
    best = run = 0
    for k in range(len(f['lagAM'])):
        ok = audible[k] and np.isfinite(f['lagAM'][k]) and np.isfinite(f['lagBM'][k]) and min(f['rAM'][k], f['rBM'][k]) >= cmin
        bad = bool(ok and abs(f['lagAM'][k] - f['lagBM'][k]) > D)
        run = run + 1 if bad else 0; best = max(best, run)
    return int(best)
