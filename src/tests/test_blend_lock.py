"""BLEND_LOCK (src2/finephase.lock_decks, 2026-11-17 RCA, off by default).

Measure the signed kick+snare lag between the two decks on loud overlap bars and
nudge only the incoming deck so they lock. Does not move the outgoing track, does
not loosen F1/X1/GAP_DB, and does not change rules.json unless a later cohort run
keeps the flag. A lag already under 15 ms, or one near half a beat, is left alone.
"""
import os, sys, json, copy
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
    old = {k: os.environ.get(k) for k in ('BLEND_LOCK', 'FINE_PHASE', 'BLEND_LOCK_MIN_MS', 'BLEND_LOCK_MAX_MS')}
    yield
    F.clear(); E._cache.clear(); E._LOCK.clear()
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_flag_off_by_default():
    os.environ.pop('BLEND_LOCK', None)
    assert F.lock_flag_on() is False
    os.environ['BLEND_LOCK'] = '1'
    assert F.lock_flag_on() is True


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


def test_incoming_120ms_early_is_locked(tmp_path, monkeypatch):
    """Incoming kicks 120 ms early vs the outgoing; BLEND_LOCK delays B by ~120 ms."""
    monkeypatch.chdir(tmp_path)
    nbar = 32
    # Outgoing on the grid (d0=0.5). Incoming 120 ms early.
    yA = drums(nbars=nbar, t0=0.5, two_step=True, seed=1)
    yB = drums(nbars=nbar, t0=0.5 - 0.120, two_step=True, seed=2)
    _write(tmp_path, 'outA', yA, grid(0.5, nbar), nbar)
    _write(tmp_path, 'inB', yB, grid(0.5, nbar), nbar)
    # 16-bar overlap at mix bar 8: A src 8-24, B src 8-24, both full gain
    decks = [_deck('outA', 0, 0, 24, 1.0), _deck('inB', 8, 8, 24, 1.0)]
    trans = [dict(a='outA', b='inB', start_bar=8, end_bar=24)]
    os.environ['BLEND_LOCK'] = '1'
    E._cache.clear()
    lag, report = F.measure_blend_lag(decks, trans, 0)
    assert lag is not None and 80 < lag < 160, report  # A late vs early-B => positive lag
    F.lock_decks(decks, trans)
    assert trans[0]['blend_lock'].get('applied') is True, trans[0]['blend_lock']
    assert abs(decks[1]['blend_lock_ms'] - lag) < 1, (decks[1], report)
    # after the lock, residual on a re-measure should be under 15 ms
    lag2, report2 = F.measure_blend_lag(decks, trans, 0)
    assert lag2 is not None and abs(lag2) < 15, report2


def test_already_locked_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nbar = 24
    y = drums(nbars=nbar, t0=0.5, two_step=True, seed=3)
    _write(tmp_path, 'outA', y, grid(0.5, nbar), nbar)
    _write(tmp_path, 'inB', y, grid(0.5, nbar), nbar)
    decks = [_deck('outA', 0, 0, 24), _deck('inB', 8, 8, 16)]
    trans = [dict(a='outA', b='inB', start_bar=8, end_bar=24)]
    os.environ['BLEND_LOCK'] = '1'
    E._cache.clear()
    F.lock_decks(decks, trans)
    assert not trans[0]['blend_lock'].get('applied'), trans[0]['blend_lock']
    assert not decks[1].get('blend_lock_ms')


def test_flag_off_does_not_touch_decks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nbar = 24
    yA = drums(nbars=nbar, t0=0.5, two_step=True, seed=1)
    yB = drums(nbars=nbar, t0=0.5 - 0.120, two_step=True, seed=2)
    _write(tmp_path, 'outA', yA, grid(0.5, nbar), nbar)
    _write(tmp_path, 'inB', yB, grid(0.5, nbar), nbar)
    decks = [_deck('outA', 0, 0, 24), _deck('inB', 8, 8, 16)]
    trans = [dict(a='outA', b='inB', start_bar=8, end_bar=24)]
    os.environ.pop('BLEND_LOCK', None)
    F.lock_decks(decks, trans)
    assert 'blend_lock' not in trans[0]
    assert 'blend_lock_ms' not in decks[1]


