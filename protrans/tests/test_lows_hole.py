"""90 Hz width-aware V-dip sensor: flags a returning hole, not a one-way breakdown drop."""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'replica'))
import lows_hole as LH


def test_lows_hole_flags_returning_gap_not_breakdown():
    # 24 bars, blend 4..20. A 6-bar hole at 8..14 that returns, depth 30 dB (> p95 25.21).
    lo = np.full(24, -10.0)
    lo[8:14] = -40.0
    flagged, val = LH.flag(lo, 4, 20)
    assert flagged is True
    assert val >= 29.0
    # A planned breakdown that never returns (drops at bar 10 and stays down) is not a V.
    br = np.full(24, -10.0)
    br[10:] = -50.0
    flagged_b, val_b = LH.flag(br, 4, 20)
    assert flagged_b is False
    assert val_b < LH.PRO_P95


def test_lows_hole_pro_threshold_is_the_p95():
    # A dip just under the pro p95 must not flag (keeps clean-pro flags at the pro rate).
    lo = np.full(24, -10.0)
    lo[8:14] = -10.0 - (LH.PRO_P95 - 1.0)
    flagged, val = LH.flag(lo, 4, 20)
    assert flagged is False
    assert abs(val - (LH.PRO_P95 - 1.0)) < 0.2
    lo2 = np.full(24, -10.0)
    lo2[8:14] = -10.0 - (LH.PRO_P95 + 1.0)
    flagged2, val2 = LH.flag(lo2, 4, 20)
    assert flagged2 is True
