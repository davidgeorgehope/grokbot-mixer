"""LEADIN_LOCK (2026-11-23 RCA, research, off by default).

When BLEND_LOCK cannot form a tight per-bar cluster (typical of a half-time
breakdown against a regular-time intro), estimate one incoming lag from the
kick-on-1 / snare-on-2-and-4 phrase template (halfbeat.deck_phase) on the
incoming lead-in phrase vs the overlapping outgoing bars. The incoming lead-in
is the anchor: only the incoming deck is moved (same sign as blend_lock_ms).
The outgoing record is not warped.

Lead-in = cue to the first mid-intro half-time (after bar 16, before drop 1),
else to drop 1. Measurement prefers the first confident 8-bar phrase of that
run. Reuses existing FINE_PHASE / BLEND_LOCK thresholds (MIN_BARS, MIN_STRENGTH,
LOCK_MIN_MS, LOCK_MAX_MS). Does not loosen them, write rules.json, or change
defaults.
"""
from __future__ import annotations
import json, os, sys

def flag_on(val=None):
    v = os.environ.get('LEADIN_LOCK', '0') if val is None else val
    if v is None:
        return False
    s = str(v).strip().lower()
    return s not in ('', '0', 'false', 'off', 'no')


def arrival_event(tid):
    ev = None
    try:
        import sections
        SB = sections.get(tid) or {}
        ev = SB.get('drop1')
        sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
        import slowdown as _SD
        P = _SD.profile(tid)
        d1 = SB.get('drop1')
        for x, y in (P or {}).get('sections') or []:
            if d1 is not None and 16 < x < d1:
                ev = x
                break
    except Exception as ex:
        print('LEADIN_LOCK event failed', tid, ex, file=sys.stderr)
    return ev


def lag_ms(decks, trans, i):
    import halfbeat as HB
    import finephase as FP
    t = trans[i]
    a_id, b_id = decks[i]['id'], decks[i + 1]['id']
    s = float(t['start_bar'])
    e = float((t.get('tail_exit') or {}).get('exit_bar') or t['end_bar'])
    b_map = decks[i + 1].get('full_map') or decks[i + 1].get('map') or []
    cue = int(b_map[0][0]) if b_map else 0
    ev = arrival_event(b_id)
    if ev is None:
        ev = cue + 16
    lead = max(int(ev) - int(cue), FP.MIN_BARS)
    both = max(0, int(min(e, s + lead) - s))
    if both < FP.MIN_BARS:
        return None, dict(why='lead-in shorter than MIN_BARS', cue=cue, ev=ev, both=both)
    b_bars = list(range(int(cue), int(cue) + both))
    a_bars = list(range(int(s), int(s) + both))
    gA = json.load(open(f'st/{a_id}.json'))
    gB = json.load(open(f'st/{b_id}.json'))

    def phrase_phase(tid, g, bars):
        candidates = []
        if len(bars) >= FP.PHRASE:
            candidates.append(bars[:FP.PHRASE])
        candidates.append(bars)
        best = None
        for sl in candidates:
            try:
                ph, strength, used = HB.deck_phase(tid, sl, g)
            except Exception:
                continue
            rec = dict(bars=[int(sl[0]), int(sl[-1])], phase=float(ph),
                       strength=float(strength), n=int(used))
            if used >= FP.MIN_BARS and strength >= FP.MIN_STRENGTH:
                return rec
            if best is None or strength > best['strength']:
                best = rec
        return best

    recA, recB = phrase_phase(a_id, gA, a_bars), phrase_phase(b_id, gB, b_bars)
    rep = dict(cue=int(cue), ev=int(ev) if ev is not None else None, both=both, A=recA, B=recB)
    if not recA or not recB:
        rep['why'] = 'deck_phase failed'
        return None, rep
    if (recA['n'] < FP.MIN_BARS or recB['n'] < FP.MIN_BARS
            or recA['strength'] < FP.MIN_STRENGTH or recB['strength'] < FP.MIN_STRENGTH):
        rep['why'] = 'weak or short phrase (MIN_STRENGTH / MIN_BARS)'
        return None, rep
    lag = (recA['phase'] - recB['phase']) * FP.BEAT_MS
    rep['lag_ms'] = round(float(lag), 1)
    return float(lag), rep


def apply_to_meta(M):
    """Set incoming blend_lock_ms from the lead-in phrase lag when the loud-bar lock did not apply."""
    if not flag_on():
        return M
    trans, decks = M.get('trans') or [], M.get('decks') or []
    for i, t in enumerate(trans):
        if i + 1 >= len(decks):
            continue
        existing = t.get('blend_lock') or {}
        if existing.get('applied'):
            existing['leadin'] = dict(skipped=True, why='BLEND_LOCK already applied')
            continue
        lag, rep = lag_ms(decks, trans, i)
        existing = dict(existing)
        existing['leadin'] = rep
        import finephase as FP
        if lag is None:
            existing['leadin']['applied'] = False
        elif abs(lag) < FP.LOCK_MIN_MS or abs(lag) > FP.LOCK_MAX_MS:
            existing['leadin']['applied'] = False
            existing['leadin']['why'] = ('already locked' if abs(lag) < FP.LOCK_MIN_MS
                                        else 'near half a beat; left to halfbeat')
        else:
            inc = decks[i + 1]
            inc['blend_lock_ms'] = round(float(inc.get('blend_lock_ms') or 0) + lag, 1)
            existing['applied'] = True
            existing['why'] = 'lead-in phrase phase (incoming lead-in as anchor)'
            existing['blend_lock_ms'] = inc['blend_lock_ms']
            existing['leadin']['applied'] = True
            print('LEADIN_LOCK', decks[i]['id'], '->', inc['id'],
                  'lag', round(lag, 1), 'lock', inc['blend_lock_ms'],
                  'A', rep.get('A'), 'B', rep.get('B'), file=sys.stderr, flush=True)
        t['blend_lock'] = existing
    return M
