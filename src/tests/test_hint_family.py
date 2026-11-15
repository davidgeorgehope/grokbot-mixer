"""hint_family (2026-11-14 RCA): off-by-default family that can nominate a natural
window whose outgoing end is near the tracklist time hint, so STRUCT's 300-point
outro bonus cannot hide every mid-track candidate from recreate's shortlist.

the listener 2026-11-15: blend technique depends on the tracks, not a fixed rule. When
source lows are given, a mid-track window is only added if the default natural
window has an engine bass hole and the hint window has fewer hole bars.
"""
import os, sys
import numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'protrans'))
import recreate as R
import json


def _cs():
    # outro-over-intro wins engine cost (STRUCT bonus), as on Prime Expansion -> Demons
    return [
        dict(win=['n', 176, None, 32, 16], cost=-187.7),
        dict(win=['n', 176, None, 16, 32], cost=-175.1),
        dict(win=['n', 112, None, 48, 16], cost=126.8),
        dict(win=['n', 112, None, 48, 32], cost=60.8),
        dict(win=['n', 96, None, 48, 16], cost=133.2),
        dict(win=['n', 144, None, 48, 16], cost=46.5),
        dict(win=['la', 176, 160, 48, 16], cost=141.2),
    ]


def _fams():
    return [dict(fam='nat_short', win=['n', 176, None, 32, 16], env={}),
            dict(fam='nat_long', win=['n', 176, None, 16, 32], env={})]


def _lows_this_pair():
    """Prime Expansion still full at 160-176; Demons intro 32-48 thin, drop1 48-64 full."""
    lo_a = np.full(200, -17.5)
    lo_b = np.full(80, -19.0)
    lo_b[:48] = -33.0
    return lo_a, lo_b


def test_hint_families_picks_lowest_cost_inside_near_bars():
    hb = 94.975
    got = {c['fam']: c['win'] for c in R.hint_families(_cs(), hb, near_bars=32)}
    assert got['hint_short'] == ['n', 112, None, 48, 16]   # closer e=96 costs more
    assert got['hint_long'] == ['n', 112, None, 48, 32]
    assert got['hint_short'][1] != 144  # e=144 is outside 32 bars of the hint


def test_hint_families_falls_back_to_closest_end():
    cs = [dict(win=['n', 224, None, 32, 16], cost=10),
          dict(win=['n', 208, None, 16, 16], cost=5),
          dict(win=['n', 240, None, 0, 32], cost=1)]
    got = {c['fam']: c['win'] for c in R.hint_families(cs, hint_bar=100, near_bars=32)}
    assert got['hint_short'] == ['n', 208, None, 16, 16]
    assert got['hint_long'] == ['n', 240, None, 0, 32]


def test_add_hint_families_off_by_default_and_skips_duplicates():
    cs, fams = _cs(), _fams()
    assert R.add_hint_families(fams, cs, 94.975, 32, enabled=False) == fams
    # without lows, enabled still nominates (used by unit tests of the shortlist)
    on = R.add_hint_families(fams, cs, 94.975, 32, enabled=True)
    names = [c['fam'] for c in on]
    assert names[:2] == ['nat_short', 'nat_long']
    assert 'hint_short' in names and 'hint_long' in names
    fams2 = fams + [dict(fam='nat_short', win=['n', 112, None, 48, 16], env={})]
    on2 = R.add_hint_families(fams2, cs, 94.975, 32, enabled=True)
    wins = [tuple(c['win']) for c in on2]
    assert wins.count(('n', 112, None, 48, 16)) == 1


def test_hole_bars_counts_engine_hole_not_shared_breakdown():
    lo_a, lo_b = _lows_this_pair()
    # default window: PE 160-176 full, Demons 32-48 thin -> many hole bars
    assert R.incoming_hole_bars(['n', 176, None, 32, 16], lo_a, lo_b) > 1
    # hint window: Demons 48-64 is the first drop, full bass -> no hole
    assert R.incoming_hole_bars(['n', 112, None, 48, 16], lo_a, lo_b) <= 1
    # both already thin (musical breakdown): not an engine hole
    lo_a2 = np.full(200, -17.5); lo_a2[160:176] = -40.0
    assert R.incoming_hole_bars(['n', 176, None, 32, 16], lo_a2, lo_b) <= 1


def test_feature_gate_only_adds_hint_when_default_has_a_hole():
    cs, fams = _cs(), _fams()
    lo_a, lo_b = _lows_this_pair()
    on = R.add_hint_families(fams, cs, 94.975, 32, enabled=True, lo_a=lo_a, lo_b=lo_b)
    assert 'hint_short' in [c['fam'] for c in on]
    # default already clean: do not drag in a mid-track window (ukf__08 case)
    lo_a_clean = np.full(200, -17.5); lo_a_clean[160:176] = -40.0
    off = R.add_hint_families(fams, cs, 94.975, 32, enabled=True, lo_a=lo_a_clean, lo_b=lo_b)
    assert [c['fam'] for c in off] == ['nat_short', 'nat_long']
    # hint window does not reduce the hole: do not add it
    lo_b_all_thin = np.full(80, -33.0)
    no = R.add_hint_families(fams, cs, 94.975, 32, enabled=True, lo_a=lo_a, lo_b=lo_b_all_thin)
    assert 'hint_short' not in [c['fam'] for c in no]


def test_hint_family_costs_match_nat_and_default_rules_leave_it_off():
    assert R.family_cost('hint_short') == R.family_cost('nat_short')
    assert R.family_cost('hint_long') == R.family_cost('nat_long')
    rules = json.load(open(os.path.join(ROOT, 'protrans', 'rules.json')))
    assert not R._flag_on(rules.get('hint_family'))
    assert 'hint_family' not in rules
    assert R._flag_on(1) and R._flag_on('true') and not R._flag_on(0) and not R._flag_on(None)
