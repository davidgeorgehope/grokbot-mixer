"""'early in, cut on the phrase' family (2026-11-11 RCA, Joe Syntax: Dusk To Dawn up at -2..-8 dB for 17 bars, then
Shine In and its bass out within one bar on Dusk To Dawn's phrase) plus the family plumbing around it."""
import os, sys, copy
import numpy as np
import pytest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src2')); sys.path.insert(0, os.path.join(ROOT, 'protrans'))


def _meta(s=16, X=32):
    A = dict(id='fakeA', start_bar=0, full_map=[[k, 'mix'] for k in range(s + X)], auto={'gain': [[s, 1.0], [s + X, 0.0]], 'low': [[s + 8, 1.0], [s + 11, 0.0]], 'high': [[s + 12, 1.0], [s + 14, 0.0]]})
    B = dict(id='fakeB', start_bar=s, full_map=[[k, 'mix'] for k in range(48)], auto={'gain': [[s, 0.0], [s + X, 1.0]], 'low': [[s + 8, 0.0], [s + 11, 1.0]], 'high': [[s + 12, 0.0], [s + 14, 1.0]]})
    return dict(decks=[A, B], trans=[dict(a='fakeA', b='fakeB', start_bar=s, end_bar=s + X, swap_bar=s + 8, bass_swap=[s + 8, s + 11], tech='x')])


@pytest.fixture
def fake_tracks(monkeypatch):
    import engine
    low = np.full(64, -18.0); low[16] = -40.0          # incoming source bar 16 (a 16-bar phrase start) is a low-end dip
    monkeypatch.setitem(engine._cache, 'fakeB', dict(id='fakeB', g={'bar': {'low': low.tolist()}}))
    monkeypatch.setitem(engine._cache, 'fakeA', dict(id='fakeA', g={'bar': {'low': [-18.0] * 64}}))
    yield


def _at(pts, x):
    return float(np.interp(x, [p[0] for p in pts], [p[1] for p in pts]))


def test_cut_lands_on_incoming_phrase_and_skips_quiet_bars(fake_tracks):
    import blend_bench as BB
    M = _meta()
    m = BB.cut_bar(M)
    # >= 16 bars in: mix 32 = incoming bar 16 (quiet, skipped); bar 32 sits at the blend end; so the 8-bar boundary, incoming bar 24
    assert m == 40, m


def test_phrase_cut_shape(fake_tracks):
    import blend_bench as BB
    M = BB.phrase_cut(_meta()); A, B = M['decks']; t = M['trans'][0]; m = t['phrase_cut']['cut_bar']
    gi, gl = 10 ** (BB.PC_IN_DB / 20), 10 ** (BB.PC_LOW_DB / 20)
    assert _at(A['auto']['gain'], m - 0.01) == pytest.approx(1.0) and _at(A['auto']['gain'], 20) == pytest.approx(1.0)
    assert _at(A['auto']['gain'], m + BB.PC_CUT) == pytest.approx(0.0, abs=1e-6)       # outgoing out within the cut bar
    assert _at(A['auto']['low'], m + BB.PC_CUT) == pytest.approx(0.0, abs=1e-6)        # and its bass with it
    assert _at(B['auto']['gain'], 16 + BB.PC_RAMP + 1) == pytest.approx(gi, rel=1e-3)   # incoming up early, near full level
    assert _at(B['auto']['low'], m - 1) == pytest.approx(gl, rel=1e-3)                  # with its lows held down
    assert _at(B['auto']['gain'], m + BB.PC_CUT) == pytest.approx(1.0) and _at(B['auto']['low'], m + BB.PC_CUT) == pytest.approx(1.0)
    assert 'high' not in A['auto'] and 'high' not in B['auto']
    assert t['bass_swap'] == [m, m + BB.PC_CUT] and m - t['start_bar'] >= BB.PC_LEAD
    g = [_at(A['auto']['gain'], m + k / 16) for k in range(17)]
    assert all(x >= y - 1e-9 for x, y in zip(g, g[1:]))                                   # monotonic exit


def test_family_listed_only_for_long_natural_blends():
    import blend_bench as BB
    cs = [dict(win=['n', 240, None, 24, 32], cost=1.0), dict(win=['n', 240, None, 40, 16], cost=2.0)]
    fams = {c['fam']: c for c in BB.families(cs, None)}
    assert fams['phrase_cut']['phrase_cut'] and fams['phrase_cut']['win'] == ['n', 240, None, 24, 32]
    assert 'phrase_cut' not in {c['fam'] for c in BB.families([dict(win=['n', 240, None, 40, 16], cost=2.0)], None)}


def test_family_costs_distinct_and_rules_override():
    import recreate as R
    names = ['nat_long', 'nat_short', 'out_loop', 'in_loop', 'lx_beat', 'cue_early', 'cue_late', 'phrase_cut', 'swap_early', 'swap_late', 'sneak_in']
    costs = [R.family_cost(n) for n in names]
    assert len(set(costs)) == len(costs) and min(costs) == R.family_cost('nat_long')
    assert R.family_cost('phrase_cut', {'family_cost': {'phrase_cut': -1}}) == -1


def test_family_env_wins_over_rules_env():
    import recreate as R
    env = R.apply_rules({'SWAP_POS': 0.21, 'FADE': 'lin'})
    pick = dict(env={'SWAP_POS': '0.6'})
    merged = {**env, **dict(pick.get('env') or {})}   # the order recreate() uses
    assert merged['SWAP_POS'] == '0.6' and merged['FADE'] == 'lin'
    src = open(R.__file__).read()
    assert "pick['env'] = {**env, **dict(pick.get('env') or {})}" in src


def test_structure_window_parse_accepts_loop_forms():
    import structure as ST
    assert ST.parse_window(['la', 224, 208, 64, 16]) == ('la', 224, 208, 64, 16)
    assert ST.parse_window(['la', [224, 208], 64, 16]) == ('la', 224, 208, 64, 16)
    assert ST.parse_window(['lb', 240, None, ('loopB', 40), 16]) == ('lb', 240, None, 40, 16)
    lab = ['intro'] * 32 + ['drop'] * 64
    ST.window_landmarks(['la', [224, 208], 64, 16], lab * 3, lab * 3)   # used to raise TypeError (int(list))


def test_sections_drop_from_structure_when_they_disagree():
    import sections
    n = 160; drums = np.full(n, -12.0); bass = np.full(n, -14.0); low = np.full(n, -14.0)
    drums[:56] = -30; bass[:56] = -40; low[:56] = -40
    bass[56:64] = -26; bass[62:64] = -40   # the bass stem only arrives at 64 (sections reads the <150 Hz band, which is loud from 56)
    g = dict(bar=dict(all=(drums + 2).tolist(), low=low.tolist(), drums=drums.tolist(), bass=bass.tolist()))
    s = sections.detect(g); r = sections.reconcile(s, g)
    assert s['drop1'] == 56 and r['drop1'] == 64, (s, r)
    assert r['drop1_src'] == 'structure.py' and r['drop1_sections'] == s['drop1'] and r['drop1'] < r['outro_start']
