"""DJ/MC talkover admission check.

A pro transition is unfair to recreate when the DJ or an MC talks over the
blend: that voice is in the pro clip but in neither source track. We separate
vocals (Demucs htdemucs) from the pro clip and from both source tracks cut to
the same time window, then per frame fit the pro vocal spectrum as a
non-negative mix of the two source vocal spectra (with a small local lag
search). Active pro-vocal energy the fit cannot explain is "talk".

Flag when talk_s >= TALK_MIN_S or talk_frac >= TALK_MIN_FRAC.
Results are cached in results/talkover.json; flagged ids are excluded by
admit.load_admitted(filtered=True) and run_admitted_tune.load_recs().
"""
from __future__ import annotations
import json, os, sys, shutil, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

SR = 16000
NFFT = 1024
HOP = 256                     # 16 ms
WIN_S = 2.0                   # gain-fit window
LAG_MAX_S = 0.15              # local lag search per window
F_LO, F_HI = 200.0, 4000.0
ACTIVE_DB = -22.0             # frame vocal energy vs clip's 95th pct
SRC_QUIET_DB = -15.0           # source vocal 'quiet' vs its own 95th pct
UNEXPLAINED = 0.6             # unexplained energy share to count a frame as talk
TALK_MIN_S = 4.0
TALK_MIN_FRAC = 0.15
CACHE_JSON = os.path.join(paths.RESULTS, 'talkover.json')

