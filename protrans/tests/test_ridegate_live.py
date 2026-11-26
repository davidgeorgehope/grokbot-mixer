"""RIDEGATE is a live (non-map) ridegate path, off by default. Does not write rules.json."""
from __future__ import annotations
import inspect, json, os, sys, pathlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'replica'))
import recreate
import ridegate_live as RG
import picker_1125 as Q
import picker_1119b as B

AGREE_MAP = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'replica', 'nightly_1126_work', 'ridegate_live_agree_map.json')
AGREE_CV = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'replica', 'nightly_1126_work', 'ridegate_live_agree_cv.json')


def test_ridegate_flag_default_off(monkeypatch):
    monkeypatch.delenv('RIDEGATE', raising=False)
    assert recreate.ridegate_live_on({}, {}) is False
    assert RG.flag_on({}, {}) is False
    assert recreate.ridegate_live_on({'RIDEGATE': 1}, {}) is True
    assert recreate.ridegate_live_on({}, {'RIDEGATE': '1'}) is True
    monkeypatch.setenv('RIDEGATE', '1')
    assert recreate.ridegate_live_on({}, {}) is True
    monkeypatch.delenv('RIDEGATE', raising=False)
    src = inspect.getsource(recreate.apply_rules)
    assert "'RIDEGATE'" in src
    assert "'RIDEGATE_PACK'" in src
    env = recreate.apply_rules({})
    assert 'RIDEGATE' not in env
    env = recreate.apply_rules({'RIDEGATE': 1})
    assert env.get('RIDEGATE') == '1'
    env = recreate.apply_rules({'RIDEGATE': 1, 'RIDEGATE_PACK': '/tmp/pack.json'})
    assert env.get('RIDEGATE_PACK') == '/tmp/pack.json'


def test_ridegate_does_not_write_rules_json():
    import paths
    p = pathlib.Path(paths.RULES)
    before = p.read_bytes()
    mtime = p.stat().st_mtime
    recreate.apply_rules({})
    recreate.apply_rules({'RIDEGATE': 1})
    recreate.ridegate_live_on({'RIDEGATE': 1}, {})
    RG.flag_on({'RIDEGATE': 1}, {})
    assert p.stat().st_mtime == mtime
    assert p.read_bytes() == before
    rules = json.loads(before)
    assert 'RIDEGATE' not in rules
    assert 'RIDEGATE_PACK' not in rules


def _toy(n_bars=200, drops=None, drop1=32, intro_len=16, outro_start=168, breakdown=None, drop2=None):
    return dict(n_bars=n_bars, music_end=n_bars, drops=drops or [[32, 80]], drop1=drop1,
                intro_len=intro_len, outro_start=outro_start, breakdown=breakdown, drop2=drop2,
                bass_by_section={})


def test_row_from_default_and_window():
    sa, sb = _toy(), _toy(n_bars=160, drop1=48, drops=[[48, 96]], outro_start=128)
    r = RG.row_from_default(sa, sb, dex=153.0, dcue=17.0, dX=16, pid='toy')
    assert 'default' in r['E'][r['Edix']]['tags']
    assert r['E'][r['Edix']]['v'] == 153.0
    assert 'default' in r['C'][r['Cdix']]['tags']
    assert r['C'][r['Cdix']]['v'] == 17.0
    dec = B.decide(r, r['Edix'], r['Cdix'], r['dX'])
    assert dec['is_default'] is True
    assert dec['win'] is None
    # a legal mid-track exit should produce a window
    je = next(i for i, c in enumerate(r['E']) if c['v'] == 65.0)
    dec2 = B.decide(r, je, r['Cdix'], 16)
    assert dec2['is_default'] is False
    assert dec2['win'] == ['n', 80, None, 16, 16]
    dex, dcue, dX = RG.default_from_win(['n', 168, None, 16, 16])
    assert (dex, dcue, dX) == (153.0, 17.0, 16)


