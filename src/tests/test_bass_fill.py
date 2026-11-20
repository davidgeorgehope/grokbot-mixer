"""BASS_FILL (2026-11-20 research, off by default): gate + loop mapping of src2/bass_fill.plan_one."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../src2'))
import bass_fill as BF

def _lows(n=120, drop=48, thin=-30.0, body=-18.0):
    lo = np.full(n, body); lo[:drop] = thin; return lo

def _deck(ib, n=40, start=100):
    return dict(start_bar=start, full_map=[[ib + k, 'mix'] for k in range(n)])

def _t(start=100, X=16, sw=(104, 109)):
    return dict(start_bar=start, end_bar=start + X, bass_swap=list(sw), swap_w=4.0)

def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv('BASS_FILL', raising=False)
    assert BF.flag_on() is False

def test_fills_thin_intro_up_to_drop():
    bf, why = BF.plan_one(_t(), _deck(32), _lows())
    # swap ends at mix bar 109, deck start 100 -> k0 = 9; drop at source 48 is deck bar 16
    assert why == 'ok' and bf['k0'] == 9 and bf['k1'] == 16 and bf['p'] == 48 and bf['L'] == 8
    # phrase-aligned: deck bar 9 is source 41 -> 48 + (41-48) % 8 = 49; fill does not cover mid-swap (deck bars 4-8)
    assert bf['map']['9'] == 49 and '4' not in bf['map'] and '8' not in bf['map'] and '16' not in bf['map']

def test_fill_starts_at_swap_end_not_before():
    bf, why = BF.plan_one(_t(), _deck(32), _lows())
    assert why == 'ok' and bf['k0'] == 9
    assert all(int(k) >= 9 for k in bf['map'])

def test_no_fill_when_bass_arrives_at_swap_end():
    # real bass at source 42 = deck bar 10, swap ends at deck bar 9; only 1 bar of post-swap thin
    bf, why = BF.plan_one(_t(), _deck(32), _lows(drop=42))
    assert bf is None

def test_no_fill_when_incoming_has_bass():
    bf, why = BF.plan_one(_t(), _deck(32), _lows(drop=0))
    assert bf is None

def test_no_fill_without_swap():
    t = _t(); t['swap_w'] = 0
    assert BF.plan_one(t, _deck(32), _lows())[0] is None

def test_no_fill_when_bass_arrives_right_at_swap():
    bf, why = BF.plan_one(_t(), _deck(32), _lows(drop=36))
    assert bf is None

def test_no_fill_when_drop_phrase_not_steady():
    lo = _lows(); lo[49:52] = -40
    assert BF.plan_one(_t(), _deck(32), lo)[0] is None

def test_pre_drop_riser_loops_from_drop():
    lo = _lows(); lo[46:48] = -18.0
    bf, why = BF.plan_one(_t(), _deck(32), lo, secs=dict(drops=[[48, 96]]))
    assert bf['k1'] == 14 and bf['p'] == 48