def _mag(y):
    from scipy.signal import stft
    _, _, Z = stft(y, SR, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    M = np.abs(Z)[(f >= F_LO) & (f <= F_HI)]
    # light time smoothing (~80 ms) so tiny misalignments don't read as residual
    k = np.ones(5) / 5
    return np.apply_along_axis(lambda r: np.convolve(r, k, 'same'), 1, M)

def _shift(M, lag):
    if lag == 0: return M
    out = np.zeros_like(M)
    if lag > 0: out[:, lag:] = M[:, :-lag]
    else: out[:, :lag] = M[:, -lag:]
    return out

def _best_lag(P, S, L):
    best, bl = -np.inf, 0
    for lag in range(-L, L + 1):
        Ss = _shift(S, lag)
        num = float((P * Ss).sum()); den = np.sqrt(float((Ss * Ss).sum()) * float((P * P).sum())) + 1e-12
        if num / den > best: best, bl = num / den, lag
    return bl, best

def unexplained_frames(pro_voc, a_voc, b_voc):
    """Per-frame (active, unexplained_share, corr_a, corr_b) for equal-length 16 kHz vocal stems."""
    from scipy.optimize import nnls
    n = min(len(pro_voc), len(a_voc), len(b_voc))
    P, A, B = _mag(pro_voc[:n]), _mag(a_voc[:n]), _mag(b_voc[:n])
    T = P.shape[1]
    e = (P ** 2).sum(0)
    edb = 10 * np.log10(e + 1e-12)
    ref = np.percentile(edb, 95)
    active = edb > ref + ACTIVE_DB
    share = np.zeros(T); ca = np.zeros(T); cb = np.zeros(T)
    W = int(WIN_S * SR / HOP); L = int(LAG_MAX_S * SR / HOP)
    for s in range(0, T, W // 2):
        sl = slice(s, min(T, s + W))
        p = P[:, sl]
        if p.shape[1] < 4: continue
        la, ra = _best_lag(p, A[:, sl], L) if A[:, sl].any() else (0, 0.0)
        lb, rb = _best_lag(p, B[:, sl], L) if B[:, sl].any() else (0, 0.0)
        a = _shift(A, la)[:, sl]; b = _shift(B, lb)[:, sl]
        g, _ = nnls(np.stack([a.ravel(), b.ravel()], 1), p.ravel())
        fit = g[0] * a + g[1] * b
        res = np.maximum(p - fit, 0)
        sh = (res ** 2).sum(0) / ((p ** 2).sum(0) + 1e-12)
        share[sl] = np.maximum(share[sl], sh) if s else sh
        ca[sl], cb[sl] = ra, rb
    def quiet(S):
        es = 10 * np.log10((S ** 2).sum(0) + 1e-12)
        return es < (np.percentile(es, 95) + SRC_QUIET_DB if S.any() else np.inf)
    # local source silence, dilated by the lag search so near-edge frames don't count
    from scipy.ndimage import binary_erosion
    src_quiet = binary_erosion(quiet(A) & quiet(B), np.ones(2 * L + 1, bool), border_value=1)
    return active, share, ca, cb, src_quiet

def syllabic_mod(y):
    """Share of vocal-envelope modulation energy at 3-6 Hz (speech ~4-5 Hz)."""
    from scipy.signal import welch
    env = np.sqrt(np.convolve(y ** 2, np.ones(160) / 160, 'same'))[::80]  # 200 Hz envelope
    env = env - env.mean()
    if len(env) < 512: return 0.0
    f, p = welch(env, 200, nperseg=512)
    band = (f >= 3) & (f <= 6); tot = (f >= 0.5) & (f <= 20)
    return float(p[band].sum() / (p[tot].sum() + 1e-12))

def assess(pro_voc, a_voc, b_voc):
    active, share, ca, cb, src_quiet = unexplained_frames(pro_voc, a_voc, b_voc)
    from scipy.ndimage import median_filter
    mf = lambda m: median_filter(m.astype(np.uint8), size=int(0.5 * SR / HOP)) > 0
    # unexplained voice anywhere (includes sung parts the fit got wrong) -> diagnostic only
    loose = mf(active & (share > UNEXPLAINED))
    # counted talk: unexplained voice while both source vocals are locally quiet
    talk = mf(active & (share > UNEXPLAINED) & src_quiet)
    dt = HOP / SR; dur = len(talk) * dt
    talk_s = float(talk.sum() * dt)
    frac = talk_s / max(dur, 1e-9)
    if talk.any():
        idx = np.repeat(talk, HOP)[:len(pro_voc)]
        speech = syllabic_mod(pro_voc[:len(idx)] * idx)
    else:
        speech = 0.0
    return dict(talk_s=round(talk_s, 2), loose_s=round(float(loose.sum() * dt), 2), talk_frac=round(frac, 3), dur_s=round(dur, 1),
                active_s=round(float(active.sum() * dt), 2),
                mean_unexplained=round(float(share[active].mean()) if active.any() else 0.0, 3),
                corr_a=round(float(np.median(ca)), 3), corr_b=round(float(np.median(cb)), 3),
                speech_mod=round(speech, 3),
                flagged=bool(talk_s >= TALK_MIN_S or frac >= TALK_MIN_FRAC))

# ---------- separation / alignment ----------
_MODEL = None
def _vocals(y44):
    """Demucs htdemucs vocal stem of a mono 44.1k signal -> mono 16k."""
    global _MODEL
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    from scipy.signal import resample_poly
    if _MODEL is None:
        _MODEL = get_model('htdemucs'); _MODEL.eval()
    x = torch.tensor(np.stack([y44, y44])[None], dtype=torch.float32)
    with torch.no_grad():
        out = apply_model(_MODEL, x, device='cpu', progress=False, num_workers=0)[0]
    v = out[_MODEL.sources.index('vocals')].mean(0).numpy()
    return resample_poly(v, 160, 441).astype(np.float32)

def _cut(src, off_s, n, sr):
    i0 = int(round(-off_s * sr))
    s = src[max(i0, 0):]
    if i0 < 0: s = np.concatenate([np.zeros(-i0, np.float32), s])
    return np.pad(s, (0, max(0, n - len(s))))[:n]

def check_clip(pro_path, src_a, src_b):
    import score
    sr = 44100
    yp = score._load(pro_path, sr=sr)
    ya, yb = score._load(src_a, sr=sr), score._load(src_b, sr=sr)
    # locate at 22.05k with the harness's locator
    d = lambda y: y[::2]
    oa = score.locate_offset(d(yp), d(ya)); ob = score.locate_offset(d(yp), d(yb))
    if oa is None or ob is None:
        return dict(error='locate_failed', flagged=False)
    n = len(yp)
    stem_dir = os.environ.get('TALK_STEM_DIR')
    key = os.path.basename(os.path.dirname(pro_path))
    f = stem_dir and os.path.join(stem_dir, key + '.npz')
    if f and os.path.exists(f):
        z = np.load(f); vp, va, vb = z['p'], z['a'], z['b']
    else:
        va = _vocals(_cut(ya, oa, n, sr)); vb = _vocals(_cut(yb, ob, n, sr)); vp = _vocals(yp)
        if f: np.savez(f, p=vp, a=va, b=vb)
    r = assess(vp, va, vb)
    r.update(off_a=round(oa, 2), off_b=round(ob, 2))
    return r

def load_cache():
    return json.load(open(CACHE_JSON)) if os.path.exists(CACHE_JSON) else {}

def flagged_ids():
    return {k for k, v in load_cache().items() if v.get('flagged')}

def check_row(row, force=False):
    """Admission check for an admitted.json row; caches by id."""
    c = load_cache()
    if row['id'] in c and not force: return c[row['id']]
    pro = row.get('pro_clip') or os.path.join(paths.CLIPS, row['split'], row['id'], 'pro.wav')
    sa = os.path.join(paths.LIB, row['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, row['b']['yt'] + '.m4a')
    r = check_clip(pro, sa, sb)
    r.update(dj=row['dj'], pair=row.get('pair'), split=row['split'])
    c = load_cache(); c[row['id']] = r
    json.dump(c, open(CACHE_JSON, 'w'), indent=1)
    return r

if __name__ == '__main__':
    import torch; torch.set_num_threads(int(os.environ.get('TALK_THREADS', '8')))
    rows = json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))
    force = '--force' in sys.argv
    for row in rows:
        r = check_row(row, force=force)
        print(row['id'], json.dumps(r), flush=True)
