"""Unit tests for the replica/hardcheck.py beat_clash threshold fix (2026-11-25).

After BLEND_LOCK sets blend_lock_ms, finephase.measure_blend_lag uses prefer_zero=True
robust_lag, returning sub-15 ms residuals (e.g. -0.73, +1.45, -2.90, -8.71 ms).
hardcheck.check must only flag beat_clash when halfbeat fails OR |lag| > FP.LOCK_MIN_MS (15 ms),
keeping FP.LOCK_MIN_MS untouched and still reporting residual_lag_ms.
"""
import json, os, sys
import numpy as np
import pytest

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


def _stub_env(monkeypatch, tmp_path, lag_val, hb_fail=False):
    cal = tmp_path / 'cal.json'
    cal.write_text(json.dumps({'lows_dip_p95': 20.0, 'pump_p95': 10.0}))
    meta = tmp_path / 'meta.json'
    meta.write_text(json.dumps({
        'decks': [{}, {}],
        'trans': [{
            'start_bar': 0,
            'end_bar': 8,
            'halfbeat': {'fail': hb_fail},
        }],
    }))
    monkeypatch.setattr(HC, 'CAL', str(cal))
    z = np.zeros((8 * 2048, 2), dtype=np.float32)
    monkeypatch.setattr(BD, 'crop_decks', lambda M, i: (0, z, z))
    monkeypatch.setattr(BD, 'band_bar_db', lambda A, n, bs, *a: np.full(n, -10.0))
    monkeypatch.setattr(FP, 'measure_blend_lag', lambda decks, trans, i: (lag_val, {'lag_ms': lag_val}))
    return str(meta)


def test_lock_min_ms_threshold_untouched():
    assert FP.LOCK_MIN_MS == 15.0


@pytest.mark.parametrize('lag_ms', [-0.73, 1.45, -2.90, -8.71, 0.0, 15.0, -15.0])
def test_sub_threshold_lag_not_flagged(monkeypatch, tmp_path, lag_ms):
    meta = _stub_env(monkeypatch, tmp_path, lag_ms, hb_fail=False)
    res = HC.check(meta)
    assert res['beat_clash'] is False
    assert res['hard_fail'] is False
    assert res['residual_lag_ms'] == lag_ms


@pytest.mark.parametrize('lag_ms', [15.1, -15.1, 45.0, -120.0, 163.99, 166.89])
def test_above_threshold_lag_still_flagged(monkeypatch, tmp_path, lag_ms):
    meta = _stub_env(monkeypatch, tmp_path, lag_ms, hb_fail=False)
    res = HC.check(meta)
    assert res['beat_clash'] is True
    assert res['hard_fail'] is True
    assert res['residual_lag_ms'] == lag_ms


@pytest.mark.parametrize('lag_ms', [None, 0.0, -0.73])
def test_halfbeat_fail_still_flagged(monkeypatch, tmp_path, lag_ms):
    meta = _stub_env(monkeypatch, tmp_path, lag_ms, hb_fail=True)
    res = HC.check(meta)
    assert res['beat_clash'] is True
    assert res['hard_fail'] is True
    assert res['halfbeat_fail'] is True
