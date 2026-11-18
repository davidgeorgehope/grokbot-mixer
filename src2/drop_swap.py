"""DROP_SWAP (2026-11-18 midnight research, off by default).

Carry-over #1 from docs/GRAPHCUT_2026-11-13.md: "later bass handoff when the
incoming has no bass in the window". BASS_COVER (keep lows on the outgoing),
graphcut fader-follow bass, and the mid-track window planner were already tried.
What was never tried is re-cueing the *same* outro-over-intro window so the
incoming's first drop lands on the bass swap, i.e. the classic DnB move
("swap the bass ... in a single, decisive move, usually right on the drop").

STRUCT's default outro-over-intro window cues the incoming at drop1 - X, so its
drop lands one bar *after* the blend ends. With FADE=long the bass swap sits at
the exit start (~bar 6-7 of a 16-bar window), so when the incoming intro has no
bass the low end is handed to a bass-less intro and the summed lows fall into a
hole until the drop (Final Hours -> Listen 44.5 dB, Prime Expansion -> Demons
22.5 dB).

Gate (per pair, not a blanket rule): only when every bar of the default STRUCT
window's incoming overlap is >= 6 dB under the incoming's own body (the existing
SWAP_THIN / BASS_COVER thin line; nothing loosened). Then nominate one extra
window with the same outgoing end and the incoming cued at drop1 - d, where d is
the 4-bar phrase boundary at or after the start of the bass handoff (so the
incoming bass is at body when the outgoing bass leaves). The original window
stays in the candidate set; both carry the STRUCT bonus and the engine's own
cost chooses. X1, GAP_DB, F1/N1 and the swap position rule are untouched.
"""
from __future__ import annotations

import math

import numpy as np


def flag_on(v=None) -> bool:
    if v is None:
        import os
        v = os.environ.get('DROP_SWAP')
    try:
        return bool(int(float(v or 0)))
    except (TypeError, ValueError):
        return str(v).strip().lower() in ('true', 'yes', 'on')


def body(lo) -> float:
    lo = np.asarray(lo, float)
    return float(np.percentile(lo, 75)) if len(lo) else -120.0


def all_thin(lo_b, ib, X, db=6.0) -> bool:
    """Every incoming overlap bar ib..ib+X-1 is >= db under the incoming body."""
    lo_b = np.asarray(lo_b, float)
    if ib < 0 or ib + X > len(lo_b):
        return False
    return bool(np.all(lo_b[ib:ib + X] < body(lo_b) - db))


def drop_bar(swap_centre, swap_w, X, q=4):
    """Window bar where the incoming drop should land: the q-bar phrase boundary at or after the
    handoff start (centre - width/2), kept at least q bars from either window edge."""
    start = float(swap_centre) - float(swap_w) / 2.0
    d = int(q * math.ceil(max(start, 0.0) / q - 1e-9))
    return int(min(max(d, q), X - q))


def recue(lo_b, drop1, X, ib_default, swap_centre, swap_w, nb, db=6.0, q=4):
    """Return the re-cued incoming start bar, or None when the gate does not hold.

    None when: the default overlap is not all thin; the new cue would start before bar 0 or run past
    the track; it equals the default cue; or the incoming is not actually at body (within db) for at
    least half of the bars after the drop inside the window (drop1 mis-detected)."""
    if drop1 is None or ib_default is None:
        return None
    if not all_thin(lo_b, int(ib_default), int(X), db):
        return None
    d = drop_bar(swap_centre, swap_w, X, q)
    ib = int(drop1) - d
    if ib < 0 or ib + X >= int(nb) or ib == int(ib_default):
        return None
    lo_b = np.asarray(lo_b, float)
    post = lo_b[int(drop1):ib + X]
    if len(post) == 0 or np.mean(post >= body(lo_b) - db) < 0.5:
        return None
    return ib
