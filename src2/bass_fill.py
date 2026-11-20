"""BASS_FILL (2026-11-20 midnight research, off by default): hand the bass to the incoming's OWN drop bass.

Carry-over "later bass handoff when the incoming has no bass in the window" (docs/GRAPHCUT_2026-11-13.md). Already tried and
lost: BASS_COVER (no swap, lows ride the fader), graph-cut fader-follow bass, DROP_SWAP (re-cue so drop1 lands on the swap),
STRUCT_THIN / THIN_DROPCUE. A later swap inside a 16-bar window is capped by X1 (swap centre at crossfader x <= 0.65) and the
gradual-tail rule to about 1 bar later than the exit-start swap, while the incoming's bass arrives at bar >= 14 or not at all in
26 of the 33 default windows. So instead of moving the swap, give it something to land on: from the swap end until the
incoming's real bass arrives, the incoming's < BASS_XO (150 Hz) band is replaced by the same band of its first steady-bass phrase
(phrase-aligned loop of 8 or 4 bars counted back from the drop, so bar positions in the chord cycle match). This is the bass-only,
stem-free version of the 'ib' fix the listener picked on 2026-11-02 (loop the incoming's own drums+bass under its beatless intro).

Gate (per blend, not a blanket rule): a bass swap exists; every incoming bar from the swap start to the real-bass bar sits
>= BASS_FILL_DB (6, the existing thin line) under the incoming's own body (75th pct of its per-bar lows); the real-bass bar
(first deck bar with 2 bars running at body-6) is within the deck's first X+16 bars and at least 2 bars after the swap end;
the loop phrase starting there is steady (every bar at body-6). The fill starts at the swap end, not a bar before the swap:
the 2026-11-20 cohort's new L1 fails were all mid-handoff (summed lows 3.06 to 5.05 dB over the louder deck) because the loop
put drop bass under the incoming lane while the outgoing lane was still up. The swap shape, crossfader, X1 and every test
threshold are unchanged; the fill sits under the incoming low lane after the handoff has finished.
"""
import numpy as np

def flag_on(v=None):
    import os
    v = os.environ.get('BASS_FILL') if v is None else v
    try: return bool(int(float(v or 0)))
    except (TypeError, ValueError): return False

def plan_one(t, B, lo, db=6.0, secs=None):
    """returns the d['bassfill'] dict for incoming deck B (or None) + a reason string."""
    if not t.get('bass_swap') or not t.get('swap_w'): return None, 'no swap'
    lo = np.asarray(lo, float); fin = lo[np.isfinite(lo)]
    if fin.size < 16: return None, 'no lows'
    body = float(np.percentile(fin, 75)); thr = body - db
    fm = B['full_map']; s = float(B['start_bar']); X = int(round(t['end_bar'] - t['start_bar']))
    src = lambda k: fm[k][0] if 0 <= k < len(fm) and fm[k][1] == 'mix' else None
    v = lambda sb: float(lo[sb]) if sb is not None and 0 <= sb < len(lo) and np.isfinite(lo[sb]) else -120.0
    k_sw = int(np.floor(float(t['bass_swap'][0]) - s))  # deck bar where the low lanes start moving
    k_sw1 = int(np.ceil(float(t['bass_swap'][1]) - s))  # first bar at or after the handoff ends
    k1 = None
    for k in range(max(0, k_sw), min(len(fm) - 1, X + 16)):
        if v(src(k)) >= thr and v(src(k + 1)) >= thr: k1 = k; break
    if k1 is None: return None, 'no real bass within X+16'
    if k1 - k_sw1 < 2: return None, f'bass arrives at deck bar {k1}, swap ends {k_sw1}'
    k0 = max(0, k_sw1)
    if any(src(k) is None for k in range(k0, k1)): return None, 'loop/beat bars in fill region'
    if any(v(src(k)) >= thr for k in range(max(0, k_sw), k1)): return None, 'not thin through the handoff'
    p = src(k1)
    for d0 in sorted((secs or {}).get('drops') or [], key=lambda x: x[0]):  # real bass starts on a pre-drop riser: loop from the drop itself
        if 0 <= d0[0] - p <= 2: p = int(d0[0]); break
    L = next((L for L in (8, 4) if all(v(p + j) >= thr for j in range(L))), None)
    if not L: return None, 'drop phrase not steady'
    m2 = {k: int(p + ((src(k) - p) % L)) for k in range(k0, k1)}
    return dict(k0=k0, k1=k1, p=int(p), L=int(L), xf=0.25, map={str(k): sb for k, sb in m2.items()},
                body=round(body, 2), thin_med=round(float(np.median([v(src(k)) for k in range(k0, k1)])) - body, 2)), 'ok'

def apply(decks, trans, lows_of, db=6.0, skip=(), secs_of=None):
    log = []
    for i, t in enumerate(trans):
        B = decks[i + 1]
        if t['a'] in skip: continue
        try:
            bf, why = plan_one(t, B, lows_of(B['id']), db, secs_of(B['id']) if secs_of else None)
        except Exception as ex:
            bf, why = None, f'error {ex}'
        if bf:
            B['bassfill'] = bf; t['bass_fill'] = {k: bf[k] for k in ('k0', 'k1', 'p', 'L', 'thin_med')}
            t['notes'] = list(t.get('notes') or []) + [f"bass fill: incoming {B['id']} <150 Hz from its drop phrase {bf['p']}-{bf['p']+bf['L']} looped under deck bars {bf['k0']}-{bf['k1']} (its intro lows sat {bf['thin_med']} dB under body)"]
        log.append(dict(a=t['a'], b=t['b'], fill=bool(bf), why=why))
    return log

def render(y, tr, d, bars_fn, BS, SR, XO):
    """y = deck audio before the low lane. Replace its < XO band with the loop's < XO band on deck bars k0..k1."""
    from scipy.signal import butter, sosfiltfilt
    bf = d['bassfill']; k0, k1 = int(bf['k0']), int(bf['k1']); n = len(y)
    m = [s for s, _ in d['full_map']]; m2 = [int(bf['map'].get(str(k), s)) for k, s in enumerate(m)]
    yl = bars_fn(tr, m2, tr['st']['mix'], n)
    a0, a1 = max(0, int((k0 - 1) * BS)), min(n, int((k1 + 1) * BS))
    sos = butter(4, XO, 'low', fs=SR, output='sos')
    ly = sosfiltfilt(sos, y[a0:a1], axis=0).astype(np.float32); ll = sosfiltfilt(sos, yl[a0:a1], axis=0).astype(np.float32)
    xf = float(bf.get('xf', 0.25)); t = (np.arange(a0, a1) / BS)
    w = (np.clip((t - k0) / xf, 0, 1) * np.clip((k1 - t) / xf, 0, 1)).astype(np.float32)  # out over xf bars ending as the real bass lands
    y = y.copy(); y[a0:a1] = y[a0:a1] + w[:, None] * (ll - ly)
    return y