def test_ride_pick_gate():
    sa, sb = _toy(), _toy()
    r = RG.row_from_default(sa, sb, dex=153.0, dcue=17.0, dX=16)
    # mid-track exit: music_end 200, v=65 -> left 135 > 40
    je = next(i for i, c in enumerate(r['E']) if c['v'] == 65.0)
    assert Q.is_mid(r, r['E'][je]['v']) is True
    assert Q.ride_pick(r, je, 0.59, 0.6) == r['Edix']  # leave: stay on default
    assert Q.ride_pick(r, je, 0.6, 0.6) == je          # ride
    assert Q.ride_pick(r, r['Edix'], 0.1, 0.6) == r['Edix']
    # late exit is not mid-track, so the gate does not override
    late = next(i for i, c in enumerate(r['E']) if r['sa']['music_end'] - c['v'] <= 40)
    assert Q.is_mid(r, r['E'][late]['v']) is False
    assert Q.ride_pick(r, late, 0.1, 0.6) == late


def test_maybe_apply_abstain_and_inject():
    sa, sb = _toy(), _toy(n_bars=160, drop1=48, drops=[[48, 96]], outro_start=128)
    r = RG.row_from_default(sa, sb, 153.0, 17.0, 16)
    # Fake pack: booster-like objects via a thin wrapper over predict_rows' pieces.
    class _Fake:
        pass
    # Rank exit so mid-track 65 is the unique argmax; cue stays on default; ride p high enough to take it.
    def pred_exit(X):
        n = len(np.asarray(X))
        s = np.zeros(n)
        j = next(i for i, c in enumerate(r['E']) if c['v'] == 65.0)
        s[j] = 10.0
        return s
    def pred_cue(X):
        return np.zeros(len(np.asarray(X)))
    def pred_ride(X):
        return np.array([0.9] * (1 if np.asarray(X).ndim == 1 else len(np.asarray(X))))
    pack = dict(_mE=type('B', (), {'predict': staticmethod(pred_exit)})(),
                _mC=type('B', (), {'predict': staticmethod(pred_cue)})(),
                _mR=type('B', (), {'predict': staticmethod(pred_ride)})(),
                exit_tau=-1e9, cue_tau=0.25, theta=0.6)
    cs = [dict(fam='default', win=['n', 168, None, 16, 16], env={}, cost=0.0)]
    hit, dec, injected = RG.maybe_apply(pack, sa, sb, ['n', 168, None, 16, 16], cs)
    assert dec['is_default'] is False
    assert dec['win'] == ['n', 80, None, 16, 16]
    assert hit is not None
    assert injected is True
    assert cs[-1]['win'] == ['n', 80, None, 16, 16]
    # ride gate below theta on a mid-track pick -> abstain, no inject
    def pred_ride_low(X):
        return np.array([0.1] * (1 if np.asarray(X).ndim == 1 else len(np.asarray(X))))
    pack2 = dict(pack, _mR=type('B', (), {'predict': staticmethod(pred_ride_low)})())
    cs2 = [dict(fam='default', win=['n', 168, None, 16, 16], env={}, cost=0.0)]
    hit2, dec2, inj2 = RG.maybe_apply(pack2, sa, sb, ['n', 168, None, 16, 16], cs2)
    assert dec2['is_default'] is True
    assert hit2 is None and inj2 is False
    assert len(cs2) == 1


def test_agree_map_if_present():
    if not os.path.exists(AGREE_MAP):
        return
    r = json.load(open(AGREE_MAP))
    assert r['n'] == 33
    assert r['agree'] == 33
    assert r['rate'] == 1.0
    assert r['disagree'] == []


def test_agree_cv_if_present():
    if not os.path.exists(AGREE_CV):
        return
    r = json.load(open(AGREE_CV))
    assert r['n'] == 1001
    assert r['agree'] == r['n']
    assert r['rate'] == 1.0
    assert r['disagree'] == []
