"""Hard checks (pass/fail, never averaged) and decision metrics for one rendered blend (2026-11-18 night).
Hard checks:
  beat_clash : halfbeat.py fail, or finephase.measure_blend_lag still finds a CONFIDENT 15-150 ms deck lag on the final decks
               (the BLEND_LOCK definition, reused unchanged).
  bass_hole  : summed rendered lows dip in the blend vs the 2 bars before (blend_diag's number) > pro p95 of the same dip.
  pumping    : largest V-shaped full-band dip of the summed decks within the blend (bar k below both +-2-bar sides) > pro p95.
Pro p95s come from calib_pro() on the 33 protrans pro clips (same bar measures on the pro mix)."""
import json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2):
    if p not in sys.path: sys.path.insert(0, p)
CAL = os.path.join(H, 'hardcheck_calib.json')

def vdip(L):
    L = np.asarray(L, float); best = 0.0
    for k in range(2, len(L) - 2):
        best = max(best, min(L[k-2:k].max(), L[k+1:k+3].max()) - L[k])
    return float(best)

def lows_dip(lo, s, e):
    lo = np.asarray(lo, float); pre = lo[max(0, s-2):s] if s > 0 else lo[:2]
    return float(pre.max() - lo[s:e].min()) if e > s and len(pre) else 0.0

def calib_pro():
    """pro p95 of lows_dip and vdip over each pro's overlap [entry, gone), measured on pro.wav."""
    import blend_diag as BD, run_admitted_tune as T, score
    from engine import BS
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); dips, pumps, rows = [], [], {}
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        s, e = d.get('in_entry_clip_bar'), d.get('out_gone_clip_bar')
        if s is None or e is None or e - s < 4: continue
        y = score._load(rec['pro_clip']); y2 = np.stack([y, y], 1) if y.ndim == 1 else y
        n = int(len(y2) // BS); lo = BD.band_bar_db(y2, n, BS, 'low', 150); al = BD.band_bar_db(y2, n, BS)
        e = min(e, n); dp = lows_dip(lo, s, e); pu = vdip(al[s:e]); dips.append(dp); pumps.append(pu); rows[rec['id']] = (round(dp, 1), round(pu, 1))
    out = dict(n=len(dips), lows_dip_p95=round(float(np.percentile(dips, 95)), 2), pump_p95=round(float(np.percentile(pumps, 95)), 2), rows=rows)
    json.dump(out, open(CAL, 'w'), indent=1); return out

def check(meta_path, png=None, title=None):
    import blend_diag as BD, finephase as FP
    from engine import BS
    cal = json.load(open(CAL)); M = json.load(open(meta_path)); t = M['trans'][0]
    if png:
        summ = BD.figure(M, 0, png, title)
    else:
        summ = None
    s0, A, B = BD.crop_decks(M, 0); n = int(round(len(A) / BS)); s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
    loA, loB = BD.band_bar_db(A, n, BS, 'low', 150), BD.band_bar_db(B, n, BS, 'low', 150)
    sumlo = 10*np.log10(10**(loA/10) + 10**(loB/10)); S = A + B; al = BD.band_bar_db(S, n, BS)
    dip = lows_dip(sumlo, s, e); pump = vdip(al[s:e])
    lag, rep = FP.measure_blend_lag(M['decks'], M['trans'], 0)
    hb = t.get('halfbeat') or {}
    clash = bool(hb.get('fail')) or (lag is not None)
    res = dict(beat_clash=clash, residual_lag_ms=lag, halfbeat_fail=bool(hb.get('fail')),
               bass_hole=dip > cal['lows_dip_p95'], lows_dip_db=round(dip, 1),
               pumping=pump > cal['pump_p95'], pump_db=round(pump, 1), png=png)
    res['hard_fail'] = bool(res['beat_clash'] or res['bass_hole'] or res['pumping'])
    return res

def _gain_db(d, x):
    g = d['auto'].get('gain') or []
    v = np.interp(x, [p[0] for p in g], [p[1] for p in g]) if g else np.ones(len(x))
    on = (x >= d['start_bar']) & (x < d['start_bar'] + len(d['full_map']))
    return 20*np.log10(np.maximum(v * on, 1e-3))

def ours_decisions(meta_path, win):
    """our decisions in the pro's terms: exit/cue track bars at the blend start, audible overlap, swap bars after entry,
    per-bar fader curves (dB) from the entry, same -12 dB 'on' rule as extract_protrans."""
    M = json.load(open(meta_path)); t = M['trans'][0]; s, e = float(t['start_bar']), float(t['end_bar'])
    x = np.arange(int(s) - 8, int(e) + 16) + 0.5
    ga, gb = _gain_db(M['decks'][0], x), _gain_db(M['decks'][1], x)
    onb = gb > -12; ona = ga > -12
    b_in = next((k for k in range(len(x)-1) if onb[k] and onb[k+1]), None)
    act = np.flatnonzero(ona); a_gone = int(act[-1]) + 1 if len(act) else None
    X = int(win[4]); E = win[1][0] if isinstance(win[1], (list, tuple)) else win[1]
    out_bar, in_bar = E - X, win[3]
    if b_in is not None:  # shift to our audible entry, like the pro's (straight 'n' windows; loops approximate)
        d = x[b_in] - 0.5 - s; out_bar += d; in_bar += d
    sw = t.get('swap_bar')
    return dict(out_bar=float(out_bar), in_bar=float(in_bar), overlap=None if b_in is None or a_gone is None else int(a_gone - b_in),
                swap_after_entry=None if sw is None or b_in is None else float(sw) - (x[b_in] - 0.5),
                curve_a=ga[b_in:].round(1).tolist() if b_in is not None else None, curve_b=gb[b_in:].round(1).tolist() if b_in is not None else None)

def fade_err(ours, pa, pb, L=24):
    """mean |dB| between our fader curves and the pro's per-deck curves from the entry, both clipped to [-30, 0], first L bars."""
    if not ours.get('curve_a') or pa is None: return None
    c = lambda v: np.clip(np.asarray(v[:L], float), -30, 0)
    oa, ob, qa, qb = c(ours['curve_a']), c(ours['curve_b']), c(pa), c(pb); n = min(len(oa), len(qa), len(ob), len(qb))
    return None if n < 4 else round(float(np.mean(np.abs(oa[:n]-qa[:n]) + np.abs(ob[:n]-qb[:n])) / 2), 2)

if __name__ == '__main__':
    print(json.dumps({k: v for k, v in calib_pro().items() if k != 'rows'}))
