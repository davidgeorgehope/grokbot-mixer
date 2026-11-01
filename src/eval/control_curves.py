"""Reverse-engineer per-bar, per-deck fader/EQ curves of real DJ transitions from audio
(after Schwarz & Fourer, "Methods and datasets for DJ-mix reverse engineering", and Kim et al. ISMIR 2020 djmix-analysis).

1. Alignment: each source track is located in the mix by cross-correlating 8 s chunks of its log sub-band power
   (20 sub-bands, 23 ms frames) against the whole mix; a RANSAC line  mix_t = a + track_t / r  over the chunk hits gives
   the time-stretch ratio r and offset a. Chunk hits that sit on a parallel line with a different offset = a loop/jump.
2. Fit: in each transition window, mix power per sub-band s and frame f is modelled as
       M[f,s] ~ GA_k * cA[s] * A[f,s] + GB_k * cB[s] * B[f,s] + GN * N[s]
   (incoherent power sum; k = EQ band of s: low <150 Hz, mid 150-2000, high >2000, same split as our engine;
   cA/cB = per-sub-band calibration from solo bars of each deck; N = crowd/MC floor shape from solo residuals)
   solved by non-negative least squares per bar and band. Gain in dB = 10*log10(G). Fader = mid-band gain,
   EQ = band gain - fader.
CLI:  control_curves.py run   -> eval/control_curves.jsonl + eval/control_curves_summary.json
      control_curves.py validate -> eval/control_curves_validation.json
"""
import numpy as np, json, os, sys, subprocess
from scipy.optimize import nnls
SR = 22050; HOP = 512; NFFT = 2048; FPS = SR / HOP
EDGES = np.r_[np.geomspace(30, 150, 5), np.geomspace(150, 2000, 9)[1:], np.geomspace(2000, 10000, 9)[1:]]  # 20 sub-bands
LAM = float(os.environ.get('CC_LAM', 0.15))  # smoothness weight relative to one bar of data
BAND = np.r_[[0]*4, [1]*8, [2]*8]; BN = ['low', 'mid', 'high']
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load(path, sr=SR):
    raw = subprocess.run(['ffmpeg', '-v', 'quiet', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)

def bandpow(y):
    """frames x 20 sub-band power, computed in 60 s chunks (no full STFT in RAM)."""
    fr = np.fft.rfftfreq(NFFT, 1 / SR); idx = [(fr >= EDGES[i]) & (fr < EDGES[i + 1]) for i in range(20)]
    W = np.stack(idx, 1).astype(np.float32); win = np.hanning(NFFT).astype(np.float32); out = []
    n = 1 + max(0, (len(y) - NFFT) // HOP); step = 2048
    for f0 in range(0, n, step):
        f1 = min(n, f0 + step); fr_idx = np.arange(f0, f1)[:, None] * HOP + np.arange(NFFT)[None]
        X = np.abs(np.fft.rfft(y[np.minimum(fr_idx, len(y) - 1)] * win, axis=1)) ** 2
        out.append(X.astype(np.float32) @ W)
    return np.concatenate(out) + 1e-10

def _z(F):
    L = np.log(F); L = L - L.mean(0); return L / (L.std(0) + 1e-6)

def stretch(F, r, n):
    """track features resampled so frame j = track time j*r/FPS (r = track sec per mix sec)."""
    t = np.arange(n) * r; ok = t <= len(F) - 1
    i0 = np.clip(t.astype(int), 0, len(F) - 2); w = (t - i0)[:, None]
    G = F[i0] * (1 - w) + F[i0 + 1] * w; G[~ok] = 0; return G, ok

def locate(Fm, Ft, chunk_s=8.0, hop_s=4.0):
    """chunk hits (track_t, mix_t, peak z) by FFT cross-correlation of z-scored log sub-band power."""
    Zm = _z(Fm); Zt = _z(Ft); L = int(chunk_s * FPS); n = len(Zm); N = 1 << int(np.ceil(np.log2(n + L)))
    FM = np.fft.rfft(Zm, N, axis=0); hits = []
    # local energy of mix for normalised correlation
    csum = np.r_[0, np.cumsum((Zm ** 2).sum(1))]
    for c0 in range(0, len(Zt) - L, int(hop_s * FPS)):
        q = Zt[c0:c0 + L]; q = q - q.mean(0)
        if q.std() < 0.2: continue
        cc = np.fft.irfft(FM * np.conj(np.fft.rfft(q, N, axis=0)), N, axis=0).sum(1)[:n - L]
        en = np.sqrt(np.maximum(csum[L:n] - csum[:n - L], 1e-6) * (q ** 2).sum()); cc = cc / en
        k = int(np.argmax(cc)); zs = (cc[k] - np.median(cc)) / (cc.std() + 1e-9)
        hits.append((c0 / FPS, k / FPS, float(cc[k]), float(zs)))
    return np.array(hits)

def fit_line(h, rng=np.random.default_rng(0), tol=0.06):
    """RANSAC mix_t = a + track_t*s (s = 1/r). Returns (a, s, inlier mask)."""
    good = h[:, 3] > 6
    H = h[good]; best = (0, None)
    if len(H) < 3: return None
    for _ in range(400):
        i, j = rng.choice(len(H), 2, replace=False)
        if abs(H[j, 0] - H[i, 0]) < 8: continue
        s = (H[j, 1] - H[i, 1]) / (H[j, 0] - H[i, 0])
        if not 0.9 < s < 1.1: continue
        a = H[i, 1] - s * H[i, 0]; inl = np.abs(H[:, 1] - (a + s * H[:, 0])) < tol
        if inl.sum() > best[0]: best = (inl.sum(), inl)
    if best[1] is None or best[0] < 3: return None
    I = H[best[1]]; s, a = np.polyfit(I[:, 0], I[:, 1], 1)
    inl = np.abs(h[:, 1] - (a + s * h[:, 0])) < tol
    # secondary lines (loops / jumps): strong hits off the main line inside the played span, consistent among themselves
    off = h[(~inl) & (h[:, 3] > 6)]; resid = off[:, 1] - (a + s * off[:, 0]) if len(off) else np.array([])
    loops = []
    if len(resid):
        r = np.round(resid / 0.05) * 0.05
        for v in np.unique(r):
            m = np.abs(resid - v) < 0.08
            if m.sum() >= 3: loops.append(dict(offset_sec=round(float(v), 2), n_chunks=int(m.sum())))
    return dict(a=float(a), s=float(s), inl=inl, n_inl=int(inl.sum()), loops=loops,
                t0=float(h[inl, 0].min()), t1=float(h[inl, 0].max() + 8))

def fit_window(Fm, A, B, bar, t0, t1, soloA, soloB):
    """A, B: stretched source features on the mix frame grid (zeros where not playing). Returns per-bar gains."""
    def calib(src, solo):
        f0, f1 = int(solo[0] * FPS), int(solo[1] * FPS)
        if f1 - f0 < FPS * 4: return None, None
        r = np.median(Fm[f0:f1] / (src[f0:f1] + 1e-10), 0)
        res = np.maximum(Fm[f0:f1] - r * src[f0:f1], 0).mean(0)
        return r, res
    cA, nA = calib(A, soloA); cB, nB = calib(B, soloB)
    if cA is None or cB is None: return None
    Nshape = (nA + nB) / 2 + 1e-12
    nb = int((t1 - t0) / bar); fb = [(int((t0 + k * bar) * FPS), int((t0 + (k + 1) * bar) * FPS)) for k in range(nb)]
    out = [{'bar': k, 't': round(t0 + k * bar, 2)} for k in range(nb)]; r2s = np.zeros((nb, 3))
    for b in range(3):
        s = BAND == b; F0, F1 = fb[0][0], fb[-1][1]; sc = Fm[F0:F1][:, s].mean(0) + 1e-12  # one normalisation per window
        rows, ys = [], []; ncol = 3 * nb
        for k, (f0, f1) in enumerate(fb):
            m = Fm[f0:f1][:, s] / sc; a = A[f0:f1][:, s] * cA[s] / sc; bb = B[f0:f1][:, s] * cB[s] / sc
            X = np.zeros((m.size, ncol)); X[:, k] = a.ravel(); X[:, nb + k] = bb.ravel(); X[:, 2 * nb + k] = np.tile(Nshape[s] / sc, (f1 - f0, 1)).ravel()
            rows.append(X); ys.append(m.ravel())
        D = np.zeros((3 * (nb - 1), ncol)); w = np.sqrt(LAM * rows[0].shape[0])  # smoothness between neighbouring bars (linear power)
        for j in range(3):
            for k in range(nb - 1): D[j * (nb - 1) + k, j * nb + k] = w; D[j * (nb - 1) + k, j * nb + k + 1] = -w
        g, _ = nnls(np.vstack(rows + [D]), np.concatenate(ys + [np.zeros(len(D))]), maxiter=50 * ncol)
        for k in range(nb):
            out[k][BN[b]] = [round(10 * np.log10(min(max(g[k], 1e-4), 4)), 2), round(10 * np.log10(min(max(g[nb + k], 1e-4), 4)), 2)]
            pred = rows[k] @ g; yv = ys[k]; r2s[k, b] = 1 - ((yv - pred) ** 2).sum() / (((yv - yv.mean()) ** 2).sum() + 1e-12)
    for k in range(nb): out[k]['r2'] = round(float(r2s[k].mean()), 3)
    return out

def transition(Fm, mixdur, bar, TA, TB, FA, FB):
    """TA/TB: alignment dicts; FA/FB: raw track features. Window: 32 bars around the overlap of both decks' played spans."""
    n = len(Fm)
    def grid(T, F):
        G, ok = stretch(F, 1 / T['s'], n - int(T['a'] * FPS) if T['a'] > 0 else n)
        Z = np.zeros_like(Fm); o = int(round(T['a'] * FPS))
        src = np.arange(n) - o; v = (src >= 0) & (src < len(G)); Z[v] = G[src[v]]; return Z
    aS0, bE0 = TA['a'] + TA['s'] * TA['t0'], TB['a'] + TB['s'] * TB['t1']
    bS0, aE0 = TB['a'] + TB['s'] * TB['t0'], TA['a'] + TA['s'] * TA['t1']
    TA = refine(Fm, TA, FA, max(aS0, bS0 - 40), bS0 - 1); TB = refine(Fm, TB, FB, aE0 + 1, min(bE0, aE0 + 40))
    A = grid(TA, FA); B = grid(TB, FB)
    # played spans in mix time (inlier chunk range)
    aS, aE = TA['a'] + TA['s'] * TA['t0'], TA['a'] + TA['s'] * TA['t1']
    bS, bE = TB['a'] + TB['s'] * TB['t0'], TB['a'] + TB['s'] * TB['t1']
    if bS > aE + 30 or aS > bS: return None
    # bar grid phase: incoming track's first inlier chunk, snapped back in whole bars
    t0 = max(bS - 16 * bar, aS + 8 * bar); t1 = min(aE + 16 * bar, bE - 8 * bar, mixdur - 1)
    k0 = np.ceil((t0 - bS) / bar); t0 = bS + k0 * bar
    if t1 - t0 < 8 * bar: return None
    soloA = (max(aS, t0 - 24 * bar), min(bS, t0 + 2 * bar) - 2)  # before B's span starts
    soloB = (max(aE, t1 - 2 * bar) + 2, min(bE, t1 + 24 * bar))
    rows = fit_window(Fm, A, B, bar, t0, t1, soloA, soloB)
    if rows is None: return None
    for r in rows: r['bar_rel_in'] = int(round((r['t'] - bS) / bar))  # bars since the incoming deck's first audible chunk
    return rows

def refine(Fm, T, F, m0, m1, span=8, step=0.25):
    """sub-frame offset refinement (+-span frames) maximising log-power correlation over a solo stretch [m0, m1] s."""
    if m1 - m0 < 4: return T
    f0, f1 = int(m0 * FPS), int(m1 * FPS); Lm = np.log(Fm[f0:f1]); Lm = Lm - Lm.mean(0); best = (-9, 0)
    for d in np.arange(-span, span + step, step):
        t = (np.arange(f0, f1) / FPS - (T['a'] + d / FPS)) / T['s'] * FPS
        if t.min() < 0 or t.max() >= len(F) - 1: continue
        i0 = t.astype(int); w = (t - i0)[:, None]; G = np.log(F[i0] * (1 - w) + F[i0 + 1] * w); G = G - G.mean(0)
        c = (G * Lm).sum() / np.sqrt((G ** 2).sum() * (Lm ** 2).sum())
        if c > best[0]: best = (c, d)
    T = dict(T); T['a'] += best[1] / FPS; T['refine_corr'] = round(float(best[0]), 3); return T

# ---------- curve descriptors ----------
def describe(rows, thr=-12):
    """overlap & handoff stats from per-bar curves (dB; deck 0 = outgoing, 1 = incoming)."""
    def on(b, d): return np.array([r[BN[b]][d] for r in rows])
    L = {b: (on(i, 0), on(i, 1)) for i, b in enumerate(BN)}; n = len(rows)
    def first(x, c): w = np.where(c(x))[0]; return int(w[0]) if len(w) else None
    def last(x, c): w = np.where(c(x))[0]; return int(w[-1]) if len(w) else None
    d = {}
    for b in BN:
        o, i = L[b]; ia = first(i, lambda x: x > thr); oe = last(o, lambda x: x > thr)
        d[f'{b}_in_bar'] = ia; d[f'{b}_out_bar'] = oe
        d[f'{b}_overlap_bars'] = None if ia is None or oe is None else max(0, oe - ia + 1)
        # monotonic? count sign reversals of >=3 dB in the smoothed curve while audible
        for nm, x in (('out', o), ('in', i)):
            xs = np.convolve(x, np.ones(2) / 2, 'same'); dx = np.diff(xs); big = dx[np.abs(dx) >= 3]
            d[f'{b}_{nm}_reversals'] = int((np.diff(np.sign(big)) != 0).sum()) if len(big) > 1 else 0
            d[f'{b}_{nm}_max_step_db'] = round(float(np.abs(dx).max()), 1) if len(dx) else 0
            # non-monotonic excursion: outgoing rebound above its running min / incoming dip below its running max (audible part)
            aud = x > -20
            d[f'{b}_{nm}_rebound_db'] = round(float(max([x[k] - x[:k + 1][aud[:k + 1]].min() for k in range(n) if aud[k]] or [0])), 1) if nm == 'out' else \
                round(float(max([x[:k + 1][aud[:k + 1]].max() - x[k] for k in range(n) if aud[k]] or [0])), 1)
    lo, li = L['low']
    both = (lo > -6) & (li > -6); d['low_both_full_bars'] = int(both.sum())
    sw = next((k for k in range(n) if lo[k] < -6 and np.median(lo[k:k + 4]) < -6 and li[k] > -6), None); d['bass_swap_bar'] = sw
    if sw is not None and 0 < sw < n - 1:
        d['bass_swap_len_bars'] = int(((li > -15) & (lo > -15)).sum())
        d['bass_out_drop_db_per_bar'] = round(float(min(np.diff(lo[max(0, sw - 2):sw + 3]))), 1)
    # outgoing decay shape (mid band = fader proxy): time from -3 dB to -20 dB, and curvature (lin vs late)
    mo = L['mid'][0]; a3 = first(mo, lambda x: x < -3); a20 = first(mo, lambda x: x < -20)
    d['out_fade_3to20_bars'] = None if a3 is None or a20 is None else a20 - a3
    hi_o, hi_i = L['high']; d['high_cut_before_fader'] = None
    h6 = first(hi_o - mo, lambda x: x < -6); d['out_high_cut_bar'] = h6
    i6 = first(L['high'][1] - L['mid'][1], lambda x: x < -6); d['in_high_cut'] = i6 is not None
    d['in_low_cut_bars'] = int(((li - L['mid'][1] < -6) & (L['mid'][1] > -12)).sum())
    d['out_low_cut_bars'] = int(((lo - mo < -6) & (mo > -12)).sum())
    return d

# ---------- validation on our own renderer ----------
def validate(out=os.path.join(ROOT, 'eval/control_curves_validation.json'), ids=('sObzaBqaBRQ', 'q_cZZY0BehE')):
    """Render A->B with src2/engine.render_deck and known lanes, then recover them blind (alignment included).
    Cases: (1) plain render, (2) mix varispeed +1.5% + tanh saturation + pink noise at -30 dB (live-set conditions)."""
    import tempfile, soundfile as sf
    sys.path.insert(0, os.path.join(ROOT, 'src2')); cwd = os.getcwd(); os.chdir(os.path.join(ROOT, 'src2'))
    import engine
    E = engine; BARe = E.BAR; X0 = 48; NB = 96  # A plays bars 0..95, B enters at mix bar 48 for 48 bars of overlap region
    ga = lambda u: float(np.cos(np.clip(u, 0, 1) * np.pi / 2)); gb = lambda u: float(np.sin(np.clip(u, 0, 1) * np.pi / 2))
    truth_cases = {
      'monotonic': dict(A_gain=[[0, 1], [X0 + 16, 1], [X0 + 32, 0]], B_gain=[[X0, 0], [X0 + 16, 1]],
                        A_low=[[X0 + 15, 1], [X0 + 17, 0]], B_low=[[X0 + 15, 0], [X0 + 17, 1]],
                        B_high=[[X0 + 7, 0], [X0 + 9, 1]]),
      'riding':    dict(A_gain=[[0, 1], [X0 + 8, 1], [X0 + 10, 0.5], [X0 + 14, 0.5], [X0 + 16, 1], [X0 + 20, 1], [X0 + 32, 0]],
                        B_gain=[[X0, 0], [X0 + 16, 1]], A_low=[[X0 + 15, 1], [X0 + 17, 0]], B_low=[[X0 + 15, 0], [X0 + 17, 1]], B_high=[])}
    res = {}
    gA_, gB_ = None, None
    for cname, tc in truth_cases.items():
        dA = dict(id=ids[0], start_bar=0, full_map=[[16 + k, 'mix'] for k in range(NB)], auto=dict(gain=tc['A_gain'], low=tc['A_low']))
        dB = dict(id=ids[1], start_bar=X0, full_map=[[k, 'mix'] for k in range(NB)], auto=dict(gain=tc['B_gain'], low=tc['B_low'], high=tc['B_high']))
        yA = E.render_deck(dA); yB = E.render_deck(dB); n = int((X0 + NB) * E.BS); M = np.zeros((n, 2), np.float32)
        M[:len(yA)] += yA; i0 = int(X0 * E.BS); M[i0:i0 + len(yB)] += yB[:n - i0]
        srcA = E.track(ids[0])['st']['mix']; srcB = E.track(ids[1])['st']['mix']
        for variant in ('plain', 'live'):
            Mv = M.mean(1)
            if variant == 'live':
                Mv = np.interp(np.arange(0, len(Mv) - 1, 1.015), np.arange(len(Mv)), Mv).astype(np.float32)  # +1.5% tempo
                Mv = np.tanh(1.5 * Mv) / 1.5; rng = np.random.default_rng(1); w = np.cumsum(rng.standard_normal(len(Mv))); w -= np.convolve(w, np.ones(4410) / 4410, 'same')
                Mv = Mv + w / np.abs(w).max() * 10 ** (-40 / 20) * np.abs(Mv).max()
            with tempfile.TemporaryDirectory() as td:
                for nm, y in (('m', Mv), ('a', srcA.mean(1)), ('b', srcB.mean(1))): sf.write(f'{td}/{nm}.wav', y, E.SR)
                ym, ya, yb = (load(f'{td}/{x}.wav') for x in 'mab')
            Fm, FA, FB = bandpow(ym), bandpow(ya), bandpow(yb)
            TA = fit_line(locate(Fm, FA)); TB = fit_line(locate(Fm, FB))
            sp = 1.015 if variant == 'live' else 1.0; bar = BARe / sp
            rows = transition(Fm, len(ym) / SR, bar, TA, TB, FA, FB)
            # truth per estimated bar: engine lanes at mix bar = t*sp/BARe (+ half bar centre)
            err = {b: [] for b in BN}; errsw = []; per = []
            for r in rows:
                mb = (r['t'] + bar / 2) * sp / BARe
                def lane(p, x, dflt=1.0): return float(np.interp(x, [q[0] for q in p], [q[1] for q in p])) if p else dflt
                # engine: band gain = fader * (1 - (1-lane)) for low/high, as amplitude -> dB
                gAm, gBm = lane(tc['A_gain'], mb), lane(tc['B_gain'], mb) if mb >= X0 else 0.0
                tru = {'mid': (gAm, gBm), 'low': (gAm * lane(tc['A_low'], mb), gBm * lane(tc['B_low'], mb)),
                       'high': (gAm, gBm * lane(tc['B_high'], mb))}
                for b in BN:
                    for dk in (0, 1):
                        t_db = 20 * np.log10(max(tru[b][dk], 1e-2))
                        if t_db > -20: err[b].append(abs(r[b][dk] - t_db))  # audible range only (below -20 dB the deck is masked)
                per.append(dict(mixbar=round(mb, 1), est={b: r[b] for b in BN}, true={b: [round(20 * np.log10(max(v, 1e-2)), 1) for v in tru[b]] for b in BN}))
            dsc = describe(rows)
            res[f'{cname}_{variant}'] = dict(
                align=dict(A_ratio_err=round(abs(1 / TA['s'] - sp), 4), B_ratio_err=round(abs(1 / TB['s'] - sp), 4),
                           B_offset_err_ms=round(1000 * abs(TB['a'] - (X0 * BARe - E.track(ids[1])['d0']) / sp), 1),
                           A_offset_err_ms=round(1000 * abs(TA['a'] - (-(E.track(ids[0])['d0'] + 16 * BARe)) / sp), 1)),
                median_abs_err_db={b: round(float(np.median(err[b])), 2) for b in BN},
                p90_abs_err_db={b: round(float(np.percentile(err[b], 90)), 2) for b in BN},
                est_bass_swap_mixbar=None if dsc['bass_swap_bar'] is None else round(per[dsc['bass_swap_bar']]['mixbar'], 1),
                true_bass_swap_mixbar=X0 + 16, out_mid_rebound_db_est=dsc['mid_out_rebound_db'], out_mid_rebound_db_true=6.0 if cname == 'riding' else 0.0, r2=round(float(np.median([r['r2'] for r in rows])), 3),
                bars=per)
            print(cname, variant, {k: v for k, v in res[f'{cname}_{variant}'].items() if k != 'bars'}, flush=True)
    os.chdir(cwd); json.dump(res, open(out, 'w'), indent=1); return res
