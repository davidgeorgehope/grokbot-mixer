"""DRUMCLASH (2026-11-20 RCA, listener: "if it's detectable it should carry a very heavy penalty"): drum-on-drum train-wreck detector.

Works on each deck's OWN audio (stretched st/<id>.wav) placed exactly where the engine plays it (the engine is sample-exact:
source bar k lands on its mix bar with 0.00 ms error, rca_beats/render_vs_source.py), so it needs no render and no beat detection
of the mix. Per overlap bar where BOTH decks carry drums (drum-onset energy >= DRUM_FRAC x the deck's own drop median), the two
decks' drum-onset envelopes (kick <150 Hz + snare 150-2k, log-spectral flux, 5.8 ms frames, 2-bar window) are cross-correlated
over +-half a beat:
  lag_ms  = lag of the strongest peak (+ = A late)
  c0      = best normalised correlation within +-ZERO_MS of zero lag (how well the hits coincide as played)
  gain    = c_peak - c0 (how much better the decks would line up if moved)
Pair score: see summarize() (share of drum-on-drum bars agreeing on one confident non-zero offset). Fewer than MIN_BARS
drum-on-drum bars -> score 0, which is exactly the 'only one deck carries drums' strategy we want to favour.
Thresholds are calibrated to the pro p95 (protrans/rca_beats/drumclash_calib.py), never hand-loosened."""
import json, os
import numpy as np
SRC2 = os.path.dirname(os.path.abspath(__file__))
SR_E = 22050; HOP = 128; DT = HOP / SR_E
OFF_MS = float(os.environ.get('DRUMCLASH_OFF_MS', 25)); GAIN_MIN = float(os.environ.get('DRUMCLASH_GAIN', 0.10))
ZERO_MS = float(os.environ.get('DRUMCLASH_ZERO_MS', 12)); C0_MIN = float(os.environ.get('DRUMCLASH_C0', 0.15))
DRUM_FRAC = float(os.environ.get('DRUMCLASH_DRUM_FRAC', 0.35)); MIN_BARS = int(os.environ.get('DRUMCLASH_MIN_BARS', 3))
FLAG = float(os.environ.get('DRUMCLASH_FLAG', 0.212))  # pair score above this = train wreck; = pro p95 (rca_beats/detector_calibration.json)
_ENV = {}

def _env_from_audio(y, sr=SR_E):
    """(2, n) drum-onset envelopes of the PERCUSSIVE part (librosa HPSS on the STFT magnitude): row 0 kick (20-150 Hz),
    row 1 snare/hat (150 Hz-5 kHz). Harmonic pads, bass notes and vocals mostly go to the harmonic part."""
    import librosa
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)); f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    _, P = librosa.decompose.hpss(S, margin=2.0); out = []
    for lo, hi in ((20, 150), (150, 5000)):
        b = np.log1p(100 * P[(f >= lo) & (f < hi)]).sum(0); o = np.maximum(0, np.diff(b, prepend=b[:1]))
        o = np.maximum(o - np.convolve(o, np.ones(64) / 64, 'same'), 0); out.append(o / (np.percentile(o, 99) + 1e-9))
    return np.array(out, np.float32)

def _perc_db(y, sr=SR_E):
    """per-frame percussive level (dB) for the drums-up gate"""
    import librosa
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)); _, P = librosa.decompose.hpss(S, margin=2.0)
    return 10 * np.log10((P ** 2).sum(0) + 1e-12)

