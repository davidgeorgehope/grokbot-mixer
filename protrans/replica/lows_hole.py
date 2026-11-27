"""Width-aware sub-bass hole sensor (hchole90, 2026-11-27).

Official hardcheck.lows_dip uses a 150 Hz band and scores any lows drop in the blend
(including planned breakdowns), so its pro p95 is 45.34 dB and it almost never sees a
real 4/8-bar hole. This sensor is the 90 Hz width-aware V-dip from hchole_1127.py:
for width w in 1..8 bars, (min of the max of the 2 bars before and the 2 after) minus
the max inside the window; take the largest. A hole that comes back is scored; a lows
drop that never returns is not.

Threshold = pro p95 of the same measure on the 33 official pro clips over the pro overlap
[entry, gone). By construction, flags on clean pro transitions sit at the pro rate (~5%,
2 of 33 on the 11-27 calibration). Do not lower the threshold; that would flag more pro
clips than the pro rate.
"""
from __future__ import annotations
import numpy as np

FC_HZ = 90.0
# Pro p95 from nightly_1127_work/hchole_lcb_1127_fc90.json (33 official pro clips, 90 Hz).
PRO_P95 = 25.21
W_MAX = 8


def lows_hole(lo, s, e, W=W_MAX):
    lo = np.asarray(lo, float)
    best = 0.0
    s, e = int(s), int(e)
    for w in range(1, W + 1):
        for k in range(max(2, s), min(e, len(lo) - 2) - w + 1):
            if k + w + 2 > len(lo):
                break
            best = max(best, min(lo[k - 2:k].max(), lo[k + w:k + w + 2].max()) - lo[k:k + w].max())
    return float(best)


def flag(lo, s, e, p95=PRO_P95, W=W_MAX):
    v = lows_hole(lo, s, e, W=W)
    return v > float(p95), v


def measure_sumlo(A, B, n, BS, s, e, fc=FC_HZ, p95=PRO_P95):
    """A, B = cropped deck audio (n bars, hop BS). Returns dict with value and flag."""
    import sys, os
    src2 = os.environ.get('PROTRANS_SRC2') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src2')
    if src2 not in sys.path:
        sys.path.insert(0, src2)
    import blend_diag as BD
    loA = BD.band_bar_db(A, n, BS, 'low', fc)
    loB = BD.band_bar_db(B, n, BS, 'low', fc)
    sumlo = 10 * np.log10(10 ** (loA / 10) + 10 ** (loB / 10) + 1e-12)
    flagged, val = flag(sumlo, s, e, p95=p95)
    return dict(lows_hole=round(float(val), 2), lows_hole_flag=bool(flagged), fc_hz=float(fc), p95=float(p95))
