"""BASS_COVER (fade_long.incoming_no_bass + mix_simple hook, 2026-11-14 RCA, off by default).

When the incoming track has no body-level bass in the overlap, skip the mid-window
bass handoff and leave lows on the outgoing (they fade with the fader). Does not
move the crossfader, does not loosen X1 or the 3 dB/bar tail rule, and does not
change rules.json.
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src2'))
import fade_long as FL
import test_crossfader as U


def _lo(n=80, body=-18.0, intro=None, drop=None):
    a = np.full(n, body, float)
    if intro is not None:
        a[:intro[0]] = intro[1]
    if drop is not None:
        a[drop:] = body
    return a


def test_detector_flags_all_thin_intro():
    # Demons-like: bars 32-47 sit ~14 dB under the drop/body, drop at 48.
    lo = np.concatenate([np.full(32, -18.0), np.full(16, -32.0), np.full(32, -18.0)])
    wb = list(range(32, 48))
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0) is True
    assert FL.incoming_no_bass(lo, wb, 16, db=12.0) is True


def test_detector_passes_when_incoming_has_body_bass():
    lo = np.full(64, -18.0)
    wb = list(range(32, 48))
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0) is False


def test_detector_uses_existing_six_db_thin_line():
    body = -18.0
    lo = np.full(64, body)
    lo[32:48] = body - 5.9  # just under 6 dB: not thin
    wb = list(range(32, 48))
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0) is False
    lo[32:48] = body - 6.1
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0) is True


def test_slack_allows_drop_on_last_bar():
    lo = np.full(64, -18.0)
    lo[32:47] = -32.0  # last overlap bar is the drop
    wb = list(range(32, 48))
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0, slack=0) is False
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0, slack=1) is True


def test_real_demons_window_is_coverable():
    path = os.path.join(ROOT, 'src2', 'st', '5YG-HKjtiHM.json')
    if not os.path.exists(path):
        return
    lo = np.array(json.load(open(path))['bar']['low'], float)
    wb = list(range(32, 48))
    assert FL.incoming_no_bass(lo, wb, 16, db=6.0) is True
    # first-half vs second-half thin (cap_solo) is a different question
    first = FL.first_incoming_thin_bar(lo, lo, wb, 16)
    assert first >= 0  # second half is a bit thinner, but the whole window is under the body


def test_no_low_lanes_passes_x1():
    """Skipping the swap means no low-lane move; X1's 0.2-0.65 centre check does not run."""
    X, s0 = 16, 160
    xs = [[s0 + k / 4, round(FL.xlong((k / 4) / X, X), 5)] for k in range(4 * X + 1)]
    t = dict(a='A', b='B', start_bar=s0, end_bar=s0 + X, xfader=xs, bass_swap=None, swap_w=0, high_bar=None)
    M = dict(trans=[t], decks=[
        dict(id='A', start_bar=0, end_bar=s0 + X, auto={'gain': [[p[0], float(np.cos(p[1] * np.pi / 2))] for p in xs], 'low': []}),
        dict(id='B', start_bar=s0, end_bar=s0 + X + 40, auto={'gain': [[p[0], float(np.sin(p[1] * np.pi / 2))] for p in xs], 'low': []}),
    ], bar_sec=240 / 174)
    assert U.run(M) == [], U.run(M)


def test_flag_off_by_default_and_not_in_rules():
    src = open(os.path.join(ROOT, 'src2', 'mix_simple.py')).read()
    assert "os.environ.get('BASS_COVER',0)" in src or "os.environ.get('BASS_COVER', 0)" in src
    rec = open(os.path.join(ROOT, 'protrans', 'recreate.py')).read()
    assert "'BASS_COVER'" in rec and "'BASS_COVER_DB'" in rec
    rules = json.load(open(os.path.join(ROOT, 'protrans', 'rules.json')))
    assert 'BASS_COVER' not in rules and 'BASS_COVER_DB' not in rules

def test_lane_builder_respects_swap_w():
    """After _ctx(None) the global SW resets; lanes must follow each blend's swap_w, not SW."""
    src = open(os.path.join(ROOT, 'src2', 'mix_simple.py')).read()
    assert "if i>0 and trans[i-1]['swap_w']>0:" in src
    assert "if i<len(decks)-1 and trans[i]['swap_w']>0:" in src
    assert "if lo:d['auto']['low']=lo" in src