def track_env(yid):
    """drum onset envelope of st/<id>.wav (cached next to it as .dclash.npy) + grid"""
    if yid in _ENV: return _ENV[yid]
    p = os.path.join(SRC2, 'st', f'{yid}.dclash2.npy'); g = json.load(open(os.path.join(SRC2, 'st', f'{yid}.json')))
    if os.path.exists(p): e = np.load(p)
    else:
        import librosa
        y, _ = librosa.load(os.path.join(SRC2, 'st', f'{yid}.wav'), sr=SR_E); e = _env_from_audio(y)
        try: np.save(p, e)
        except OSError: pass
    downs = g['downs']; nb = int(round(4 * g['per'] / DT))
    lvl = np.array([e[:, int(d / DT):int(d / DT) + nb].mean() if int(d / DT) + nb <= e.shape[1] else 0.0 for d in downs])
    try:
        import sections; sec = sections.get(yid); drops = sec.get('drops') or []
        ref = np.median(np.concatenate([lvl[a:b] for a, b in drops])) if drops else np.percentile(lvl, 75)
    except Exception:
        ref = np.percentile(lvl, 75)
    _ENV[yid] = dict(e=e, downs=downs, per=g['per'], lvl=lvl, ref=float(ref) or 1e-9)
    return _ENV[yid]

def xcorr(x, y, per):
    """normalised xcorr of two equal-length envelopes over +-half a beat -> (lag_ms of peak, c_peak, c0)"""
    L = int(per / 2 / DT); n = min(len(x), len(y)); x = x[:n] - x[:n].mean(); y = y[:n] - y[:n].mean()
    den = np.linalg.norm(x) * np.linalg.norm(y) + 1e-12
    lags = np.arange(-L, L + 1)
    c = np.array([np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)]) for j in lags]) / den
    i = int(np.argmax(c)); z = np.abs(lags * DT * 1000) <= ZERO_MS
    return float(lags[i] * DT * 1000), float(c[i]), float(c[z].max())

def bar_metrics(x, y, per):
    """x, y: (2, n) kick/snare envelopes of one window. Kick vs kick and snare vs snare separately (a DJ lines up like with like;
    a combined envelope lets A's snare 'match' B's kick at a fake offset)."""
    lk, ck, c0k = xcorr(x[0], y[0], per); ls, cs_, c0s = xcorr(x[1], y[1], per)
    return dict(lag_k=round(lk, 1), cp_k=round(ck, 3), c0_k=round(c0k, 3), lag_s=round(ls, 1), cp_s=round(cs_, 3), c0_s=round(c0s, 3))

def bar_rows(pairs, A, B, win_bars=2):
    """pairs: [(a_src_time_s, b_src_time_s, a_bar, b_bar)] one per overlap bar (start of the bar in each deck's st audio, as played)."""
    rows = []; nb = int(round(4 * A['per'] / DT)); W = nb * win_bars
    for ta, tb, ka, kb in pairs:
        da = A['lvl'][ka] / A['ref'] if 0 <= ka < len(A['lvl']) else 0; db = B['lvl'][kb] / B['ref'] if 0 <= kb < len(B['lvl']) else 0
        r = dict(a_bar=ka, b_bar=kb, drums_a=round(float(da), 2), drums_b=round(float(db), 2))
        if da >= DRUM_FRAC and db >= DRUM_FRAC:
            ia, ib = int(round(ta / DT)), int(round(tb / DT))
            x, y = A['e'][:, ia:ia + W], B['e'][:, ib:ib + W]
            if min(x.shape[1], y.shape[1]) >= nb:
                r.update(bar_metrics(x, y, A['per']))
        rows.append(r)
    return rows

CP_MIN = float(os.environ.get('DRUMCLASH_CP_MIN', 0.2)); CLUSTER_MS = float(os.environ.get('DRUMCLASH_CLUSTER_MS', 15))

def _wrapd(x, y, beat_ms=60000 / 174):
    return abs(((x - y) + beat_ms / 2) % beat_ms - beat_ms / 2)

HIGH = float(os.environ.get('DRUMCLASH_HIGH', 0.5))  # confidence above which the clash is a veto-level fault (majority of bars)

def _bar_offset(r):
    """confident non-zero offset of one drum-on-drum bar, or None: kick AND snare xcorr both peak (>= CP_MIN, beating zero lag by
    >= GAIN_MIN) at the same |lag| > OFF_MS (within CLUSTER_MS)."""
    if 'lag_k' not in r: return None
    ok = lambda lag, cp, c0: abs(lag) > OFF_MS and cp >= CP_MIN and cp - c0 >= GAIN_MIN
    if ok(r['lag_k'], r['cp_k'], r['c0_k']) and ok(r['lag_s'], r['cp_s'], r['c0_s']) and _wrapd(r['lag_k'], r['lag_s']) <= CLUSTER_MS:
        return (r['lag_k'] + r['lag_s']) / 2
    return None

