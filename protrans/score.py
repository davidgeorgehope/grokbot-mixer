"""Similarity of a pro transition vs our recreation (0-100) with a breakdown.

The scorer may see the pro audio; the engine (recreate.py) must not.

Before any comparison we time-align `ours` to the pro clip (kick-envelope
cross-correlation) and crop both to the same overlap. Beat and event terms
are measured on that equal-length window so they are not comparing
different parts of two files.

Per-stem curves use Demucs (drums/bass/vocals/other=melody) when the
separator imports and runs; otherwise band-split proxies. Per-deck curves
are recovered when both clean sources are given.

Sanity: score(x, x) ~ 100; a different transition should score clearly low.
Score weights are FIXED (not tuned) so the tuner cannot cheat the metric.
"""
from __future__ import annotations
import json, os, subprocess, hashlib
import numpy as np

SCORER_VERSION = "gain-events-v3-beatid"  # v3 (2026-11-11 RCA): beat_align also scores beat identity (deck-vs-deck lock vs the pro); score_v2 kept in the result

SR = 22050
HOP = 512
NFFT = 2048
ALIGN_HOP = 256
ALIGN_MAX_S = 24.0
# fixed weights (do not put these in rules.json)
W = dict(stem_curves=0.28, deck_curves=0.22, beat_align=0.15,
         bass_swap=0.13, outgoing_cut=0.12, blend_length=0.10)

