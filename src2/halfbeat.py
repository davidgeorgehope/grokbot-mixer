"""Half-beat grid check (2026-11-11 RCA, Shine In -> Dusk To Dawn rated 2/5).

prep.grid() fits the beat phase with a broadband onset comb and prep/fixgrid only choose among the four whole-beat
downbeats, so a grid that locked onto the off-beat (every beat half a beat late or early) was never tested. Nu:Tone
"Shine In" had exactly that: its kicks and snares sat on grid beats x.42, and our two decks played 158 ms apart.

This module scores a track's grid against the same grid shifted half a beat using the drum pattern:
  * per drum bar (bar['drums'] within 6 dB of its 75th percentile) the kick (30-150 Hz) and snare (1.5-5 kHz)
    onset envelopes are folded onto NB bins per bar;
  * template: snare on beats 2 and 4, kick on beat 1 (each bin max-pooled +-1 bin, z-scored folds);
  * 'whole' = best template score at the four whole-beat downbeats (+-2 bins), 'half' = best at the four
    half-beat ones. The grid is half a beat off when half - whole >= MARGIN (and >= MIN_BARS drum bars).
check(b) only reads; apply(b) shifts the grid (beats, downs, phrases), re-samples the bar features in time,
refreshes 'all/low/hat' from the audio and drops the bar-indexed caches. A copy of the old grid is kept in
st/<id>.json.prehalf (once). CLI: python3 halfbeat.py [--apply] [ids...]  (default: every st/<id>.json with a wav)."""
import json, os, sys, glob
import numpy as np

SR = 44100; T = 174.0; BEAT = 60 / T; BAR = 4 * BEAT
NB = 64                      # bins per bar (16 per beat, 21.6 ms)
HOP = 128
MARGIN = float(os.environ.get('HALFBEAT_MARGIN', 0.5))   # z-units the half-beat phase must win by
MIN_BARS = int(os.environ.get('HALFBEAT_MIN_BARS', 16))
_CACHES = ('onset.npy', 'sections.json', 'feat.npz', 'beat.npz', 'dnb_lv.npz')