def summarize(rows):
    """confidence = share of drum-on-drum bars that agree (within CLUSTER_MS) on one confident kick+snare offset.
    level: 'clean' (<= FLAG = pro p95), 'gray' (FLAG..HIGH: mild penalty, list for an A/B), 'clash' (> HIGH: majority of bars agree)."""
    dd = [r for r in rows if 'lag_k' in r]
    if len(dd) < MIN_BARS:
        return dict(score=0.0, confidence=0.0, level='clean', n_dd=len(dd), flagged=False, cluster_lag_ms=None, why='no drum-on-drum overlap (< %d bars)' % MIN_BARS)
    o = [x for x in (_bar_offset(r) for r in dd) if x is not None]
    best, lag = 0, None
    for x in o:
        m = [y for y in o if _wrapd(x, y) <= CLUSTER_MS]
        if len(m) > best: best, lag = len(m), float(np.median(m))
    s = best / len(dd); level = 'clash' if s > HIGH else ('gray' if s > FLAG else 'clean')
    return dict(score=round(s, 3), confidence=round(s, 3), level=level, n_dd=len(dd), n_off=len(o), flagged=level == 'clash',
                cluster_lag_ms=None if lag is None else round(lag, 1))

def window_pairs(a, b, win, lock_ms=0.0):
    """engine window [kind, out_end, loop, in_begin, X] -> per-bar (ta, tb, ka, kb). Natural windows only ('n');
    loop families return None (not scored)."""
    if not win or win[0] != 'n': return None
    A, B = track_env(a), track_env(b); out_end, in_b, X = int(win[1]), int(win[3]), int(win[4])
    ps = []
    for j in range(X):
        ka, kb = out_end - X + j, in_b + j
        if 0 <= ka < len(A['downs']) and 0 <= kb < len(B['downs']):
            ps.append((A['downs'][ka], B['downs'][kb] - lock_ms / 1000.0, ka, kb))
    return ps

def window_clash(a, b, win, lock_ms=0.0):
    ps = window_pairs(a, b, win, lock_ms)
    if ps is None: return None
    rows = bar_rows(ps, track_env(a), track_env(b)); s = summarize(rows); s['rows'] = rows; return s

def flag_on(v=None):
    v = os.environ.get('DRUMCLASH', '0') if v is None else v
    return str(v).strip().lower() not in ('', '0', 'false', 'off', 'no', 'none')


def window_eval(a, b, win, lock_ms=0.0, lock_fallback=True):  # noqa
    """pick-time verdict for an engine window. If the decks agree on one offset and BLEND_LOCK will run, the lock fallback moves the
    incoming by that offset (as finephase.lock_decks does with DRUMCLASH on) and the RESIDUAL decides: a grid that steps inside a
    track (Ghetto Blaster: drop 2 sits 76 ms off drop 1) stays flagged after the lock."""
    s0 = window_clash(a, b, win, lock_ms)
    if s0 is None: return None
    s0.pop('rows', None); out = dict(raw=s0, lock_ms=lock_ms)
    if lock_fallback and s0['level'] != 'clean' and s0.get('cluster_lag_ms') is not None:
        s1 = window_clash(a, b, win, lock_ms + s0['cluster_lag_ms']); s1.pop('rows', None)
        out.update(fallback_lock_ms=round(lock_ms + s0['cluster_lag_ms'], 1), residual=s1)
        fin = s1
    else:
        fin = s0
    out.update(score=fin['score'], confidence=fin['confidence'], level=fin['level'], flagged=fin['flagged'], n_dd=fin['n_dd'])
    return out