def _load(path, sr=SR, t0=None, t1=None):
    cmd = ['ffmpeg', '-v', 'error']
    if t0 is not None: cmd += ['-ss', f'{t0:.3f}']
    cmd += ['-i', path]
    if t1 is not None and t0 is not None: cmd += ['-t', f'{t1-t0:.3f}']
    cmd += ['-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

def _rms(y, hop=HOP):
    if len(y) < hop: return np.array([np.sqrt(np.mean(y**2)+1e-12)])
    n = 1 + (len(y) - hop) // hop
    frames = y[:n*hop].reshape(n, hop)
    return np.sqrt(np.mean(frames**2, 1) + 1e-12)

def _db(e):
    return 20 * np.log10(np.maximum(e, 1e-8))

def _butter(y, kind, fc, sr=SR):
    from scipy.signal import butter, sosfiltfilt
    fc = np.asarray(fc, float)
    wn = np.clip(fc / (sr/2), 1e-4, 0.99)
    wn = float(wn) if wn.ndim == 0 or wn.size == 1 else wn
    sos = butter(4, wn, kind, output='sos')
    return sosfiltfilt(sos, y)

def band_stems(y):
    """Fast stem proxies when Demucs is off."""
    bass = _butter(y, 'low', 150)
    drums = _butter(y, 'band', [80, 400])
    vocals = _butter(y, 'band', [300, 3400])
    melody = y - bass - 0.35 * vocals
    return dict(drums=drums, bass=bass, vocals=vocals, melody=melody)

def demucs_available():
    try:
        import demucs  # noqa: F401
        return True
    except Exception:
        return False

def demucs_stems(path, cache_dir):
    """Return dict of stem waveforms or None if Demucs is unavailable."""
    key = hashlib.md5(f'{os.path.abspath(path)}|{os.path.getmtime(path)}'.encode()).hexdigest()[:16]
    outd = os.path.join(cache_dir, 'stems', key)
    names = ('drums', 'bass', 'vocals', 'other')
    mapped = {'drums':'drums','bass':'bass','vocals':'vocals','other':'melody'}
    ready = all(os.path.exists(os.path.join(outd, 'htdemucs', 'clip', n+'.wav')) for n in names)
    if not ready:
        os.makedirs(outd, exist_ok=True)
        clip = os.path.join(outd, 'clip.wav')
        if not os.path.exists(clip):
            subprocess.run(['ffmpeg','-v','error','-y','-i',path,'-ac','2','-ar',str(SR),clip], check=True)
        r = subprocess.run(['python3','-m','demucs','-n','htdemucs','-j','2','-o',outd,clip],
                           capture_output=True, text=True)
        if r.returncode:
            return None
    stems = {}
    base = os.path.join(outd, 'htdemucs', 'clip')
    for n in names:
        wav = os.path.join(base, n+'.wav')
        if not os.path.exists(wav): return None
        stems[mapped[n]] = _load(wav)
    return stems

def _resample(a, n):
    if len(a) == n: return a
    if len(a) < 2 or n < 1: return np.zeros(n)
    x = np.linspace(0, 1, len(a))
    return np.interp(np.linspace(0, 1, n), x, a)

def curve_sim(a, b):
    """Map two energy curves to 0-100. Uncorrelated curves score low (not ~50)."""
    n = min(len(a), len(b))
    if n < 4: return 0.0
    a, b = np.asarray(a[:n], float), np.asarray(b[:n], float)
    sa, sb = a.std(), b.std()
    if sa < 1e-8 and sb < 1e-8: return 100.0
    if sa < 1e-8 or sb < 1e-8: return 0.0
    r = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(r): r = 0.0
    an = (a-a.mean())/(sa+1e-9); bn = (b-b.mean())/(sb+1e-9)
    nrmse = float(np.sqrt(np.mean((an-bn)**2)))
    # Positive correlation only: r=0 / nrmse~sqrt(2) -> ~0-10, not ~50.
    corr_part = 100.0 * max(0.0, r)
    shape_part = 100.0 * max(0.0, 1.0 - nrmse/2.0)
    return float(np.clip(0.65*corr_part + 0.35*shape_part, 0, 100))

def time_sim(t_ours, t_pro, scale):
    """How close two event times are. scale is the 'ok' distance (same units). None vs None = 100."""
    if t_ours is None and t_pro is None: return 100.0
    if t_ours is None or t_pro is None: return 20.0
    return float(np.clip(100 * np.exp(-abs(t_ours-t_pro) / max(scale, 1e-6)), 0, 100))

BAR_SEC = 240.0 / 174.0  # one 4/4 bar at the harness tempo

def _to_bars(db, hop=HOP, sr=SR):
    """Pool a per-frame dB curve into per-bar dB (mean power)."""
    db = np.asarray(db, float)
    fpb = BAR_SEC * sr / hop
    nb = int(len(db) // fpb)
    if nb < 1:
        return db
    p = 10 ** (db / 10.0)
    out = [10*np.log10(np.mean(p[int(round(k*fpb)):int(round((k+1)*fpb))]) + 1e-12) for k in range(nb)]
    return np.array(out)

def events_from_pair(out_db, in_db):
    """Events in bars from deck gain curves, relative to each deck's active level.

    Sustained presence avoids a single noisy frame becoming a bar-zero swap;
    -12 dB relative presence measures the overlap, not absolute mastering level.
    A cut is the final sustained exit (-12 dB), not the first -6 dB fade point.
    """
    o, i = _to_bars(out_db), _to_bars(in_db)
    n = min(len(o), len(i))
    if not n:
        return dict(bass_swap=None, outgoing_cut=None, blend_length=0)
    o, i = o[:n], i[:n]
    def relative(x):
        ref = np.percentile(x, 90)
        return x - ref if ref > -90 else np.full_like(x, -120)
    o, i = relative(o), relative(i)
    on_o, on_i = o > -12, i > -12
    def sustained(mask):
        return next((k for k in range(n-1) if mask[k:k+2].all()), None)
    start = sustained(on_i)
    # Require established outgoing dominance before an incoming handoff.
    dominant = (o > i) & on_o
    established = sustained(dominant)
    swap = None if established is None else sustained(
        (np.arange(n) > established) & (i >= o - 1.0) & on_i)
    active = np.flatnonzero(on_o)
    end = int(active[-1]) + 1 if len(active) else 0
    cut = end if end < n and len(active) else None
    both = np.flatnonzero(on_o & on_i)
    runs = np.split(both, np.flatnonzero(np.diff(both) > 1) + 1)
    blend = int(max(map(len, runs)))
    return dict(bass_swap=swap, outgoing_cut=cut, blend_length=blend)


def source_gain_events(mix, src_a, src_b):
    """Identify deck controls with multi-bin NNLS, not one equation/two unknowns.

    The old per-frame power pseudoinverse assigned both decks gain even during
    solo passages. Gains remove the source's own dynamics from event timing.
    Spectral fitting is phase-tolerant; these controls are used only for events.
    """
    import diagnose_gap as D
    aligned = []
    for path in (src_a, src_b):
        loc = D.version_match.locate_in(mix, _load(path))
        if loc.get('track_t') is None:
            return None
        y = D.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
        y, _ = D.refine_lag(mix, y)
        aligned.append(y)
    gains, _, times, _ = D.band_gains(mix, *aligned)
    def curves(band):
        # events_from_pair accepts HOP-spaced dB curves.
        t = np.arange(len(_rms(mix))) * HOP / SR
        return tuple(_db(np.interp(t, times, gains[band][deck])) for deck in ('a', 'b'))
    bass = events_from_pair(*curves('bass'))
    full = events_from_pair(*curves('all'))
    return dict(bass_swap=bass['bass_swap'], outgoing_cut=full['outgoing_cut'],
                blend_length=full['blend_length'])

def _kick_env(y, hop=ALIGN_HOP, sr=SR):
    z = _butter(y, 'low', 150, sr=sr)
    e = _rms(z, hop)
    # onset-ish: positive first difference emphasises downbeats
    d = np.diff(e, prepend=e[:1])
    return np.maximum(d, 0.0) + 0.25 * e

def align_ours_to_pro(y_pro, y_ours, sr=SR, max_shift_s=ALIGN_MAX_S):
    """Shift ours so its kick envelope best matches pro. Return equal-length slices.

    lag_samples > 0 means ours is delayed (ours[0] lines up with pro[lag]).
    """
    hop = ALIGN_HOP
    ep, eo = _kick_env(y_pro, hop, sr), _kick_env(y_ours, hop, sr)
    ep = ep - ep.mean(); eo = eo - eo.mean()
    max_lag = min(int(max_shift_s * sr / hop), max(len(ep), len(eo)) - 2)
    if max_lag < 4 or len(ep) < 8 or len(eo) < 8:
        n = min(len(y_pro), len(y_ours))
        return y_pro[:n], y_ours[:n], 0, 1.0
    nfft = 1 << int(np.ceil(np.log2(len(ep) + len(eo))))
    cc = np.fft.irfft(np.fft.rfft(ep, nfft) * np.conj(np.fft.rfft(eo, nfft)), nfft)
    # cc[k] for k>=0: eo delayed by k frames; cc[-k]: eo advanced by k
    vals = np.concatenate([cc[-max_lag:], cc[:max_lag+1]])
    lags = np.arange(-max_lag, max_lag+1)
    i = int(np.argmax(vals))
    lag_f = int(lags[i])
    denom = (np.linalg.norm(ep) * np.linalg.norm(eo)) + 1e-12
    peak = float(vals[i] / denom)
    lag = lag_f * hop
    if lag >= 0:
        yp, yo = y_pro[lag:], y_ours
    else:
        yp, yo = y_pro, y_ours[-lag:]
    n = min(len(yp), len(yo))
    if n < int(4 * sr):
        # overlap too short; fall back to a centre crop of equal length
        n = min(len(y_pro), len(y_ours))
        return y_pro[:n], y_ours[:n], 0, peak
    return yp[:n], yo[:n], lag, peak

def beat_off_ms(a, b, sr=SR):
    hop = 64
    z_a = _butter(a, 'low', 120, sr=sr)
    z_b = _butter(b, 'low', 120, sr=sr)
    def env(z):
        n = 1 + max(0, (len(z)-hop)//hop)
        fr = z[:n*hop].reshape(n, hop)
        e = np.sqrt((fr**2).mean(1)+1e-12)
        return e - e.mean()
    ea, eb = env(z_a), env(z_b)
    n = min(len(ea), len(eb)); ea, eb = ea[:n], eb[:n]
    if n < 8: return 0.0
    L = int(0.04 * sr / hop)
    xc = [np.dot(ea[max(0,k):n+min(0,k)], eb[max(0,-k):n-max(0,k)]) for k in range(-L, L+1)]
    return abs(int(np.argmax(xc)) - L) * hop / (sr/1000)

def beat_score(yp, yo, sr=SR):
    """Residual flam plus kick-pattern agreement on the already-aligned window."""
    flam = beat_off_ms(yp, yo, sr=sr)
    flam_s = float(np.clip(100 * np.exp(-flam / 8.0), 0, 100))
    env_s = curve_sim(_kick_env(yp), _kick_env(yo))
    return 0.4 * flam_s + 0.6 * env_s, flam

BEAT_SEC = 60.0 / 174.0
ID_HOP = 64
ID_TAU_MS = 25.0

def _stretched_source(path):
    """the 174-BPM stretched source the engine plays (src2/st/<id>.wav) when it exists, else the file itself"""
    yt = os.path.splitext(os.path.basename(path))[0]
    st = os.path.join(os.path.dirname(__file__), '..', 'src2', 'st', yt + '.wav')
    return st if os.path.exists(st) else path

def _fine_env(y, hop=32, sig=2.0):
    from scipy.signal import butter, sosfiltfilt
    from scipy.ndimage import gaussian_filter1d
    z = sosfiltfilt(butter(4, [40, 4000], 'band', fs=SR, output='sos'), y)
    n = len(z) // hop
    e = np.sqrt((z[:n*hop].reshape(n, hop)**2).mean(1) + 1e-12)
    d = gaussian_filter1d(np.maximum(np.diff(e, prepend=e[:1]), 0.0), sig)
    return d - d.mean()

_SRC = {}
def _src_feats(path):
    p = _stretched_source(path)
    if p not in _SRC:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'eval'))
        import control_curves as CC
        y = _load(p)
        _SRC[p] = (CC.bandpow(y), _fine_env(y))
    return _SRC[p]

def _fit_chunks(h, cc_min=0.45, tol=0.05):
    """mix_t = a + s*track_t from chunk hits (track_t, mix_t, cc, z): every pair of strong hits proposes a line
    (|s-1| < 3%), the line with the largest summed cc of inliers wins (repeated choruses only win if they explain more)."""
    if h is None or len(h) == 0:
        return None
    H = h[h[:, 2] >= cc_min]
    if len(H) < 2:
        return None
    best = None
    for i in range(len(H)):
        for j in range(i + 1, len(H)):
            dt = H[j, 0] - H[i, 0]
            if abs(dt) < 3:
                continue
            s_ = (H[j, 1] - H[i, 1]) / dt
            if not 0.97 < s_ < 1.03:
                continue
            a = H[i, 1] - s_ * H[i, 0]
            inl = np.abs(H[:, 1] - (a + s_ * H[:, 0])) < tol
            sc = float(H[inl, 2].sum())
            if inl.sum() >= 2 and (best is None or sc > best[0]):
                best = (sc, inl)
    if best is None:
        return None
    I = H[best[1]]
    s_, a = np.polyfit(I[:, 0], I[:, 1], 1) if len(I) >= 3 else (1.0, float(np.mean(I[:, 1] - I[:, 0])))
    return dict(a=float(a), s=float(s_), n=int(len(I)), m0=float(I[:, 1].min()), m1=float(I[:, 1].max() + 6.0))

def _deck_line(y, Fm, em, path, max_shift=0.08):
    """mix_t = a + s * src_t for one deck (band-power chunk RANSAC, control_curves.fit_line), then the beat-level
    fine shift (onset envelope, +-80 ms, i.e. well under half a beat so it can't jump to the off-beat)."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'eval'))
    import control_curves as CC
    Ft, es = _src_feats(path)
    h, _ = CC.locate(Fm, Ft, chunk_s=6.0, hop_s=2.0)
    line = _fit_chunks(h)
    if not line:
        return None
    a, s_ = line['a'], line['s']
    fr = SR / 32.0
    m0, m1 = max(0.0, line['m0']), min(len(y) / SR, line['m1'])
    if m1 - m0 < 6:
        return None
    tm = np.arange(int(m0 * fr), int(m1 * fr)) / fr
    ref = em[(tm * fr).astype(int)]
    best = None
    for d in np.arange(-max_shift, max_shift + 1e-9, 0.001):
        ts = (tm - a - d) / s_ * fr
        ok = (ts >= 0) & (ts < len(es) - 1)
        if ok.sum() < len(ts) * 0.8:
            continue
        v = np.interp(ts[ok], np.arange(len(es)), es)
        c = float(np.dot(ref[ok], v) / (np.linalg.norm(ref[ok]) * np.linalg.norm(v) + 1e-12))
        if best is None or c > best[0]:
            best = (c, d)
    if best is None:
        return None
    return dict(a=a + best[1], s=s_, r=round(best[0], 3), span=(round(m0, 1), round(m1, 1)))

def deck_lock(y, src_a, src_b):
    """phase (beats, [-0.5, 0.5)) of deck A's source beat grid relative to deck B's at the middle of mix clip y"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'eval'))
    import control_curves as CC
    Fm, em = CC.bandpow(y), _fine_env(y)
    la, lb = _deck_line(y, Fm, em, src_a), _deck_line(y, Fm, em, src_b)
    if not la or not lb:
        return None
    tc = len(y) / SR / 2
    ua = (tc - la['a']) / la['s'] / BEAT_SEC
    ub = (tc - lb['a']) / lb['s'] / BEAT_SEC
    ph = float((ua - ub + 0.5) % 1.0 - 0.5)
    return dict(phase_beats=round(ph, 4), rate=round(1 / la['s'], 4), r_a=la['r'], r_b=lb['r'])

def beat_identity(y_p, y_o, src_a, src_b, r_min=0.2):
    """v3 beat-identity term: does ours lock the two decks the way the pro does (same beat, not half a beat off)?
    100 * exp(-|lock_ours - lock_pro| ms / 25). None when either deck can't be located in either clip."""
    try:
        lp = deck_lock(y_p, src_a, src_b)
        lo = deck_lock(y_o, src_a, src_b)
    except Exception as e:
        return None, dict(error=str(e)[-200:])
    if not lp or not lo or min(lp['r_a'], lp['r_b'], lo['r_a'], lo['r_b']) < r_min:
        return None, dict(pro=lp, ours=lo, why='deck not located (onset r < %g)' % r_min)
    d = float((lo['phase_beats'] - lp['phase_beats'] + 0.5) % 1.0 - 0.5)
    ms = abs(d) * BEAT_SEC * 1000.0
    return float(100.0 * np.exp(-ms / ID_TAU_MS)), dict(pro=lp, ours=lo, diff_beats=round(d, 4), diff_ms=round(ms, 1))

def _stem_bundle_from_wave(y, path, use_demucs, cache):
    stems = None
    if use_demucs:
        try: stems = demucs_stems(path, cache)
        except Exception: stems = None
    if stems is None:
        stems = band_stems(y)
        kind = 'bands'
    else:
        kind = 'demucs'
        # resample each stem onto the (possibly already trimmed) wave length
        for k, v in list(stems.items()):
            if len(v) != len(y):
                # better: linear resample in time
                if len(v) > 1:
                    t = np.linspace(0, 1, len(v))
                    stems[k] = np.interp(np.linspace(0, 1, len(y)), t, v).astype(np.float32)
                else:
                    stems[k] = np.zeros(len(y), np.float32)
    curves = {k: _db(_rms(v)) for k, v in stems.items()}
    return y, stems, curves, kind

def locate_offset(mix, src):
    """Best lag (src starts this many seconds into mix). Uses band-power xcorr."""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'eval'))
        import control_curves as CC
        Fm, Ft = CC.bandpow(mix), CC.bandpow(src)
        hits, _ = CC.locate(Fm, Ft, chunk_s=6.0, hop_s=3.0)
        if len(hits) == 0: return None
        hits = hits[np.argsort(-hits[:, 3])]
        mix_t = float(hits[0, 1]); src_t = float(hits[0, 0])
        return mix_t - src_t
    except Exception:
        em, es = _rms(mix), _rms(src[:min(len(src), len(mix))])
        n = len(em); L = len(es)
        if L >= n: es = es[: max(4, n//2)]; L = len(es)
        if L < 4 or n < L + 2: return None
        N = 1 << int(np.ceil(np.log2(n+L)))
        cc = np.fft.irfft(np.fft.rfft(em, N) * np.conj(np.fft.rfft(es, N)))[:n-L+1]
        k = int(np.argmax(cc))
        return k * HOP / SR

def deck_curves_from_sources(mix_stems, path_a, path_b):
    """Per-stem per-deck energy via aligned source stems vs mix stems (least squares)."""
    ya, yb = _load(path_a), _load(path_b)
    mix_y = sum(mix_stems.values())
    oa = locate_offset(mix_y, ya)
    ob = locate_offset(mix_y, yb)
    if oa is None or ob is None:
        return None
    out = {}
    for name, my in mix_stems.items():
        proxy = band_stems(ya)
        sa = proxy[name] if name in proxy else ya
        sb = band_stems(yb)[name] if name in band_stems(yb) else yb
        def place(src, off):
            i0 = int(round(-off * SR))
            if i0 < 0:
                s = np.concatenate([np.zeros(-i0, np.float32), src])
            else:
                s = src[i0:]
            if len(s) < len(my):
                s = np.pad(s, (0, len(my)-len(s)))
            return s[:len(my)]
        A = place(sa, oa); B = place(sb, ob)
        em, ea, eb = _rms(my)**2, _rms(A)**2, _rms(B)**2
        n = min(len(em), len(ea), len(eb))
        ga = np.zeros(n); gb = np.zeros(n)
        for k in range(n):
            M = np.array([[ea[k], eb[k]]])
            try:
                g, _, _, _ = np.linalg.lstsq(M, np.array([em[k]]), rcond=None)
            except Exception:
                g = np.array([0.5, 0.5])
            ga[k], gb[k] = max(g[0], 0), max(g[1], 0)
        out[name] = (_db(np.sqrt(ga*ea[:n]+1e-12)), _db(np.sqrt(gb*eb[:n]+1e-12)))
    return out, oa, ob

def _slice_stems(stems, y_full, y_win):
    """Crop stem waves to the same region as an already-sliced mono mix window."""
    # We cannot recover the exact sample offset if y_win was taken from the
    # middle; callers pass the slice bounds instead via align + index.
    return stems

def score(pro_path, ours_path, src_a=None, src_b=None, use_demucs=None, cache=None):
    cache = cache or os.path.join(os.path.dirname(__file__), 'cache')
    if use_demucs is None:
        use_demucs = demucs_available()
    y_p_full = _load(pro_path)
    y_o_full = _load(ours_path)
    y_p, y_o, lag, peak = align_ours_to_pro(y_p_full, y_o_full)
    # Crop original files to the overlap before Demucs so stems share the window.
    # Write short temp wavs only when we actually run Demucs.
    import tempfile, shutil
    tmpdir = None
    pro_for_stems, ours_for_stems = pro_path, ours_path
    if use_demucs and (lag != 0 or len(y_p) != len(y_p_full) or len(y_o) != len(y_o_full)):
        tmpdir = tempfile.mkdtemp(prefix='ptscore_')
        pro_for_stems = os.path.join(tmpdir, 'pro.wav')
        ours_for_stems = os.path.join(tmpdir, 'ours.wav')
        def _w(p, y):
            subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(SR),'-ac','1',
                            '-i','-','-ac','2',p], input=y.astype(np.float32).tobytes(), check=True)
        _w(pro_for_stems, y_p); _w(ours_for_stems, y_o)

    y_p, st_p, cu_p, kind_p = _stem_bundle_from_wave(y_p, pro_for_stems, use_demucs, cache)
    y_o, st_o, cu_o, kind_o = _stem_bundle_from_wave(y_o, ours_for_stems, use_demucs, cache)
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # If we Demucs'd the original untrimmed files (identity / no shift), crop stems to the window.
    if kind_p == 'demucs' and len(next(iter(st_p.values()))) != len(y_p):
        pass  # already resampled in _stem_bundle_from_wave
    stem_scores = {k: curve_sim(cu_p[k], cu_o[k]) for k in cu_p if k in cu_o}
    stem_mean = float(np.mean(list(stem_scores.values()))) if stem_scores else 0.0

    deck = None; deck_mean = None
    ev_p = ev_o = None
    if src_a and src_b and os.path.exists(src_a) and os.path.exists(src_b):
        try:
            got_p = deck_curves_from_sources(st_p, src_a, src_b)
            got_o = deck_curves_from_sources(st_o, src_a, src_b)
            if got_p and got_o:
                deck_p, _, _ = got_p
                deck_o, _, _ = got_o
                parts = []
                for k in deck_p:
                    if k not in deck_o: continue
                    parts.append(curve_sim(deck_p[k][0], deck_o[k][0]))
                    parts.append(curve_sim(deck_p[k][1], deck_o[k][1]))
                deck_mean = float(np.mean(parts)) if parts else stem_mean
                deck = dict(per_stem_deck=round(deck_mean, 2))
                bo_p, bi_p = deck_p.get('bass', next(iter(deck_p.values())))
                bo_o, bi_o = deck_o.get('bass', next(iter(deck_o.values())))
                ev_p = source_gain_events(y_p, src_a, src_b)
                ev_o = source_gain_events(y_o, src_a, src_b)
        except Exception as e:
            deck = dict(error=str(e)[-200:])

    if ev_p is None:
        ev_p = events_from_pair(cu_p['bass'], cu_p['melody'])
        ev_o = events_from_pair(cu_o['bass'], cu_o['melody'])
    if deck_mean is None:
        deck_mean = stem_mean

    beat_s, beat = beat_score(y_p, y_o)
    beat_v2 = beat_s
    ident_s, ident = (None, None)
    if src_a and src_b and os.path.exists(src_a) and os.path.exists(src_b):
        ident_s, ident = beat_identity(y_p, y_o, src_a, src_b)
    if ident_s is not None:
        beat_s = 0.5 * beat_v2 + 0.5 * ident_s
    swap_s = time_sim(ev_o.get('bass_swap'), ev_p.get('bass_swap'), 4)
    cut_s = time_sim(ev_o.get('outgoing_cut'), ev_p.get('outgoing_cut'), 4)
    len_s = time_sim(ev_o.get('blend_length'), ev_p.get('blend_length'), 8)
    # Same-structure clips (all cut 24s before incoming) share event times.
    # Do not let that inflate a mismatch when the audio itself disagrees.
    gate = 0.35 + 0.65 * (stem_mean / 100.0)
    swap_s, cut_s, len_s = swap_s * gate, cut_s * gate, len_s * gate

    total = (W['stem_curves']*stem_mean + W['deck_curves']*deck_mean + W['beat_align']*beat_s
             + W['bass_swap']*swap_s + W['outgoing_cut']*cut_s + W['blend_length']*len_s)
    total_v2 = total + W['beat_align'] * (beat_v2 - beat_s)
    return dict(
        score=round(float(total), 2),
        score_v2=round(float(total_v2), 2),
        scorer_version=SCORER_VERSION,
        breakdown=dict(stem_curves=round(stem_mean,2), deck_curves=round(deck_mean,2),
                       beat_align=round(float(beat_s),2), bass_swap=round(swap_s,2),
                       outgoing_cut=round(cut_s,2), blend_length=round(len_s,2),
                       stems= {k: round(v,2) for k,v in stem_scores.items()},
                       beat_off_ms=round(float(beat),2), beat_align_v2=round(float(beat_v2),2),
                       beat_identity=None if ident_s is None else round(float(ident_s),2), beat_lock=ident, events_pro=ev_p, events_ours=ev_o,
                       stem_kind=(kind_p, kind_o), deck=deck,
                       align=dict(lag_samples=int(lag), lag_ms=round(lag * 1000.0 / SR, 2),
                                  peak=round(float(peak), 4), win_sec=round(len(y_p)/SR, 3))),
        weights=W,
        pro=pro_path, ours=ours_path,
    )

if __name__ == '__main__':
    import sys
    print(json.dumps(score(*sys.argv[1:]), indent=2))