def test_real_pair_locks_under_15ms():
    root = os.path.join(HERE, '..', '..', 'src2')
    meta_p = '/tmp/protrans_bench/rca17b_wUVt_GsvMzw_tCyYwek-o28_meta.json'
    if not os.path.exists(meta_p) or not os.path.exists(os.path.join(root, 'st', 'tCyYwek-o28.wav')):
        pytest.skip('Nov 17 pair render not on this box')
    cwd = os.getcwd()
    os.chdir(root)
    try:
        M = json.load(open(meta_p))
        decks, trans = copy.deepcopy(M['decks']), copy.deepcopy(M['trans'])
        os.environ['BLEND_LOCK'] = '1'
        E._cache.clear(); F.clear(); E._LOCK.clear()
        lag, _ = F.measure_blend_lag(decks, trans, 0)
        assert lag is not None and 80 < lag < 150, lag
        F.lock_decks(decks, trans)
        assert trans[0]['blend_lock'].get('applied') is True
        lag2, rep2 = F.measure_blend_lag(decks, trans, 0)
        assert lag2 is not None and abs(lag2) < 15, rep2
    finally:
        os.chdir(cwd)
        E._cache.clear(); F.clear(); E._LOCK.clear()


def test_dry_plan_writes_blend_lock_ms():
    """Official recreate uses mix_simple --dry; the lock must be in dry_meta or the clip is a no-op."""
    import subprocess, tempfile
    root = os.path.join(HERE, '..', '..', 'src2')
    meta_p = '/tmp/protrans_bench/rca17b_wUVt_GsvMzw_tCyYwek-o28_meta.json'
    plan_p = '/tmp/protrans_bench/rca17b_plan.json'
    if not os.path.exists(meta_p) or not os.path.exists(plan_p) or not os.path.exists(os.path.join(root, 'st', 'tCyYwek-o28.wav')):
        pytest.skip('Nov 17 pair render not on this box')
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, 'drylock')
        env = dict(os.environ)
        # Loud-bar lag follows the official fade curves. Without FADE=long /
        # TAIL_EXIT=6 the equally-loud region slides to bars 230-234 and the
        # estimator reports a bogus -108 ms instead of the +123 ms clash lag.
        rules_p = os.path.join(HERE, '..', '..', 'protrans', 'rules.json')
        rules = json.load(open(rules_p))
        for k, v in rules.items():
            if k == 'note' or v is None:
                continue
            env[str(k)] = str(v)
        env['BLEND_LOCK'] = '1'
        env.pop('FINE_PHASE', None)
        r = subprocess.run(['python3', 'mix_simple.py', '--plan', plan_p, '--out', out, '--dry'],
                           cwd=root, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
        M = json.load(open(out + '_dry_meta.json'))
        inc = M['decks'][1]
        report = M['trans'][0].get('blend_lock') or {}
        assert report.get('applied') is True, report
        ms = inc.get('blend_lock_ms')
        assert ms is not None and 80 < float(ms) < 150, (ms, report)


def test_confident_lag_accepts_this_pair_and_rejects_misfires():
    """The first 33-pair eval applied 2-bar / 50 ms clusters to already-locked blends
    (e.g. netsky__02 offs [152, -61] -> -61 ms, lock 2.4 -> 57.6, score -5.86).
    A tight 3-bar majority is required before we move a deck."""
    # 2-bar offs and 1-bar offs for the 2026-11-17 clash: 3-of-4 at +123
    assert abs(F.confident_lag([130.6, 123.4, 123.4, -50.8]) - 123.4) < 1
    assert abs(F.confident_lag([130.6, 123.4, 30.5, 122.0]) - 123.4) < 2
    # already-locked smear (wilkinson): do not invent an 18.9 ms lock
    assert F.confident_lag([-1.5, 18.9, 40.6]) is None
    # two disagreeing bars (netsky__02)
    assert F.confident_lag([152.4, -61.0]) is None
    # 2-of-6 at -59.5 (netsky__17)
    assert F.confident_lag([-59.5, 50.8, -59.5, -168.3, 114.6, 37.7]) is None
    # 2-of-4 at -74 (hybrid_minds__08)
    assert F.confident_lag([114.6, -74.0, -75.5, -45.0]) is None
    # 2-of-3 at 135 (hybrid_minds__11)
    assert F.confident_lag([-90.0, 149.5, 121.9]) is None
    # 23-to-57 ms smear (joe_syntax__01, 1-bar offs)
    assert F.confident_lag([137.9, 42.1, 23.2, 56.6]) is None
    # already-locked 10 ms bar inside a 17 ms cluster (hybrid_minds_ukf__19)
    assert F.confident_lag([29.0, 17.4, 10.2, 158.2]) is None
    # real tight lag over 8 bars should still apply (~-67 ms)
    lag = F.confident_lag([-37.7, -58.0, -74.0, -59.5, -72.6, -68.2, -79.8, -66.8])
    assert lag is not None and 50 < abs(lag) < 80