def rendered_eval(A, B, s0, start, end, sr=44100, gate_db=20.0):
    """check on the rendered decks of one blend (blend_diag.crop_decks: mix-grid aligned, fader gains applied). A bar counts as
    drum-on-drum only when BOTH decks' percussive level is within gate_db of the louder deck's percussive peak level."""
    import librosa
    ya, yb = (librosa.resample(z.mean(1), orig_sr=sr, target_sr=SR_E) for z in (A, B))
    return decks_eval(ya, yb, s0, start, end, gate_db=gate_db)

def decks_eval(ya, yb, s0=0, start=None, end=None, gate_db=20.0):
    ea, eb = _env_from_audio(ya), _env_from_audio(yb); pa, pb = _perc_db(ya), _perc_db(yb)
    per = 60 / 174; bar = 4 * per; nb = int(round(bar / DT)); n = int(min(ea.shape[1], eb.shape[1]) / nb)
    la = np.array([pa[k * nb:(k + 1) * nb].mean() for k in range(n)]); lb = np.array([pb[k * nb:(k + 1) * nb].mean() for k in range(n)])
    ref = max(np.percentile(la, 95), np.percentile(lb, 95)); rows = []
    k0 = 0 if start is None else max(0, int(start - s0)); k1 = n if end is None else min(n, int(end - s0))
    for k in range(k0, k1):
        r = dict(bar=s0 + k, perc_a=round(float(la[k] - ref), 1), perc_b=round(float(lb[k] - ref), 1))
        if la[k] >= ref - gate_db and lb[k] >= ref - gate_db:
            i = k * nb; x, y = ea[:, i:i + 2 * nb], eb[:, i:i + 2 * nb]
            if min(x.shape[1], y.shape[1]) >= nb: r.update(bar_metrics(x, y, per))
        rows.append(r)
    out = summarize(rows); out['rows'] = rows; return out


# ---- v3 (2026-11-20 13:xx ET): off-lattice hits. Debugging hm09 B showed the decks' snare ATTACKS agree to 0.6 ms (A -17.5,
# B -18.1 ms vs the mix grid; rca_beats/snaretime.py), so there is no constant offset for v2 to find; what is 'off' is that B's
# intro build (bars 48-63) puts its hits between A's 16ths (20 % of B's strong onsets > 25 ms off A's 16th lattice; A's own: 1 %).
# v3 asks the question a DJ's ear asks: do the other deck's hits land on the reference deck's 16th-note lattice? It covers a
# constant flam (every hit off by the same lag) and an irregular / rolling / swung layer over a straight beat alike.
LAT_TOL_MS = float(os.environ.get('DRUMCLASH_LAT_TOL_MS', 25))   # a hit further than this from the reference lattice is 'off'
ON_FRAC = float(os.environ.get('DRUMCLASH_ON_FRAC', 0.3))          # onsets weaker than this x the deck's p90 strength are ignored
BAR_OFF = float(os.environ.get('DRUMCLASH_BAR_OFF', 0.677))        # bar 'off' when its off-lattice share > this = pro p95 per bar (734 pro bars, detector_calibration_v3.json)
FLAG3 = float(os.environ.get('DRUMCLASH_FLAG3', 0.307))            # pair confidence above this = gray = pro p95 (31 pros, detector_calibration_v3.json)

def _onsets(y, sr=SR_E):
    """drum hits only: onsets of the HPSS percussive part (a breakdown's vocal / pad note onsets are not beats)"""
    import librosa
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)); _, P = librosa.decompose.hpss(S, margin=2.0)
    M = librosa.power_to_db(librosa.feature.melspectrogram(S=P ** 2, sr=sr, n_mels=64))
    st = librosa.onset.onset_strength(S=M, sr=sr, hop_length=HOP)
    fr = librosa.onset.onset_detect(onset_envelope=st, sr=sr, hop_length=HOP)
    return fr * DT, st[fr] if len(fr) else np.zeros(0)

def _lattice(t, w, s16):
    """strength-weighted circular phase (s) and concentration r of onsets t on a 16th lattice of period s16"""
    if len(t) < 4 or w.sum() <= 0: return None, 0.0
    z = np.sum(w * np.exp(2j * np.pi * t / s16)) / w.sum(); return float(np.angle(z) / (2 * np.pi) * s16), float(abs(z))

