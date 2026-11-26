"""Tests for replica/hardcheck.py incoming_vanish hard check (2026-11-25)."""
import json
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROTRANS = os.path.dirname(HERE)
REPLICA = os.path.join(PROTRANS, 'replica')
SRC2 = os.path.join(os.path.dirname(PROTRANS), 'src2')
for p in (REPLICA, PROTRANS, SRC2):
    if p not in sys.path:
        sys.path.insert(0, p)

import blend_diag as BD
import finephase as FP
import hardcheck as HC


def test_incoming_vanish_detects_pola02_pattern_and_ignores_clean():
    # pola02_blocked_ee pattern: B audible around -34..-36 dB vs A ~-22..-27 dB,
    # then vanishes (-42..-43 dB, < A - 16 dB) for 2 bars, then returns (-16 dB).
    alA = np.full(40, -24.0)
    alA[3:11] = [-21.9, -24.3, -22.9, -26.4, -21.9, -22.6, -22.4, -27.3]
    alA[13:15] = [-21.8, -25.1]
    alB_bad = np.full(40, -15.5)
    alB_bad[:3] = [-50.9, -44.9, -40.7]
    alB_bad[3:13] = [-34.1, -37.1, -36.9, -36.7, -36.5, -36.7, -36.7, -36.2, -37.5, -37.2]
    alB_bad[13:16] = [-41.9, -42.7, -33.7]

    cal = json.load(open(HC.CAL))
    assert 'incoming_vanish_p95' in cal
    score_bad = HC.incoming_vanish(alB_bad, alA, 0, 40)
    assert score_bad > cal['incoming_vanish_p95']

    # Smooth monotonic incoming fade-in (pola02_fixed_ee pattern) passes with 0.0
    alB_good = np.full(40, -15.5)
    alB_good[:16] = np.linspace(-52.0, -33.7, 16)
    assert HC.incoming_vanish(alB_good, alA, 0, 40) == 0.0

    # Solo Track B breakdown after Deck A exits (B > A) is NOT a vanish fault
    alA_faded = np.full(40, -55.0)
    alB_solo = np.full(40, -15.0)
    alB_solo[20:24] = -32.0
    assert HC.incoming_vanish(alB_solo, alA_faded, 0, 40) == 0.0


def test_hardcheck_check_flags_incoming_vanish(monkeypatch, tmp_path):
    cal = tmp_path / 'cal.json'
    cal.write_text(json.dumps({'lows_dip_p95': 45.34, 'pump_p95': 10.0, 'incoming_vanish_p95': 5.24}))
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({'decks': [{}, {}], 'trans': [{'start_bar': 0, 'end_bar': 24, 'halfbeat': {'fail': False}}]}))
    monkeypatch.setattr(HC, 'CAL', str(cal))
    z = np.zeros((24 * 2048, 2), dtype=np.float32)
    monkeypatch.setattr(BD, 'crop_decks', lambda M, i: (0, z, z))
    monkeypatch.setattr(FP, 'measure_blend_lag', lambda decks, trans, i: (0.0, {'lag_ms': 0.0}))

    alA = np.full(24, -24.0)
    alB = np.full(24, -15.0)
    alB[:2] = -50.0
    alB[2:6] = -34.0
    alB[6:8] = -43.0
    alB[8:10] = -32.0

    def _band(arr, n, bs, band=None, fc=None):
        if band == 'low':
            return np.full(n, -25.0)
        if np.all(arr == 0):
            _band.idx += 1
            # crop_decks returns (0, A, B); check() calls band_bar_db(S), band_bar_db(A), band_bar_db(B)
            return np.full(n, -15.0) if _band.idx == 1 else (alA if _band.idx == 2 else alB)
        return np.full(n, -15.0)
    _band.idx = 0
    monkeypatch.setattr(BD, 'band_bar_db', _band)

    res = HC.check(str(meta))
    assert res['incoming_vanish'] is True
    assert res['incoming_vanish_db'] >= 8.0
    assert res['hard_fail'] is True
