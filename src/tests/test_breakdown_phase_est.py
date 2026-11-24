"""BREAKDOWN_PHASE_EST: isolated snares / on-beat kicks on a post-drop half-time
outgoing overlap. The 40 ms pass line is unchanged. Flag off leaves official
kick+snare in place.
"""
import os, sys
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC2 = os.path.join(HERE, '..', '..', 'src2')
sys.path.insert(0, SRC2)
import breakdown_phase_est as B
import halfbeat as H
import engine as E

SR = E.SR
BEAT = E.BEAT
BAR = E.BAR
BS = E.BS


def _click(n, sr=SR, f=190.0, decay=30.0, amp=1.0):
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * f * t) * np.exp(-t * decay)).astype(np.float32)


def _put(y, sig, t, sr=SR):
    i = int(round(t * sr))
    if i < 0 or i >= len(y):
        return
    n = min(len(sig), len(y) - i)
    y[i:i + n] += sig[:n]


def synth(nbars, kind, delay_ms=0.0, s0_bars=8, sr=SR):
    """Stereo deck starting at mix bar 0. kind: 'regular' or 'halftime'.
    delay_ms > 0 = this deck's hits land later (A-late if applied to A)."""
    pre = s0_bars * BAR
    n = int(round((pre + nbars * BAR + BAR) * sr))
    y = np.zeros((n, 2), np.float32)
    kick = _click(int(0.10 * sr), f=60, decay=18, amp=1.2)
    snare = _click(int(0.12 * sr), f=1800, decay=22, amp=0.9)
    delay = delay_ms / 1000.0
    for k in range(nbars):
        b = pre + k * BAR + delay
        if kind == 'regular':
            _put(y[:, 0], kick, b, sr); _put(y[:, 1], kick, b, sr)
            _put(y[:, 0], snare, b + BEAT, sr); _put(y[:, 1], snare, b + BEAT, sr)
            _put(y[:, 0], snare, b + 3 * BEAT, sr); _put(y[:, 1], snare, b + 3 * BEAT, sr)
        elif kind == 'halftime':
            # kick on 1 of even bars only; snares still on 2 and 4 (js13-like)
            if k % 2 == 0:
                _put(y[:, 0], kick, b, sr); _put(y[:, 1], kick, b, sr)
            _put(y[:, 0], snare, b + BEAT, sr); _put(y[:, 1], snare, b + BEAT, sr)
            _put(y[:, 0], snare, b + 3 * BEAT, sr); _put(y[:, 1], snare, b + 3 * BEAT, sr)
        else:
            raise ValueError(kind)
    return y


S0 = 120
START, END = 128, 160
N = END - START


def _pair(delay_b_ms=0.0, delay_a_ms=0.0):
    yA = synth(N + 16, 'halftime', delay_ms=delay_a_ms, s0_bars=8)
    yB = synth(N + 16, 'regular', delay_ms=delay_b_ms, s0_bars=8)
    # both crops start at mix S0 = 120, 8 bars pre
    return yA, yB


def test_flag_off_does_not_switch_estimator():
    os.environ.pop('BREAKDOWN_PHASE_EST', None)
    yA, yB = _pair(0)
    r = B.measure(yA, yB, S0, START, END, BS, SR, BEAT, force=False,
                  a_id=None, src_bars=None)
    assert r['official'] is True and r['active'] is False
    assert r['family'] == 'kick+snare'


def test_aligned_halftime_outgoing_passes_under_new_estimator():
    yA, yB = _pair(0)
    r = B.measure(yA, yB, S0, START, END, BS, SR, BEAT, force=True)
    assert r['active'] is True
    assert r['usable'] and r['family'] in ('snare', 'snare+onbeat_kick', 'onbeat_kick')
    assert r['ok'] and abs(r['median_ms']) <= B.PASS_MS, r
    assert r['pass_ms'] == 40.0


def test_halfbeat_trainwreck_still_fails():
    """Incoming delayed by half a beat: snares and on-beat kicks must fail 40 ms."""
    yA, yB = _pair(delay_b_ms=H.BEAT * 1000 / 2)  # B late by 172 ms
    r = B.measure(yA, yB, S0, START, END, BS, SR, BEAT, force=True)
    assert r['active'] is True
    assert r['usable'], r
    assert not r['ok'], r
    assert abs(r['median_ms']) > B.PASS_MS, r
    # residual should sit near a half-beat, not near 0
    assert abs(abs(r['median_ms']) - H.BEAT * 1000 / 2) < 40, r


def test_eighty_ms_flam_still_fails():
    yA, yB = _pair(delay_b_ms=80.0)
    r = B.measure(yA, yB, S0, START, END, BS, SR, BEAT, force=True)
    assert r['usable'] and not r['ok'], r
    assert abs(r['median_ms']) > B.PASS_MS, r


def test_pass_line_is_not_loosened():
    assert B.PASS_MS == 40.0
    # 50 ms residual (over the line) must fail
    yA, yB = _pair(delay_b_ms=50.0)
    r = B.measure(yA, yB, S0, START, END, BS, SR, BEAT, force=True)
    assert r['usable'] and not r['ok'], r
    assert r['pass_ms'] == 40.0


def test_known_halftime_after_breakdown_activates():
    secs = dict(drop1=64, breakdown=128, drops=[[64, 128], [160, 224]])
    ht = [[129, 162]]
    src = list(range(128, 160))
    active, rec = B.outgoing_is_breakdown_ht('x', src, secs=secs, ht_sections=ht)
    assert active and rec.get('ht_hit') == [129, 162], rec


def test_intro_overlap_does_not_activate_without_margin():
    """A pre-drop intro is not a post-drop breakdown (even if half-time is listed later)."""
    secs = dict(drop1=64, breakdown=128)
    ht = [[129, 162]]
    src = list(range(0, 16))
    active, rec = B.outgoing_is_breakdown_ht('x', src, secs=secs, ht_sections=ht)
    assert not active, rec