def lattice_eval(ya, yb, per=60 / 174, s0=0, start=None, end=None, gate_db=20.0, up=None):
    """off-lattice confidence of one overlap. ya, yb: each deck alone (22.05 kHz mono, fader gains applied) on one timeline whose
    bar k starts at k*4*per. Onsets are picked on the overlap segment only (peak picking normalises to the segment, so a quiet
    build is not drowned by the incoming's later drop), kept when audible (deck's percussive level within gate_db of the pair's
    loud level at the hit). The reference deck is the one whose hits sit tighter on a 16th lattice; a bar counts when the
    reference deck's drums are up and the other deck has >= 2 audible hits; its off share = strength-weighted share of the other
    deck's hits more than LAT_TOL_MS from the reference lattice. Returns the summarize() dict shape (+ ref, per-bar rows)."""
    pa, pb = _perc_db(ya), _perc_db(yb); bar = 4 * per; nb = int(round(bar / DT)); s16 = per / 4
    n = int(min(len(pa), len(pb)) / nb)
    la = np.array([pa[k * nb:(k + 1) * nb].mean() for k in range(n)]); lb = np.array([pb[k * nb:(k + 1) * nb].mean() for k in range(n)])
    ref = max(np.percentile(la, 95), np.percentile(lb, 95))
    k0 = 0 if start is None else max(0, int(start - s0)); k1 = n if end is None else min(n, int(end - s0))
    def clean(why, rows=()):
        return dict(score=0.0, confidence=0.0, level='clean', n_dd=0, flagged=False, cluster_lag_ms=None, kind='lattice', why=why, rows=list(rows))
    if k1 - k0 < MIN_BARS: return clean('overlap < %d bars' % MIN_BARS)
    i0, i1 = k0 * nb * HOP, k1 * nb * HOP; T0 = k0 * bar
    def ons(y, pdb):
        t, w = _onsets(y[i0:i1]); t = t + T0; fr = np.clip((t / DT).astype(int), 0, len(pdb) - 1)
        lv = np.array([pdb[max(0, f - 2):f + 3].max() for f in fr]) - ref if len(fr) else np.zeros(0)
        keep = lv >= -gate_db; return t[keep], w[keep]
    (ta, wa), (tb, wb) = ons(ya, pa), ons(yb, pb)
    (fa, ra), (fb, rb) = _lattice(ta, wa, s16), _lattice(tb, wb, s16)
    if fa is None or fb is None: return clean('too few audible hits on one deck')
    # drums up per bar: given (pick time: the deck's own drop-relative drum level, DRUM_FRAC) or the percussive-level gate
    ua = np.array(up[0], bool) if up is not None else la >= ref - gate_db
    ub = np.array(up[1], bool) if up is not None else lb >= ref - gate_db
    na, nb_ = int(ua[k0:k1].sum()), int(ub[k0:k1].sum())
    # reference = the deck carrying a beat in more bars (tie: tighter on its 16th lattice)
    if (na, ra) >= (nb_, rb): refd, phi, uref, to, wo = 'a', fa, ua, tb, wb
    else: refd, phi, uref, to, wo = 'b', fb, ub, ta, wa
    dev = ((to - phi) + s16 / 2) % s16 - s16 / 2; rows = []; off = []; devs = []
    for k in range(k0, k1):
        m = (to >= k * bar) & (to < (k + 1) * bar); r = dict(bar=s0 + k, ref_up=bool(uref[k]), n=int(m.sum()))
        if r['ref_up'] and m.sum() >= 2:
            sh = float((wo[m] * (np.abs(dev[m]) * 1000 > LAT_TOL_MS)).sum() / wo[m].sum()); off.append(sh); devs += list(dev[m] * 1000)
            r.update(off_share=round(sh, 3), med_dev_ms=round(float(np.median(dev[m]) * 1000), 1))
        rows.append(r)
    if len(off) < MIN_BARS: return clean('fewer than %d bars with the reference beat up and hits on the other deck' % MIN_BARS, rows)
    conf = sum(1 for x in off if x > BAR_OFF) / len(off)
    level = 'clash' if conf > HIGH else ('gray' if conf > FLAG3 else 'clean')
    return dict(score=round(conf, 3), confidence=round(conf, 3), level=level, n_dd=len(off), flagged=level == 'clash', kind='lattice',
                ref=refd, r_ref=round(max(ra, rb), 3), r_other=round(min(ra, rb), 3), median_off_share=round(float(np.median(off)), 3),
                cluster_lag_ms=round(float(np.median(devs)), 1), rows=rows)