def _flux(y, lo, hi, sr=SR, hop=HOP):
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [lo, hi], 'band', fs=sr, output='sos') if lo > 0 else butter(4, hi, 'low', fs=sr, output='sos')
    z = sosfiltfilt(sos, y)
    n = len(z) // hop
    e = np.sqrt((z[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    return np.maximum(np.diff(e, prepend=e[:1]), 0.0)


def drum_envs(y, sr=SR):
    """(kick, snare) onset envelopes at HOP; y mono"""
    return _flux(y, 30, 150, sr), _flux(y, 1500, 5000, sr)


def fold(env, downs, mask, sr=SR, hop=HOP, nb=NB):
    """bar-folded envelope: bin j holds the max over its whole span (centred on downbeat + j/nb bar), averaged over masked bars.
    Point-sampling the narrow flux peaks aliased at 64 bins (a correct grid read as half off)."""
    fr = sr / hop; acc = np.zeros(nb); n = 0; w = BAR / nb
    for k in range(min(len(downs), len(mask))):
        if not mask[k]:
            continue
        lo = np.floor((downs[k] + (np.arange(nb) - 0.5) * w) * fr).astype(int)
        hi = np.ceil((downs[k] + (np.arange(nb) + 0.5) * w) * fr).astype(int)
        if hi[-1] + 1 >= len(env) or lo[0] < 0:
            continue
        acc += np.array([env[a:b + 1].max() for a, b in zip(lo, hi)]); n += 1
    return acc / max(n, 1), n


def _z(f):
    return (f - f.mean()) / (f.std() + 1e-9)


def template_scores(K, S, nb=NB):
    """score(s) for every bin shift s: snare on beats 2, 4 and kick on beat 1 of a bar that starts s bins after the grid downbeat"""
    K, S = _z(K), _z(S); q = nb // 4
    pk = lambda f, i: max(f[(i - 1) % nb], f[i % nb], f[(i + 1) % nb])
    return np.array([pk(S, s + q) + pk(S, s + 3 * q) + 0.5 * pk(K, s) for s in range(nb)])


def phase_from_folds(K, S, nb=NB):
    sc = template_scores(K, S, nb); q = nb // 4; w = max(1, nb // 32)
    def best(centres):
        cand = [(sc[(c + d) % nb], (c + d) % nb) for c in centres for d in range(-w, w + 1)]
        top = max(v for v, _ in cand)
        # near-ties (a straight kick on 1 and 3 makes the bar symmetric): the smallest move wins
        near = [(abs(((s_ + nb // 2) % nb) - nb // 2), -v, s_) for v, s_ in cand if v >= top - 0.25]
        _, v, s_ = min(near); return -v, s_
    whole, sw = best([0, q, 2 * q, 3 * q]); half, sh = best([q // 2, q + q // 2, 2 * q + q // 2, 3 * q + q // 2])
    return dict(whole=round(float(whole), 3), half=round(float(half), 3), margin=round(float(half - whole), 3),
                shift_whole_bins=int(sw), shift_half_bins=int(sh))


def offbeat_ratio(env, beats, sr=SR, hop=HOP):
    """RCA audit heuristic: mean envelope peak half a beat after each grid beat / at the beat (>= 1: suspicious)"""
    fr = sr / hop; w = int(0.02 * fr)
    def pk(t):
        i = int(t * fr); return env[max(0, i - w):i + w + 1].max() if i + w < len(env) else 0.0
    on = np.mean([pk(t) for t in beats[2:-2]]); off = np.mean([pk(t + BEAT / 2) for t in beats[2:-2]])
    return float(off / (on + 1e-12))


def drum_mask(g, K=None, S=None, sr=SR, hop=HOP):
    """drum bars: bar['drums'] (else 'all') within 6 dB of its 75th percentile; at prep time (no bar features yet)
    the bars whose kick+snare onset energy is in the top half"""
    B = g.get('bar') or {}
    if B.get('drums') or B.get('all'):
        dr = np.array(B.get('drums') or B['all'], float)
        return dr > np.percentile(dr, 75) - 6
    fr = sr / hop; d = np.array(g['downs'], float); e = K + S
    v = np.array([e[int(a * fr):int((a + BAR) * fr)].sum() for a in d])
    return v >= np.median(v)


def analyse(y, g, sr=SR):
    """grid check on mono audio y (at sr) and grid dict g (downs, beats, bar features)"""
    downs = np.array(g['downs'], float); K, S = drum_envs(y, sr)
    mask = drum_mask(g, K, S, sr)
    fK, n = fold(K, downs, mask, sr); fS, _ = fold(S, downs, mask, sr)
    r = phase_from_folds(fK, fS)
    r['drum_bars'] = int(n)
    r['offbeat_ratio'] = round(offbeat_ratio(K + S, np.array(g.get('beats') or downs), sr), 3)
    r['half_off'] = bool(n >= MIN_BARS and r['margin'] >= MARGIN)
    r['uncertain'] = bool(n >= MIN_BARS and 0 < r['margin'] < MARGIN)
    s = r['shift_half_bins'] if r['half_off'] else r['shift_whole_bins']
    sh = s * BAR / NB
    if sh > BAR / 2:
        sh -= BAR
    r['shift_sec'] = round(float(sh), 4)   # move the downbeats by this much (half_off: an odd number of half beats)
    return r



# ---- render-time deck-vs-deck check (used by mix_simple.py and the mix test suite) ----
HB_MARGIN_R = float(os.environ.get('HALFBEAT_MARGIN_R', 0.0))  # fail when the median half-beat r beats the lag-0 r at all


def deck_lags(oa, ob, wa, wb, mask=None, sr=SR, hop=512):
    """per-bar onset xcorr between two decks (oa/ob: per-bar onset envelopes, onsets.ensure) over source bars wa/wb,
    searched over +-BEAT/2. r0 = best within +-BEAT/8 of lag 0 (mix_simple's drum-fight R), rh = best within +-BEAT/8
    of +-BEAT/2, lag_ms = median signed best lag, bars = bars used (mask[k] False skips blend bar k)."""
    fps = sr / hop; ml = max(1, int((BEAT / 8) * fps)); mh = int(round((BEAT / 2) * fps)); r0 = []; rh = []; lg = []
    for k, (xa, xb) in enumerate(zip(wa, wb)):
        if xa >= len(oa) or xb >= len(ob) or xa < 0 or xb < 0 or (mask is not None and not mask[k]):
            continue
        ea = oa[xa] - oa[xa].mean(); eb = ob[xb] - ob[xb].mean(); na, nb_ = np.linalg.norm(ea), np.linalg.norm(eb)
        if na < 1e-9 or nb_ < 1e-9:
            continue
        c = np.correlate(ea / na, eb / nb_, mode='full'); m = len(c) // 2
        r0.append(float(c[m - ml:m + ml + 1].max()))
        rh.append(float(max(c[m + mh - ml:m + mh + ml + 1].max(), c[m - mh - ml:m - mh + ml + 1].max())))
        w = c[m - mh - ml:m + mh + ml + 1]; lg.append((int(np.argmax(w)) - (mh + ml)) * 1000 / fps)
    if not r0:
        return dict(r0=1.0, rh=0.0, lag_ms=0.0, bars=0)
    return dict(r0=float(np.median(r0)), rh=float(np.median(rh)), lag_ms=float(np.median(lg)), bars=len(r0))


HB_MIN_RH = float(os.environ.get('HALFBEAT_MIN_RH', 0.3))  # the half-beat lag must itself lock (Mix 07 OYzCe>cxS6: r0 0.14 vs rh 0.18 is two uncorrelated decks, not an off-beat lock)


def verdict(q, margin=None):
    m = HB_MARGIN_R if margin is None else margin
    q = dict(q); q['fail'] = bool(q['bars'] >= 4 and q['rh'] >= HB_MIN_RH and q['rh'] > q['r0'] + m)
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in q.items()}


def _drums_on(b):
    d = np.array(json.load(open(f'st/{b}.json'))['bar'].get('drums') or json.load(open(f'st/{b}.json'))['bar']['all'], float)
    return d > np.percentile(d, 75) - 8


HB_PHASE = float(os.environ.get('HALFBEAT_PHASE', 0.25))     # fail when the decks' drum phases sit >= this many beats apart (closer to half a beat than to lag 0)
HB_MIN_STRENGTH = float(os.environ.get('HALFBEAT_MIN_STRENGTH', MARGIN))  # both decks' template fit must beat its half-beat-away fit by this (z-units)
_ENV = {}


def _envs(b):
    if b not in _ENV:
        _ENV[b] = drum_envs(_load(b))
    return _ENV[b]


def beat_phase(fK, fS, nb=NB):
    """(phase in beats [-0.5, 0.5), strength) of a bar fold: the sub-beat offset at which the snare-on-2-and-4 template
    (template_scores, best over the four whole-beat downbeats) fits, and by how much it beats the fit half a beat away
    (z-units, like MARGIN). Template-based so a 2-step kick on the 'and' of 3 does not pull the phase."""
    sc = template_scores(fK, fS, nb); q = nb // 4
    sb = np.array([max(sc[j + k * q] for k in range(4)) for j in range(q)])
    j = int(np.argmax(sb)); s = float(sb[j] - sb[(j + q // 2) % q])
    return ((j + q // 2) % q - q // 2) / q, s


def deck_phase(b, bars, g=None):
    """drum phase of track b over its source bars (drum bars only); g = grid dict (default st/<b>.json)"""
    g = g or json.load(open(f'st/{b}.json')); K, S = _envs(b); downs = np.array(g['downs'], float)
    m = np.zeros(len(downs), bool)
    for k in bars:
        if 0 <= k < len(downs):
            m[k] = True
    fK, n = fold(K, downs, m); fS, _ = fold(S, downs, m)
    ph, s = beat_phase(fK, fS)
    return ph, s, n


def blend_check(a, b, wa, wb, ga=None, gb=None):
    """half-beat verdict for one blend from source bars wa (outgoing) / wb (incoming), drum-on-drum bars only.
    Basis: each deck's drum phase inside the beat (snare-on-2-and-4 template on the kick/snare fold over the overlap bars, on that deck's grid). With the
    grids lined up bar for bar the decks' hits land dphase beats apart; fail when that is closer to half a beat than to 0.
    Fails only when that AND the per-bar onset xcorr agree (rh at a half-beat lag beats r0 at lag 0, verdict()). Each alone
    misfires on the calibration set: the xcorr read 'half-beat better' on the Joe Syntax pair after the fix too (Dusk To
    Dawn's busy off-beat percussion); the drum phase read +-0.375 beat on -n50uo8so4U's intro in Mix 07 and Mix 08
    (r0 0.74/0.66 > rh 0.63/0.55: aligned). Calibration 2026-11-11: Mix 05 v8, 06 i12, 07 r17, 08 r11c 0 fails;
    the Joe pair on the old grid fails, on the re-gridded one passes."""
    import onsets
    dA, dB = _drums_on(a), _drums_on(b)
    mask = [xa < len(dA) and xb < len(dB) and xa >= 0 and xb >= 0 and dA[xa] and dB[xb] for xa, xb in zip(wa, wb)]
    q = deck_lags(onsets.ensure(a), onsets.ensure(b), wa, wb, mask)
    q = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in q.items()}
    sa = [xa for xa, m in zip(wa, mask) if m]; sb = [xb for xb, m in zip(wb, mask) if m]
    if len(sa) < 4:
        return dict(q, fail=False, basis='drum-phase+lag', note='< 4 drum-on-drum bars')
    pa, stra, _ = deck_phase(a, sa, ga); pb, strb, _ = deck_phase(b, sb, gb)
    d = (pa - pb + 0.5) % 1.0 - 0.5
    phase_fail = bool(abs(d) >= HB_PHASE and min(stra, strb) >= HB_MIN_STRENGTH)
    lag_fail = verdict(q)['fail']
    return dict(q, phase_fail=phase_fail, lag_fail=lag_fail, fail=phase_fail and lag_fail, phase_a=round(pa, 3), phase_b=round(pb, 3), dphase_beats=round(d, 3), dphase_ms=round(d * BEAT * 1000, 1),
                strength=round(min(stra, strb), 3), basis='drum-phase+lag')


def meta_blends(meta):
    """(a, b, wa, wb) source bars of both decks for every blend in a mix meta (decks[i].full_map, trans[i] start/end)"""
    out = []
    for i, t in enumerate(meta['trans']):
        A, B = meta['decks'][i], meta['decks'][i + 1]
        s, e = int(t['start_bar']), int(t['end_bar'])
        wa = [A['full_map'][k - A['start_bar']][0] for k in range(s, e) if 0 <= k - A['start_bar'] < len(A['full_map'])]
        wb = [B['full_map'][k - B['start_bar']][0] for k in range(s, e) if 0 <= k - B['start_bar'] < len(B['full_map'])]
        n = min(len(wa), len(wb)); out.append((t['a'], t['b'], wa[:n], wb[:n]))
    return out

def _load(b):
    import soundfile as sf
    y, _ = sf.read(f'st/{b}.wav', dtype='float32', always_2d=True)
    return y.mean(1)


def check(b):
    g = json.load(open(f'st/{b}.json'))
    return analyse(_load(b), g)


def _fine(y, downs, sr=SR, win=0.025):
    """1-ms comb refinement (+-25 ms) of the shifted grid on kick+snare hits"""
    K, S = drum_envs(y, sr); e = K / (K.max() + 1e-12) + S / (S.max() + 1e-12); fr = sr / HOP
    beats = (downs[:, None] + np.arange(4)[None] * BEAT).ravel()
    offs = np.arange(-win, win + 1e-9, 0.001)
    sc = [np.interp((beats + o) * fr, np.arange(len(e)), e).sum() for o in offs]
    return float(offs[int(np.argmax(sc))])


def shift_grid(g, y, sr, r):
    """beats / downs / phrases of grid dict g moved by r['shift_sec'] plus a 1-ms refinement; returns (new g, old downs, new downs).
    Bars stay aligned in time (new bar k starts within half a bar of old bar k); bar features are NOT touched here."""
    old = np.array(g['downs'], float); dur = len(y) / sr
    new = old + r['shift_sec']
    new = new + _fine(y, new[(new > 0) & (new < dur - BAR)], sr)
    new = new[(new >= 0) & (new + BAR <= dur + 1e-6)]
    beats = np.arange(new[0] % BEAT, dur - 0.01, BEAT)
    phr0 = g['phrases'][0] if g.get('phrases') else old[0]
    q = int(np.argmin(np.abs(new - phr0 - r['shift_sec'])))
    g = dict(g, downs=new.tolist(), beats=beats.tolist(), phrases=new[q % 8::8].tolist(),
             halfbeat=dict(r, applied=True, old_d0=float(old[0]), new_d0=float(new[0])))
    return g, old, new


def fix_grid(g, y, sr=SR):
    """prep-time entry (prep.py, fixgrid.py): (grid, report); the grid is shifted only when the check says half a beat off"""
    r = analyse(y, g, sr)
    if r['half_off']:
        g, _, _ = shift_grid(g, y, sr, r)
    else:
        g = dict(g, halfbeat=dict(r, applied=False))
    return g, r


def apply(b, r=None):
    """shift st/<b>.json by r['shift_sec'] (+ 1-ms refinement); keeps the bar count aligned in time"""
    f = f'st/{b}.json'; g = json.load(open(f)); y = _load(b)
    r = r or analyse(y, g)
    if not r['half_off']:
        return None
    if not os.path.exists(f + '.prehalf'):
        json.dump(g, open(f + '.prehalf', 'w'))
    g2, old, new = shift_grid(g, y, SR, r)
    bar = g.get('bar') or {}
    nbar = {}
    for k, v in bar.items():   # time re-sampling: new bar j takes the old feature at its own start time
        v = np.array(v, float)
        if len(v) == len(old):
            nbar[k] = np.round(np.interp(new, old, v), 2).tolist()
    g2['bar'] = nbar
    json.dump(g2, open(f, 'w'))
    for ext in _CACHES:
        p = f'st/{b}.{ext}'
        if os.path.exists(p):
            os.remove(p)
    # 'all', 'low', 'hat' straight from the audio on the new grid (voc/drums/bass keep the time re-sampled values)
    import subprocess
    subprocess.run([sys.executable, 'barfeats.py'], env=dict(os.environ, BF=f), check=True, capture_output=True)
    return dict(b=b, old_d0=float(old[0]), new_d0=float(new[0]), n_old=len(old), n_new=len(new))


def ids():
    return sorted(os.path.basename(p)[:-5] for p in glob.glob('st/*.json')
                  if p.count('.') == 1 and os.path.exists(p[:-5] + '.wav'))


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for b in args or ids():
        r = check(b)
        line = dict(id=b, **r)
        if '--apply' in sys.argv and r['half_off']:
            line['applied'] = apply(b, r)
        print(json.dumps(line), flush=True)
