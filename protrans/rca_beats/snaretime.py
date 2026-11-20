"""Attack time of each deck's backbeat snare (beats 2 and 4) vs the mix grid, from the isolated rendered deck: broadband
(150 Hz-8 kHz) rectified-amplitude envelope at 1 ms, attack = first crossing of 50 % of the local peak within +-90 ms of the beat.
Pattern- and timbre-light: compares when the hits START, not where envelope mass sits."""
import numpy as np, scipy.signal as sg
def attacks(y, sr, s0, bars, beat, bs):
    m = y.mean(1) if y.ndim > 1 else y; b, a = sg.butter(4, [150, 8000], 'band', fs=sr); x = np.abs(sg.filtfilt(b, a, m))
    k = int(sr / 1000); env = np.convolve(x, np.ones(k) / k, 'same'); out = {}
    for bar in bars:
        r = []
        for q in (1, 3):
            t = (bar - s0) * bs + q * beat * sr; i0, i1 = int(t - 0.09 * sr), int(t + 0.09 * sr)
            if i0 < 0 or i1 > len(env): continue
            w = env[i0:i1]; p = int(np.argmax(w)); base = np.percentile(w, 10)
            if w[p] < 4 * (base + 1e-9): continue
            j = np.nonzero(w[:p + 1] < base + 0.5 * (w[p] - base))[0]; j = j[-1] + 1 if len(j) else 0
            r.append((i0 + j - t) / sr * 1000)
        out[bar] = r
    return out