def rendered_lattice(A, B, s0, start, end, sr=44100):
    import librosa
    ya, yb = (librosa.resample(z.mean(1), orig_sr=sr, target_sr=SR_E) for z in (A, B))
    return lattice_eval(ya, yb, 60 / 174, s0, start, end)

_WAV = {}
def _st_audio(yid):
    if yid not in _WAV:
        import librosa
        _WAV[yid] = librosa.load(os.path.join(SRC2, 'st', f'{yid}.wav'), sr=SR_E)[0]
    return _WAV[yid]

def window_lattice(a, b, win, lock_ms=0.0):
    """pick-time lattice verdict for a natural engine window: each deck's st audio placed as the engine plays it (sample-exact),
    under an equal-power X-bar crossfade (the shape the fader approximates); the rendered hard check uses the real fader."""
    if not win or win[0] != 'n': return None
    A, B = track_env(a), track_env(b); out_end, in_b, X = int(win[1]), int(win[3]), int(win[4]); ka = out_end - X
    if ka < 0 or ka >= len(A['downs']) or in_b >= len(B['downs']): return None
    per = A['per']; n = int(round(X * 4 * per * SR_E)); ia = int(round(A['downs'][ka] * SR_E)); ib = int(round((B['downs'][in_b] - lock_ms / 1000.0) * SR_E))
    def seg(y, i):
        z = np.zeros(n, np.float32); s = y[max(0, i):max(0, i) + n - max(0, -i)]; z[max(0, -i):max(0, -i) + len(s)] = s; return z
    x = np.linspace(0, np.pi / 2, n); ya = seg(_st_audio(a), ia) * np.cos(x); yb = seg(_st_audio(b), ib) * np.sin(x)
    upa = [0 <= ka + j < len(A['lvl']) and A['lvl'][ka + j] / A['ref'] >= DRUM_FRAC for j in range(X)]
    upb = [0 <= in_b + j < len(B['lvl']) and B['lvl'][in_b + j] / B['ref'] >= DRUM_FRAC for j in range(X)]
    return lattice_eval(ya, yb, per, 0, 0, X, up=(upa, upb))

def _lock_add(v):
    """ms to add to blend_lock_ms (A minus B; + = delay B) that moves the other deck's hits onto the reference lattice"""
    d = v.get('cluster_lag_ms')
    if d is None or abs(d) <= OFF_MS: return None
    return -d if v.get('ref') == 'a' else d

KIND = os.environ.get('DRUMCLASH_KIND', 'lattice')

def window_eval3(a, b, win, lock_ms=0.0, lock_fallback=True):
    s0 = window_lattice(a, b, win, lock_ms)
    if s0 is None: return None
    s0.pop('rows', None); out = dict(raw=s0, lock_ms=lock_ms); fin = s0; add = _lock_add(s0)
    if lock_fallback and s0['level'] == 'clash' and add is not None and abs(lock_ms + add) <= 150:
        s1 = window_lattice(a, b, win, lock_ms + add); s1.pop('rows', None)
        out.update(fallback_lock_ms=round(lock_ms + add, 1), residual=s1); fin = s1 if s1['confidence'] < s0['confidence'] else s0
    out.update(score=fin['score'], confidence=fin['confidence'], level=fin['level'], flagged=fin['flagged'], n_dd=fin['n_dd'])
    return out


