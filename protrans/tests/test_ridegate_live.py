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



def test_legal_natural_uses_n_bars_not_music_end():
    """mix_simple injects when e <= t['nb'] (== sections n_bars). music_end is often shorter."""
    sa = dict(n_bars=229, music_end=221)
    sb = dict(n_bars=262, music_end=256)
    # the ridegate map window on hybrid_minds_ukf__09: past music_end, inside the grid
    assert RG._legal_natural(sa, sb, ['n', 224, None, 64, 16]) is True
    assert RG._legal_natural(sa, sb, ['n', 208, None, 48, 16]) is True
    # past the grid still illegal
    assert RG._legal_natural(sa, sb, ['n', 240, None, 64, 16]) is False
    # incoming cue past music_end but inside n_bars must also pass
    sb2 = dict(n_bars=198, music_end=190)
    assert RG._legal_natural(dict(n_bars=236, music_end=226), sb2, ['n', 232, None, 40, 16]) is True


def test_rendered_window_matches_map_for_pinned_pairs():
    """maybe_apply's window (what recreate would render) equals the map window for every
    pinned pair. Uses live src2 sections and an empty cs, so injection has to pass the
    same n_bars bound mix_simple uses. Does not render audio.
    """
    import paths
    mp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'replica', 'nightly_1126_work', 'map_ridegate.json')
    if not os.path.exists(mp_path) or not os.path.isdir(RG.PACK_DIR):
        return
    import run_admitted_tune as T
    mp = json.load(open(mp_path))['by_id']
    recs = {r['id']: r for r in T.load_recs()}
    pack = RG.load_pack()
    st = os.path.join(paths.SRC2, 'st')
    # map *render* windows (n1126_ridegate ckpt) when present
    try:
        mapped = T.load_ckpt('n1126_ridegate')
    except Exception:
        mapped = {}
    missing, disagree = [], []
    for pid, ref in sorted(mp.items()):
        rec = recs.get(pid)
        if rec is None:
            missing.append(pid); continue
        a, b = rec['a']['yt'], rec['b']['yt']
        spa, spb = os.path.join(st, f'{a}.sections.json'), os.path.join(st, f'{b}.sections.json')
        if not (os.path.exists(spa) and os.path.exists(spb)):
            missing.append(pid); continue
        sa, sb = json.load(open(spa)), json.load(open(spb))
        r = RG.row_for_render(sa, sb, 0.0, 0.0, 16, a_yt=a, b_yt=b, pid=pid)
        default_win = ['n', int(r['dex'] + r['dX'] - 1), None, int(r['dcue'] - 1), int(r['dX'])]
        hit, dec, _ = RG.maybe_apply(pack, sa, sb, default_win, cs=[], a_yt=a, b_yt=b, pid=pid)
        applied = list(hit['win']) if hit is not None else list(default_win)
        want = list(ref['win']) if ref.get('win') else None
        legal = bool(want) and RG._legal_natural(sa, sb, want) and not ref.get('abstain')
        expected = want if legal else list(default_win)
        if applied != expected:
            disagree.append(dict(id=pid, applied=applied, expected=expected, want=want,
                                 default=default_win, legal=legal, abstain=dec.get('is_default'),
                                 p_leave=dec.get('p_leave')))
        if pid in mapped:
            mwin = list((mapped[pid].get('pick') or {}).get('win') or [])
            if mwin and applied != mwin:
                disagree.append(dict(id=pid, vs='map_render', applied=applied, map_render=mwin))
    assert not missing, missing
    assert disagree == [], disagree
    assert len(mp) == 33



def test_linger_guard_flag_default_off(monkeypatch):
    monkeypatch.delenv('LINGER_GUARD', raising=False)
    assert recreate.linger_guard_on({}, {}) is False
    assert RG.linger_guard_on({}, {}) is False
    monkeypatch.setenv('LINGER_GUARD', '1')
    assert RG.linger_guard_on({}, {}) is True
    monkeypatch.delenv('LINGER_GUARD', raising=False)
    src = inspect.getsource(recreate.apply_rules)
    assert "'LINGER_GUARD'" in src
    env = recreate.apply_rules({})
    assert 'LINGER_GUARD' not in env
    env = recreate.apply_rules({'LINGER_GUARD': 1})
    assert env.get('LINGER_GUARD') == '1'
    import paths, json as _json
    rules = _json.loads(pathlib.Path(paths.RULES).read_bytes())
    assert 'LINGER_GUARD' not in rules


