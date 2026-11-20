"""SLOWPAIR (2026-11-20 research, off by default): pair-aware hard slowdown / half-time handling.
Pure-function tests; no track audio and no mix_simple."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src2'))
import slowpair as S


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv('SLOWPAIR', raising=False)
    assert S.flag_on() is False
    assert S.flag_on('1') is True and S.flag_on('0') is False and S.flag_on('off') is False


def test_rules_json_does_not_enable_slowpair():
    rules = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'protrans', 'rules.json')))
    assert 'SLOWPAIR' not in rules


def _sec(drops, end):
    return dict(drops=drops, music_end=end, drop1=drops[0][0] if drops else 0)


def test_hard_spans_skip_short_dips_keep_outro_and_long_intro():
    sec = _sec([[48, 112], [144, 192]], 224)
    # 8-bar mid dip, 15-bar in-drop (just under HARD_BARS), 16-bar outro, 24-bar intro, 12-bar ht
    spans = S.hard_spans(
        slow=[[0, 24], [80, 88], [100, 115], [198, 224]],
        ht=[[16, 28]],
        sec=sec,
    )
    kinds = {(s['start'], s['end'], s['kind']) for s in spans}
    assert (198, 224, 'slow') in kinds          # 26-bar outro
    assert (0, 24, 'slow') in kinds             # 24-bar intro
    assert (16, 28, 'ht') in kinds
    assert (80, 88, 'slow') not in kinds        # 8-bar dip
    assert (100, 115, 'slow') not in kinds      # 15-bar in-drop


def test_case_a_outgoing_hard_outro_clash_and_alt_before_slowdown():
    # Ghetto Blaster shape: last drop 144-192, hard outro 198-235, default 208-224 over 48-64.
    a_sec = _sec([[40, 128], [144, 192]], 235)
    a_sp = S.hard_spans(slow=[[198, 235]], ht=[], sec=a_sec)
    b_sp, b_sec = [], _sec([[64, 128]], 224)
    default = ['n', 224, None, 48, 16]
    assert S.window_clash(default, a_sp, b_sp, a_sec)['cases'] == ['A']
    # 192-208 starts 6 bars before the slowdown (the posted Ghetto Blaster fix).
    # Overlap is 10 bars, under CASE_A_COVER 12, and the blend does not start inside.
    early = ['n', 208, None, 48, 16]
    assert S.overlap_bars(192, 208, 198, 235) == 10
    assert S.window_clash(early, a_sp, b_sp, a_sec) is None
    # 176-192 starts before payoff floor (192-8=184) so it is rejected even though it does not clash
    cs = [
        dict(win=default, cost=0.0),
        dict(win=early, cost=2.0),
        dict(win=['n', 192, None, 48, 16], cost=1.0),  # start 176 < 184
    ]
    alt, info = S.pick_alt(cs, default, a_sp, b_sp, a_sec, b_sec)
    assert alt == early and info['reason'] == 'ok'


def test_case_a_short_graze_is_not_a_clash():
    a_sec = _sec([[88, 184], [248, 312]], 327)
    a_sp = S.hard_spans(slow=[[316, 327]], ht=[], sec=a_sec)  # 11-bar outro, not hard
    assert a_sp == []
    win = ['n', 320, None, 48, 16]  # 304-320, 4-bar graze, start is before 316
    forced = [dict(start=316, end=327, kind='slow', labels=['outro'])]
    assert S.window_clash(win, forced, [], a_sec) is None  # start outside, overlap 4 < 12


def test_case_b_hot_outgoing_plus_long_incoming_intro():
    # Outgoing still in its last drop; incoming cued on a 48-bar hard intro.
    a_sec = _sec([[48, 128], [160, 240]], 242)
    b_sec = _sec([[48, 96]], 169)
    b_sp = S.hard_spans(slow=[[2, 48]], ht=[], sec=b_sec)
    default = ['n', 240, None, 32, 16]  # A 224-240 in drop 2; B 32-48 in the intro
    assert S.outgoing_hot(224, 240, a_sec) is True
    assert S.window_clash(default, [], b_sp, a_sec)['cases'] == ['B']
    # same exit, cue after the intro
    later = ['n', 240, None, 48, 16]
    assert S.window_clash(later, [], b_sp, a_sec) is None
    cs = [dict(win=default, cost=0.0), dict(win=later, cost=3.0),
          dict(win=['n', 208, None, 48, 16], cost=1.0)]  # different exit; Case B prefers same exit
    alt, info = S.pick_alt(cs, default, [], b_sp, a_sec, b_sec)
    assert alt == later and info['reason'] == 'ok'


def test_case_b_does_not_fire_when_outgoing_has_left_the_drop():
    # Safe default: outro-over-intro. A 160-176 is after last drop end 160.
    a_sec = _sec([[32, 48], [64, 96], [128, 160]], 180)
    b_sec = _sec([[16, 32], [48, 112]], 223)
    b_sp = S.hard_spans(slow=[[0, 41]], ht=[], sec=b_sec)
    win = ['n', 176, None, 0, 16]
    assert S.outgoing_hot(160, 176, a_sec) is False
    assert S.window_clash(win, [], b_sp, a_sec) is None


def test_rerank_adds_cost_and_nominates_slowpair_family():
    a_sec = _sec([[144, 192]], 235)
    a_sp = S.hard_spans(slow=[[198, 235]], ht=[], sec=a_sec)
    b_sec = _sec([[64, 128]], 224)
    default = ['n', 224, None, 48, 16]
    altw = ['n', 208, None, 48, 16]
    # length_pref=16 makes nat_short the default pick, same as current rules.json
    scored = [(0.01, dict(fam='nat_short', win=default, env={})),
              (0.15, dict(fam='nat_long', win=['n', 224, None, 48, 32], env={}))]
    cs = [dict(win=default, cost=0.0), dict(win=altw, cost=2.0),
          dict(win=['n', 224, None, 48, 32], cost=5.0)]
    # 32-bar family window 192-224 overlaps the outro by 26 bars, so it also clashes
    new, info = S.rerank(scored, cs, a_sp, [], a_sec, b_sec, base_cost=lambda w, f: 0.01)
    assert info['changed'] is True
    assert new[0][1]['fam'] == 'slowpair' and list(new[0][1]['win']) == altw
    assert new[0][0] == 0.01
    nat = [c for c in new if c[1]['fam'] == 'nat_short'][0]
    assert nat[0] == 0.01 + S.COST


def test_payoff_guard_rejects_start_before_last_eight_of_final_drop():
    a_sec = _sec([[144, 192]], 235)
    assert S.payoff_floor(a_sec) == 184


def test_case_b_same_exit_ignores_engine_slack():
    """A later cue at the same exit often loses the 300 outro-over-intro engine bonus."""
    a_sec = _sec([[48, 128], [160, 240]], 242)
    b_sec = _sec([[48, 96]], 169)
    b_sp = S.hard_spans(slow=[[2, 48]], ht=[], sec=b_sec)
    default = ['n', 240, None, 32, 16]
    later = ['n', 240, None, 48, 16]
    cs = [dict(win=default, cost=0.0), dict(win=later, cost=300.0)]
    alt, info = S.pick_alt(cs, default, [], b_sp, a_sec, b_sec, slack=15)
    assert alt == later and info['reason'] == 'ok'


def test_case_a_still_respects_engine_slack():
    a_sec = _sec([[40, 128], [144, 192]], 235)
    a_sp = S.hard_spans(slow=[[198, 235]], ht=[], sec=a_sec)
    b_sec = _sec([[64, 128]], 224)
    default = ['n', 224, None, 48, 16]
    early = ['n', 208, None, 48, 16]
    cs = [dict(win=default, cost=0.0), dict(win=early, cost=300.0)]
    alt, info = S.pick_alt(cs, default, a_sp, [], a_sec, b_sec, slack=15)
    assert alt is None and info['reason'] == 'no_alt'