# ---- pulse term (2026-11-20 13:4x ET, hm09 B ground truth, rca_beats/hm09_truth.py): B's intro build (src bars 48-63) is a
# roll/stutter whose percussive periodicity runs off the 174 grid (tempogram 363 -> ~400 BPM, 1-beat autocorrelation 0.6 -> 0.0)
# played under A's full drop 2. No constant offset (attacks agree to <1 ms), no drift of the grids: the 'beat off' is one deck
# carrying a straight beat while the other carries audible percussion with NO 174 pulse.
def _pulse_rows(ya, yb, per, s0, k0, k1, gate_db=20.0):
    import librosa
    rows = []; pa, pb = _perc_db(ya), _perc_db(yb); nb = int(round(4 * per / DT)); L = int(round(per / DT))
    n = int(min(len(pa), len(pb)) / nb)
    la = np.array([pa[k * nb:(k + 1) * nb].mean() for k in range(n)]); lb = np.array([pb[k * nb:(k + 1) * nb].mean() for k in range(n)])
    ref = max(np.percentile(la, 95), np.percentile(lb, 95))
    def env(y):
        S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)); _, P = librosa.decompose.hpss(S, margin=2.0)
        return librosa.onset.onset_strength(S=librosa.power_to_db(librosa.feature.melspectrogram(S=P ** 2, sr=SR_E, n_mels=64)), sr=SR_E, hop_length=HOP)
    ea, eb = env(ya), env(yb)
    def ac(e, k):
        w = e[k * nb:(k + 2) * nb]
        if len(w) < nb + L: return None
        w = w - w.mean(); d = float(np.dot(w, w)); return None if d <= 0 else float(np.dot(w[:-L], w[L:]) / d)
    for k in range(max(0, k0), min(n, k1)):
        r = dict(bar=s0 + k, perc_a=round(float(la[k] - ref), 1), perc_b=round(float(lb[k] - ref), 1), ac_a=ac(ea, k), ac_b=ac(eb, k))
        if r['ac_a'] is not None and r['ac_b'] is not None and la[k] >= ref - gate_db and lb[k] >= ref - gate_db:
            # the deck with the stronger 174 pulse is the beat; the other's lack of pulse is the clash (0 = both pulse)
            r['pulse_gap'] = round(abs(r['ac_a'] - r['ac_b']), 3) if max(r['ac_a'], r['ac_b']) > 0 else 0.0
        rows.append(r)
    return rows

PULSE_BAR = float(os.environ.get('DRUMCLASH_PULSE_BAR', 0.528))  # = pro p95 of per-bar pulse_gap (607 pro bars, detector_calibration_pulse.json)
PULSE_FLAG = float(os.environ.get('DRUMCLASH_PULSE_FLAG', 0.273))  # = pro p95 of pair confidence (31 pros)

def pulse_summary(rows, bar_thr=None, flag=None):
    bar_thr = PULSE_BAR if bar_thr is None else bar_thr; flag = PULSE_FLAG if flag is None else flag
    v = [r['pulse_gap'] for r in rows if 'pulse_gap' in r]
    if len(v) < MIN_BARS: return dict(confidence=0.0, level='clean', n_dd=len(v), kind='pulse', why='< %d drum-on-drum bars' % MIN_BARS)
    c = sum(1 for x in v if x > bar_thr) / len(v); lvl = 'clash' if c > HIGH else ('gray' if c > flag else 'clean')
    return dict(confidence=round(c, 3), level=lvl, n_dd=len(v), kind='pulse', median_gap=round(float(np.median(v)), 3))

def rendered_pulse(A, B, s0, start, end, sr=44100):
    import librosa
    ya, yb = (librosa.resample(z.mean(1), orig_sr=sr, target_sr=SR_E) for z in (A, B))
    rows = _pulse_rows(ya, yb, 60 / 174, s0, int(start - s0), int(end - s0)); out = pulse_summary(rows); out['rows'] = rows; return out


