"""HALFBEAT_LOCK (src2/finephase.py, 2026-11-25, off by default).

Verifies:
1. Off by default (HALFBEAT_LOCK=0 leaves ~172 ms lags untouched).
2. Genuine half-beat offset (kick+snare aligned at +half_beat, r_half > r_0) gets re-phased
   by ~+172.4 ms when HALFBEAT_LOCK=1 and BLEND_LOCK=1, dropping residual lag < 15 ms.
3. Mid-band spoof where kick+snare is already dead-locked at 0 ms (ukf__28 failure mode:
   r0 >= 0.50 on 30-150 + 1500-5000 Hz while 150-1500 Hz mid synth gives +165 ms) is
   rejected and NOT re-phased.
"""
import os, sys, json
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
import engine as E
import finephase as F
from test_halfbeat import drums, grid, SR, BEAT, BAR


@pytest.fixture(autouse=True)
def _clean():
    F.clear(); E._cache.clear(); E._LOCK.clear()
    old = {k: os.environ.get(k) for k in ('BLEND_LOCK', 'HALFBEAT_LOCK', 'FINE_PHASE', 'HALFBEAT_LOCK_MAX_MS')}
    yield
    F.clear(); E._cache.clear(); E._LOCK.clear()
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _write(tmp, tid, y, g, nbar):
    import soundfile as sf
    stereo = np.stack([y, y], 1) if y.ndim == 1 else y
    (tmp / 'st').mkdir(exist_ok=True)
    sf.write(tmp / 'st' / f'{tid}.wav', stereo, SR, subtype='FLOAT')
    g = dict(g)
    g.setdefault('bar', dict(all=[-10.0] * nbar, drums=[-12.0] * nbar, low=[-18.0] * nbar))
    json.dump(g, open(tmp / 'st' / f'{tid}.json', 'w'))


def _deck(tid, start, src0, n, gain=1.0):
    return dict(id=tid, start_bar=start, end_bar=start + n,
                full_map=[[src0 + k, 'mix'] for k in range(n)],
                auto={'gain': [[start, gain], [start + n, gain]]}, acap=False)


def test_halfbeat_lock_off_by_default():
    os.environ.pop('HALFBEAT_LOCK', None)
    assert F.hb_lock_flag_on() is False
    os.environ['HALFBEAT_LOCK'] = '1'
    assert F.hb_lock_flag_on() is True


def test_genuine_halfbeat_offset_fixed_when_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nbar = 32
    yA = drums(nbars=nbar, t0=0.5, two_step=True, seed=11)
    # B arrives ~166 ms early (close to half a beat) on both kick+snare and mid
    yB = drums(nbars=nbar, t0=0.5 - 0.166, two_step=True, seed=12)
    _write(tmp_path, 'outA', yA, grid(0.5, nbar), nbar)
    _write(tmp_path, 'inB', yB, grid(0.5, nbar), nbar)
    decks = [_deck('outA', 0, 0, 24, 1.0), _deck('inB', 8, 8, 24, 1.0)]
    trans = [dict(a='outA', b='inB', start_bar=8, end_bar=24)]

    # Off by default: BLEND_LOCK=1 alone leaves >150 ms alone
    os.environ['BLEND_LOCK'] = '1'
    os.environ.pop('HALFBEAT_LOCK', None)
    E._cache.clear()
    F.lock_decks(decks, trans)
    assert not trans[0]['blend_lock'].get('applied')
    assert not decks[1].get('blend_lock_ms')

    # With HALFBEAT_LOCK=1: re-phases by +half_beat (~172.4 ms) and drops residual < 15 ms
    os.environ['HALFBEAT_LOCK'] = '1'
    E._cache.clear()
    F.lock_decks(decks, trans)
    assert trans[0]['blend_lock'].get('applied') is True
    assert trans[0]['blend_lock'].get('halfbeat_lock') is True
    assert abs(decks[1]['blend_lock_ms'] - (F.BEAT_MS / 2.0)) < 1.0
    lag2, _ = F.measure_blend_lag(decks, trans, 0)
    assert lag2 is not None and abs(lag2) < 15.0


def test_kick_snare_locked_mid_spoof_is_rejected(tmp_path, monkeypatch):
    """If kick+snare is already dead-locked at 0 ms (r0 >= 0.50), do NOT apply half-beat
    shift even if bar_offsets (30-150 + 150-1500 Hz) returned +164 ms."""
    monkeypatch.chdir(tmp_path)
    nbar = 24
    yA = drums(nbars=nbar, t0=0.5, two_step=True, seed=21)
    yB = drums(nbars=nbar, t0=0.5, two_step=True, seed=22)
    _write(tmp_path, 'outA', yA, grid(0.5, nbar), nbar)
    _write(tmp_path, 'inB', yB, grid(0.5, nbar), nbar)
    decks = [_deck('outA', 0, 0, 24, 1.0), _deck('inB', 8, 8, 16, 1.0)]
    trans = [dict(a='outA', b='inB', start_bar=8, end_bar=24)]

    os.environ['BLEND_LOCK'] = '1'
    os.environ['HALFBEAT_LOCK'] = '1'
    E._cache.clear()
    monkeypatch.setattr(F, 'measure_blend_lag',
                        lambda d, t, i: (164.0, dict(lag_ms=164.0, bars=list(range(10, 17)), offs=[164.0]*7)))
    F.lock_decks(decks, trans)
    assert trans[0]['blend_lock'].get('applied') is False
    assert not decks[1].get('blend_lock_ms')
    assert trans[0]['blend_lock']['halfbeat_check']['r0'] > 0.50