def test_live_predict_matches_built_row_when_present():
    """Wherever a built row exists (including holdout/fresh), live predict equals that row's decision."""
    RG.reset_built_index()
    pack = RG.load_pack()
    hold = [r for r in RG.load_all_built() if r['set'] == 'holdout']
    assert hold, 'need official holdout snapshot rows'
    RG._index_built()
    # holdout is indexed (the bug was skipping it)
    assert any(r['set'] == 'holdout' for r in RG._BUILT_BY_ID.values())
    yt_of = RG._yt_keys()
    checked = 0
    disagree = []
    for r in hold:
        key = yt_of.get(r['id'])
        if not key:
            continue
        a, b = key.split('|', 1)
        got = RG.row_for_render(r['sa'], r['sb'], r['dex'], r['dcue'], r['dX'], a_yt=a, b_yt=b, pid='live')
        assert got['id'] == r['id']
        dec_built = RG.predict_rows(pack, [r])[0]
        dec_live = RG.predict_rows(pack, [got])[0]
        if not RG._same(dec_live, dict(exit=dec_built['exit'], cue=dec_built['cue'], X=dec_built['X'],
                                       win=dec_built.get('win'), is_default=dec_built.get('is_default'))):
            # _same expects slightly different keys; compare directly
            pass
        same = (dec_live.get('is_default') == dec_built.get('is_default')
                and dec_live.get('win') == dec_built.get('win')
                and dec_live.get('exit') == dec_built.get('exit')
                and dec_live.get('cue') == dec_built.get('cue'))
        checked += 1
        if not same:
            disagree.append((r['id'], dec_built, dec_live))
        default_win = ['n', int(r['dex'] + r['dX'] - 1), None, int(r['dcue'] - 1), int(r['dX'])]
        hit, dec, _ = RG.maybe_apply(pack, r['sa'], r['sb'], default_win, cs=[], a_yt=a, b_yt=b, pid='live')
        applied = list(hit['win']) if hit is not None else list(default_win)
        expected = list(dec_built['win']) if dec_built.get('win') and not dec_built.get('is_default') else list(default_win)
        # linger guard is off by default, so maybe_apply should follow the built decision
        if applied != expected:
            disagree.append((r['id'], 'maybe_apply', applied, expected))
    assert checked >= 20, checked
    assert disagree == [], disagree


def test_linger_bars_and_guard(monkeypatch, tmp_path):
    # outgoing drop over bars 0-16, incoming breakdown 0-16
    sa = dict(n_bars=80, music_end=80, drops=[[16, 32]], phases=[{'name': 'drop', 'start': 16, 'end': 32}])
    sb = dict(n_bars=80, music_end=80, drops=[[16, 32]], breakdown=0, drop2=16,
              phases=[{'name': 'breakdown', 'start': 0, 'end': 16}, {'name': 'drop', 'start': 16, 'end': 32}])
    win = ['n', 32, None, 0, 16]  # legal (e-X==16) and 16 linger bars
    assert RG.linger_bars(sa, sb, win) == 16
    sb2 = dict(n_bars=80, drops=[[0, 16]], phases=[{'name': 'drop', 'start': 0, 'end': 16}])
    assert RG.linger_bars(sa, sb2, win) == 0
    cal = dict(p95=5.4, threshold=5.4)
    dest = tmp_path / 'linger.json'
    dest.write_text(__import__('json').dumps(cal))
    monkeypatch.setenv('LINGER_GUARD_CAL', str(dest))
    RG._LINGER_CAL = None
    assert RG.linger_threshold() == 5.4
    monkeypatch.delenv('LINGER_GUARD', raising=False)
    # flag off: maybe_apply still injects a lingering window
    r = RG.row_from_default(sa, sb, 1.0, 1.0, 16, pid='toy_linger')
    class _Fake: pass
    def pred_exit(X):
        s = np.zeros(len(np.asarray(X))); s[0] = 10.0; return s
    # force a mid-track pick by ranking a non-default exit if present
    je = next((i for i, c in enumerate(r['E']) if c['v'] != r['dex']), 0)
    def pred_exit2(X):
        s = np.zeros(len(np.asarray(X))); s[je] = 10.0; return s
    def pred_cue(X):
        return np.zeros(len(np.asarray(X)))
    def pred_ride(X):
        return np.array([0.9] * (1 if np.asarray(X).ndim == 1 else len(np.asarray(X))))
    pack = dict(_mE=type('B', (), {'predict': staticmethod(pred_exit2)})(),
                _mC=type('B', (), {'predict': staticmethod(pred_cue)})(),
                _mR=type('B', (), {'predict': staticmethod(pred_ride)})(),
                exit_tau=-1e9, cue_tau=0.25, theta=0.6)
    default_win = ['n', 32, None, 0, 16]
    # construct a want that lingers: monkeypatch predict
    # easier: call maybe_apply after patching linger on a known want via a thin stub
    monkeypatch.setenv('LINGER_GUARD', '1')
    # If the pack abstains, nothing to block. Drive want through linger_bars > threshold path
    # by using a pack-less wrapper: set dec via monkeypatch of predict_rows
    real_pred = RG.predict_rows
    def fake_pred(pack, rows):
        return [dict(is_default=False, win=['n', 32, None, 0, 16], exit=1.0, cue=1.0, X=16, p_leave=0.2)]
    monkeypatch.setattr(RG, 'predict_rows', fake_pred)
    hit, dec, inj = RG.maybe_apply(pack, sa, sb, default_win, cs=[], pid='toy_linger')
    assert dec.get('linger_blocked') is True
    assert dec.get('linger_bars') == 16
    assert hit is None and inj is False
    monkeypatch.setenv('LINGER_GUARD', '0')
    hit2, dec2, inj2 = RG.maybe_apply(pack, sa, sb, default_win, cs=[], pid='toy_linger')
    assert dec2.get('linger_blocked') is not True
    assert hit2 is not None
    monkeypatch.setattr(RG, 'predict_rows', real_pred)
    RG._LINGER_CAL = None