# ---- pick time (pulse only). The pulse term is a property of each deck's own audio (does it carry a 174 pulse in that bar?), so
# it needs no alignment and can be read from per-track caches; only audibility depends on the fader, which pick time does not
# know (an equal-power guess missed hm09's early-in plateau), so pick time uses unity levels (upper bound) and only a MILD
# penalty; the rendered hard check (real fader) is the veto. The lattice term depends on the real render (fader, lock)
# and on pick-time st audio misread whole breakdowns (hm09's breakdown exit read 'clash'), so it is only used on the render.
def track_pulse(yid):
    p = os.path.join(SRC2, 'st', f'{yid}.pulse.json')
    if os.path.exists(p): return json.load(open(p))
    import librosa
    g = json.load(open(os.path.join(SRC2, 'st', f'{yid}.json'))); y = _st_audio(yid); per = g['per']; L = int(round(per / DT))
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)); _, P = librosa.decompose.hpss(S, margin=2.0)
    db = 10 * np.log10((P ** 2).sum(0) + 1e-12)
    e = librosa.onset.onset_strength(S=librosa.power_to_db(librosa.feature.melspectrogram(S=P ** 2, sr=SR_E, n_mels=64)), sr=SR_E, hop_length=HOP)
    nb = int(round(4 * per / DT)); lv, ac = [], []
    for d in g['downs']:
        i = int(round(d / DT)); lv.append(float(db[i:i + nb].mean()) if i + nb <= len(db) else -120.0)
        w = e[i:i + 2 * nb]
        if len(w) < nb + L: ac.append(None); continue
        w = w - w.mean(); q = float(np.dot(w, w)); ac.append(None if q <= 0 else float(np.dot(w[:-L], w[L:]) / q))
    out = dict(perc_db=lv, ac=ac)
    try: json.dump(out, open(p, 'w'))
    except OSError: pass
    return out

def window_pulse(a, b, win, gate_db=20.0):
    if not win or win[0] != 'n': return None
    A, B = track_pulse(a), track_pulse(b); out_end, in_b, X = int(win[1]), int(win[3]), int(win[4]); ka = out_end - X
    if ka < 0 or out_end > len(A['ac']) or in_b + X > len(B['ac']): return None
    ref = max(np.percentile(A['perc_db'][max(0, ka - 8):out_end], 95), np.percentile(B['perc_db'][in_b:in_b + X + 8], 95))
    rows = []
    for j in range(X):
        # unity level (no fader): an upper bound on audibility, so pick time says 'could clash'; the render decides
        aa, ab = A['ac'][ka + j], B['ac'][in_b + j]; la, lb = A['perc_db'][ka + j], B['perc_db'][in_b + j]
        r = dict(bar=j, ac_a=aa, ac_b=ab, perc_a=round(la - ref, 1), perc_b=round(lb - ref, 1))
        if aa is not None and ab is not None and la >= ref - gate_db and lb >= ref - gate_db:
            r['pulse_gap'] = round(abs(aa - ab), 3) if max(aa, ab) > 0 else 0.0
        rows.append(r)
    out = pulse_summary(rows); out['rows'] = rows; return out

_RANK = dict(clean=0, gray=1, clash=2)
def window_eval_pt(a, b, win, lock_ms=0.0):
    """pick-time verdict (pulse term) in the window_eval dict shape"""
    v = window_pulse(a, b, win)
    if v is None: return None
    v.pop('rows', None)
    return dict(raw=v, score=v['confidence'], confidence=v['confidence'], level=v['level'], flagged=v['level'] == 'clash', n_dd=v['n_dd'])

def rendered_combined(A, B, s0, start, end):
    """render verdict: the worse of the lattice term (constant flam / off-lattice hits) and the pulse term (straight beat vs
    a deck with no 174 pulse), each gated at its own pro p95"""
    l = rendered_lattice(A, B, s0, start, end); p = rendered_pulse(A, B, s0, start, end); l.pop('rows', None); p.pop('rows', None)
    w = l if _RANK[l['level']] >= _RANK[p['level']] else p
    return dict(w, lattice=l, pulse=p, cluster_lag_ms=l.get('cluster_lag_ms'), ref=l.get('ref'), flagged=w['level'] == 'clash')
