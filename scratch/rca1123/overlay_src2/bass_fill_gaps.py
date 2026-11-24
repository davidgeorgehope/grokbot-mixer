"""BASS_FILL_GAPS (2026-11-23 RCA, research, off by default).

Same idea and thresholds as BASS_FILL (incoming drop-bass loop under a thin
intro after the swap ends; body = 75th percentile of the track's lows; thin =
body - BASS_FILL_DB, default 6). The live module aborts the whole fill when
any single bar between the swap start and the first 2-bar body run sits at or
over the thin line, even when that bar is an isolated blip and the surrounding
bars are thin.

This variant keeps the 6 dB line and the 2-bar definition of real bass, but
fills only the thin bars in [swap_end, real_bass). Isolated nearly-body bars
keep their native lows (no threshold loosening, no swap/fader/window change).
Live bass_fill.py is not imported or modified; attach the same `bassfill`
dict shape so engine.render_deck's existing hook can render it.
"""
from __future__ import annotations
import os, sys
import numpy as np


def flag_on(val=None):
    v = os.environ.get('BASS_FILL_GAPS', '0') if val is None else val
    if v is None:
        return False
    return str(v).strip().lower() not in ('', '0', 'false', 'off', 'no')


def plan_one(t, B, lo, db=6.0, secs=None):
    if not t.get('bass_swap') or not t.get('swap_w'):
        return None, 'no swap'
    lo = np.asarray(lo, float)
    fin = lo[np.isfinite(lo)]
    if fin.size < 16:
        return None, 'no lows'
    body = float(np.percentile(fin, 75))
    thr = body - db
    fm = B['full_map']
    s = float(B['start_bar'])
    X = int(round(t['end_bar'] - t['start_bar']))
    src = lambda k: fm[k][0] if 0 <= k < len(fm) and fm[k][1] == 'mix' else None
    v = lambda sb: float(lo[sb]) if sb is not None and 0 <= sb < len(lo) and np.isfinite(lo[sb]) else -120.0
    k_sw = int(np.floor(float(t['bass_swap'][0]) - s))
    k_sw1 = int(np.ceil(float(t['bass_swap'][1]) - s))
    k1 = None
    for k in range(max(0, k_sw), min(len(fm) - 1, X + 16)):
        if v(src(k)) >= thr and v(src(k + 1)) >= thr:
            k1 = k
            break
    if k1 is None:
        return None, 'no real bass within X+16'
    if k1 - k_sw1 < 2:
        return None, f'bass arrives at deck bar {k1}, swap ends {k_sw1}'
    k0 = max(0, k_sw1)
    if any(src(k) is None for k in range(k0, k1)):
        return None, 'loop/beat bars in fill region'
    thin_ks = [k for k in range(k0, k1) if v(src(k)) < thr]
    skip_ks = [k for k in range(k0, k1) if v(src(k)) >= thr]
    if not thin_ks:
        return None, 'no thin bars to fill after swap'
    p = src(k1)
    for d0 in sorted((secs or {}).get('drops') or [], key=lambda x: x[0]):
        if p is not None and 0 <= d0[0] - p <= 2:
            p = int(d0[0])
            break
    if p is None:
        return None, 'no loop phrase start'
    L = next((L for L in (8, 4) if all(v(p + j) >= thr for j in range(L))), None)
    if not L:
        return None, 'drop phrase not steady'
    # map only thin bars; isolated body blips keep the native source bar
    m2 = {k: int(p + ((src(k) - p) % L)) for k in thin_ks}
    return dict(k0=k0, k1=k1, p=int(p), L=int(L), xf=0.25,
                map={str(k): sb for k, sb in m2.items()},
                skip_ks=skip_ks, thin_ks=thin_ks,
                body=round(body, 2),
                thin_med=round(float(np.median([v(src(k)) for k in thin_ks])) - body, 2)), 'ok'


def apply_to_meta(M, db=None):
    if not flag_on():
        return M
    db = float(os.environ.get('BASS_FILL_DB', 6) or 6) if db is None else db
    trans, decks = M.get('trans') or [], M.get('decks') or []
    sys.path.insert(0, '/workspace/mixes/src2')
    import sections
    src2 = '/workspace/mixes/src2'
    for i, t in enumerate(trans):
        if i + 1 >= len(decks):
            continue
        B = decks[i + 1]
        st = f"{src2}/st/{B['id']}.json"
        import json
        g = json.load(open(st))
        lo = np.array(g['bar']['low'], float)
        try:
            bf, why = plan_one(t, B, lo, db, sections.get(B['id']))
        except Exception as ex:
            bf, why = None, f'error {ex}'
        rec = dict(fill=bool(bf), why=why, variant='BASS_FILL_GAPS')
        if bf:
            B['bassfill'] = bf
            t['bass_fill'] = {k: bf[k] for k in ('k0', 'k1', 'p', 'L', 'thin_med') if k in bf}
            t['bass_fill']['skip_ks'] = bf.get('skip_ks')
            t['bass_fill']['variant'] = 'BASS_FILL_GAPS'
            t['notes'] = list(t.get('notes') or []) + [
                f"bass fill gaps: incoming {B['id']} <150 Hz from drop phrase {bf['p']}-{bf['p']+bf['L']} "
                f"looped under thin deck bars {bf['thin_ks']} (intro lows sat {bf['thin_med']} dB under body; "
                f"isolated body bars {bf.get('skip_ks')} left native)"
            ]
            print('BASS_FILL_GAPS', B['id'], 'k0', bf['k0'], 'k1', bf['k1'],
                  'p', bf['p'], 'L', bf['L'], 'skip', bf.get('skip_ks'),
                  file=sys.stderr, flush=True)
        else:
            print('BASS_FILL_GAPS skip', why, file=sys.stderr, flush=True)
        t['bass_fill_gaps'] = rec if not bf else {**rec, **t['bass_fill']}
    return M
