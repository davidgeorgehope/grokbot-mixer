"""FINE_PHASE (src2/finephase.py, 2026-11-17 RCA, off by default).

A track whose intro is a confident quarter-to-third-beat off the global (drop-locked)
grid gets a per-phrase time nudge on those source bars so the kicks/snares land on the
mix grid. A correctly phased track, and a weak/short phrase, are left alone. Does not
loosen X1, GAP_DB, or the half-beat gate. rules.json is unchanged unless a later
cohort run keeps the flag.
"""
import os, sys, json
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src2'))
import halfbeat as H
import finephase as F
from test_halfbeat import drums, grid, SR, BEAT, BAR


@pytest.fixture(autouse=True)
def _clean():
    F.clear()
    old = {k: os.environ.get(k) for k in ('FINE_PHASE', 'FINE_PHASE_MIN_MS', 'FINE_PHASE_MIN_STRENGTH')}
    yield
    F.clear()
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_flag_off_by_default():
    os.environ.pop('FINE_PHASE', None)
    assert F.flag_on() is False
    os.environ['FINE_PHASE'] = '0'
    assert F.flag_on() is False
    os.environ['FINE_PHASE'] = '1'
    assert F.flag_on() is True


def test_correct_grid_gets_no_nudge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    y = drums(nbars=48, t0=0.5, two_step=True)
    g = grid(0.5, 46)
    (tmp_path / 'st').mkdir()
    _write_track(tmp_path, 'ok', y, g)
    nudges = F.phrase_nudges('ok', g)
    assert nudges == {}, nudges


def test_early_intro_is_nudged_later_drop_is_not(tmp_path, monkeypatch):
    """Bars 0-31: drums 151 ms early (Ghetto Blaster intro-like). Bars 32-47: on the grid."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'st').mkdir()
    # Build audio: first 32 bars start 151 ms earlier than the grid's d0, last 16 on-grid.
    early = 0.151
    y_early = drums(nbars=32, t0=0.5 - early, two_step=True, seed=1)
    y_drop = drums(nbars=16, t0=0.5 + 32 * BAR, two_step=True, seed=2)
    n = max(len(y_early), len(y_drop))
    y = np.zeros(n, np.float32)
    y[:len(y_early)] += y_early
    y[:len(y_drop)] += y_drop
    g = grid(0.5, 48)
    _write_track(tmp_path, 'jump', y, g)
    nudges = F.phrase_nudges('jump', g)
    intro = [nudges.get(k, 0) for k in range(0, 32)]
    drop = [nudges.get(k, 0) for k in range(32, 48)]
    assert intro and all(ms > 100 for ms in intro), (intro, F.report('jump'))
    # +151 ms reads the source earlier so early hits land on the grid
    assert abs(float(np.median(intro)) - 151) < 25, intro
    assert all(abs(ms) < F.MIN_MS for ms in drop), (drop, F.report('jump'))


def test_nudge_sign_matches_engine(tmp_path, monkeypatch):
    """phase < 0 (hits early) => positive nudge (engine reads the source earlier)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'st').mkdir()
    early = 0.151
    y = drums(nbars=32, t0=0.5 - early, two_step=True)
    g = grid(0.5, 30)
    _write_track(tmp_path, 'early', y, g)
    ph, s, n = H.deck_phase('early', list(range(8, 24)), g)
    assert ph < -0.3 and s >= 1.5, (ph, s, n)
    ms = F.nudge_ms('early', 16)
    assert ms > 0 and abs(ms + ph * F.BEAT_MS) < 2, (ms, ph)


def test_weak_phrase_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'st').mkdir()
    # complete silence: the template has no drum pattern to lock onto
    n = int((0.5 + 32 * BAR + 1) * SR)
    y = np.zeros(n, np.float32)
    g = grid(0.5, 30)
    _write_track(tmp_path, 'weak', y, g)
    assert F.phrase_nudges('weak', g) == {}


def test_real_ghetto_blaster_intro_is_nudged():
    root = os.path.join(HERE, '..', '..', 'src2')
    wav = os.path.join(root, 'st', 'tCyYwek-o28.wav')
    if not os.path.exists(wav):
        pytest.skip('Ghetto Blaster source not on this box')
    cwd = os.getcwd()
    os.chdir(root)
    try:
        F.clear()
        g = json.load(open('st/tCyYwek-o28.json'))
        # intro 0-39, drop2 144-191
        intro = [F.nudge_ms('tCyYwek-o28', k) for k in range(24, 32)]
        drop2 = [F.nudge_ms('tCyYwek-o28', k) for k in range(144, 152)]
        assert all(ms > 100 for ms in intro), (intro, F.report('tCyYwek-o28'))
        assert abs(float(np.median(intro)) - 151) < 30, intro
        assert all(abs(ms) < 30 for ms in drop2), (drop2, F.report('tCyYwek-o28'))
    finally:
        os.chdir(cwd)
        F.clear()


def _write_track(tmp, tid, y, g):
    import soundfile as sf
    # halfbeat.drum_envs / _load read st/<id>.wav at native SR as stereo-capable
    stereo = np.stack([y, y], 1) if y.ndim == 1 else y
    sf.write(tmp / 'st' / f'{tid}.wav', stereo, SR, subtype='FLOAT')
    json.dump(g, open(tmp / 'st' / f'{tid}.json', 'w'))
