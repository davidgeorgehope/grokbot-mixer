#!/usr/bin/env python3
"""Read-only: measure the outgoing 'ride after the bass swap' (src/build_qa/test_release_structure_tail.py::
test_outgoing_fader_tail_is_gradual, second half) on the 33 admitted pro transitions.

Our test, per blend window [s,e] of X bars on the crossfader level g (dB, cos law):
  ride = number of whole bars >= bass swap with g > -20 dB;  fail if ride < 0.35*X - 1.
Pros have no crossfader to read, so g is the outgoing deck's full-band NNLS gain (diagnose_gap.band_gains,
the same deck-gain fit guard_vs_pro.py uses for events), per bar, relative to its own p90 (its pre-blend level).
The bass swap is the bass-band event (score.events_from_pair), as in guard_vs_pro.py. The window is
incoming on (first sustained bar > -24 dB rel) to outgoing gone (last bar > -24 dB rel, +1), the same -24 dB
'audible' line our test uses for the per-bar slope. Muted decks still fit at about -7..-12 dB in NNLS, so pro
ride is an upper bound; this only matters if pros pass.

Usage (from /workspace/mixes): python3 src/calib/ride_vs_pro.py [--workers 3]
Writes src/calib/ride_vs_pro_results.json. Changes no threshold.
"""
import json, os, sys, datetime
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard_vs_pro as G
PS, DG, VM = G.PS, G.DG, G.VM
OUT = Path(__file__).resolve().parent / 'ride_vs_pro_results.json'
RIDE_DB, ON_DB, FRAC = -20.0, -24.0, 0.35

def rel(x):
    ref = np.percentile(x, 90); return x - ref

def sustained(mask, k0=0):
    return next((k for k in range(k0, len(mask) - 1) if mask[k:k + 2].all()), None)

def ride_metric(out_rel, in_rel, swap):
    """bars arrays (dB rel); returns dict like the test. Pure, unit-tested."""
    n = min(len(out_rel), len(in_rel)); o, i = np.asarray(out_rel[:n]), np.asarray(in_rel[:n])
    s = sustained(i > ON_DB)
    act = np.flatnonzero(o > ON_DB)
    if s is None or not len(act) or swap is None: return None
    e = int(act[-1]) + 1
    if e <= s: return None
    X = e - s; sw = max(int(np.ceil(swap)), s)
    ride = int(np.sum(o[sw:e] > RIDE_DB))
    need = FRAC * X - 1
    return dict(start=int(s), end=e, X=int(X), swap=float(swap), ride=ride, need=round(need, 2),
                margin=round(ride - need, 2), fail=bool(ride < need), ride_frac=round(ride / X, 3))

def curves(clip):
    path = clip['pro_clip']; sa, sb = G.src_path(clip['yt_a']), G.src_path(clip['yt_b'])
    mix = PS._load(str(path)); al = []
    for p, c in ((sa, clip.get('loc_a')), (sb, clip.get('loc_b'))):
        if not p or not os.path.exists(p): return None
        if c and c.get('mix_t') is not None and c.get('track_t') is not None: loc = c
        else:
            loc = VM.locate_in(mix, PS._load(p))
            if loc.get('track_t') is None: return None
        y = DG.place_source(p, loc['track_t'], loc['mix_t'], len(mix)); y, _ = DG.refine_lag(mix, y); al.append(y)
    gains, _, times, _ = DG.band_gains(mix, *al)
    t = np.arange(len(PS._rms(mix))) * PS.HOP / PS.SR
    cv = {b: [PS._to_bars(PS._db(np.interp(t, times, gains[b][d]))) for d in ('a', 'b')] for b in ('bass', 'all')}
    return cv

def measure(clip):
    try:
        cv = curves(clip)
        if cv is None: return dict(id=clip['id'], error='no sources')
        # bass swap: score.events_from_pair's rule (-12 dB rel presence, established outgoing dominance), on bars
        o, i = rel(np.asarray(cv['all'][0])), rel(np.asarray(cv['all'][1]))
        bo, bi = rel(np.asarray(cv['bass'][0])), rel(np.asarray(cv['bass'][1]))
        n = min(len(bo), len(bi)); on_o, on_i = bo[:n] > -12, bi[:n] > -12
        est = sustained((bo[:n] > bi[:n]) & on_o)
        swap = None if est is None else sustained((np.arange(n) > est) & (bi[:n] >= bo[:n] - 1.0) & on_i)
        m = ride_metric(o, i, swap)
        return dict(id=clip['id'], dj=clip['dj'], split=clip['split'], pair=clip['pair'], m=m,
                    out_rel=[round(float(x), 1) for x in o], in_rel=[round(float(x), 1) for x in i])
    except Exception as e:
        return dict(id=clip['id'], error=f'{type(e).__name__}: {e}'[-300:])

def main():
    w = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 3
    clips = [c for c in G.load_corpus_index() if c['admitted']]
    from multiprocessing import Pool
    with Pool(w) as P: rows = P.map(measure, clips)
    ok = [r for r in rows if r.get('m')]
    fails = [r for r in ok if r['m']['fail']]
    mg = sorted(r['m']['margin'] for r in ok)
    pct = lambda p: round(float(np.percentile(mg, p)), 2)
    summ = dict(n=len(clips), n_measured=len(ok), n_fail=len(fails), pct_fail=round(100 * len(fails) / max(1, len(ok)), 1),
                margin_bars=dict(p5=pct(5), p10=pct(10), median=pct(50), min=mg[0] if mg else None),
                ride_frac=dict(p5=round(float(np.percentile([r['m']['ride_frac'] for r in ok], 5)), 3),
                               median=round(float(np.median([r['m']['ride_frac'] for r in ok])), 3)),
                X=dict(median=float(np.median([r['m']['X'] for r in ok]))),
                # largest FRAC each pro would pass (ride >= FRAC*X - 1); p5 of it = the FRAC 95% of pros pass
                pass_frac=dict(p5=round(float(np.percentile([(r['m']['ride'] + 1) / r['m']['X'] for r in ok], 5)), 3),
                               p10=round(float(np.percentile([(r['m']['ride'] + 1) / r['m']['X'] for r in ok], 10)), 3),
                               median=round(float(np.median([(r['m']['ride'] + 1) / r['m']['X'] for r in ok])), 3)),
                n_censored=sum(1 for r in ok if r['m']['start'] == 0 or r['m']['end'] >= len(r['out_rel'])),
                n_uncensored_fail=sum(1 for r in fails if r['m']['start'] > 0 and r['m']['end'] < len(r['out_rel'])))
    for r in ok:
        m = r['m']; print(f"{r['split']:5s} {r['id'][:38]:38s} X={m['X']:3d} swap={m['swap']:5.1f} ride={m['ride']:3d} need={m['need']:5.1f} {'FAIL' if m['fail'] else 'ok'}")
    for r in rows:
        if r.get('error') or not r.get('m'): print('unmeasured', r['id'], r.get('error'))
    print('SUMMARY', json.dumps(summ))
    json.dump(dict(generated=datetime.datetime.now().astimezone().isoformat(timespec='seconds'), read_only=True,
                   method=__doc__, summary=summ, rows=rows), open(OUT, 'w'), indent=1)

if __name__ == '__main__': main()
