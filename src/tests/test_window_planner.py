"""window_planner (src2/window_planner.py, 2026-11-15 research, off by default):
nominate mid-track blend windows from both decks' sections and choose per
pair from track features. Not a blanket rule. GAP_DB and X1 are never loosened.
"""
import os, sys, json, copy
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src2'))
sys.path.insert(0, os.path.join(ROOT, 'protrans'))
import window_planner as WP
import bassgap
import recreate as R


# Prime Expansion -> Demons (11-14 target): default outro-intro has a fat
# bass hole; drop1_end is PE 96-112 over Demons 48-64, the window the listener liked.
PE = dict(n_bars=191, intro_end=32, drop1=32, breakdown=112, drop2=136,
          outro_start=168, music_end=185, drops=[[32, 112], [136, 184]])
DEMONS = dict(n_bars=219, intro_end=48, drop1=48, breakdown=112, drop2=144,
              outro_start=192, music_end=211, drops=[[48, 112], [144, 208]])

# Cinnamon -> Together (11-15 target): short incoming intro, outgoing
# breakdown into an incoming drop, SNAP_IN fade.
CIN = dict(n_bars=215, intro_end=48, drop1=48, breakdown=112, drop2=128,
           outro_start=184, music_end=205, drops=[[48, 112], [128, 192]])
TOG = dict(n_bars=263, intro_end=16, drop1=16, breakdown=48, drop2=64,
           outro_start=240, music_end=256, drops=[[16, 48], [64, 144], [160, 240]])


def _lows_pe_demons():
    lo_a = np.full(200, -17.5)
    lo_a[112:136] = -40.0  # breakdown
    lo_a[184:] = -40.0
    lo_b = np.full(220, -19.0)
    lo_b[:48] = -33.0  # intro thin
    lo_b[112:144] = -40.0
    return lo_a, lo_b


def _lows_cin_tog():
    lo_a = np.full(215, -17.0)
    lo_a[112:128] = -42.0  # short breakdown
    lo_a[200:] = -35.0     # keep the late second drop at body so the default
                           # outro-intro window (176-192 over a thin intro)
                           # still has a majority engine hole, as on the real pair
    lo_b = np.full(263, -19.0)
    lo_b[:16] = -40.0  # short thin intro
    lo_b[48:64] = -36.0
    return lo_a, lo_b


def test_gap_db_is_the_pro_p95_and_not_loosened():
    assert bassgap.GAP_DB == 9.84
    assert WP.GAP_DB == bassgap.GAP_DB
    assert WP.hole_min(16) == 8
    assert WP.hole_min(32) == 16


def test_section_at_boundaries():
    sec, info = WP.section_at(PE, 96)
    assert sec == 'drop' and info['hit'] == 'drop1' and info['near_drop1_end']
    # exclusive end of drop1 is the breakdown, so a window *ending* at 112
    # still plays drop1 bars 96-111
    sec, info = WP.section_at(PE, 112)
    assert sec == 'breakdown'
    sec, info = WP.section_at(PE, 10)
    assert sec == 'intro'
    # drop2 runs through 184, even though outro_start is 168; a bar in that
    # run is still a drop. The outro starts after the last drop.
    sec, info = WP.section_at(PE, 170)
    assert sec == 'drop' and info['hit'] == 'drop2'
    sec, info = WP.section_at(PE, 184)
    assert sec == 'outro' or info['in_outro']
    sec, info = WP.section_at(TOG, 191)
    assert sec == 'drop' and info['hit'] == 'drop3'


def test_nominates_drop1_end_and_breakdown_drop_and_lifts_bar80_cap():
    c19 = WP.nominate(PE, DEMONS, X=16)
    types = {c['type'] for c in c19}
    assert 'outro_intro' in types and 'drop1_end' in types and 'breakdown_drop' in types
    wins = {c['type']: [] for c in c19}
    for c in c19:
        wins[c['type']].append(c['win'])
    assert ['n', 112, None, 48, 16] in wins['drop1_end']
    # Together's third drop starts at 160, past the usual incoming bar-80 cap
    c25 = WP.nominate(CIN, TOG, X=16)
    ibs = [c['win'][3] for c in c25 if c['type'] == 'breakdown_drop']
    assert any(ib >= 160 for ib in ibs), ibs
    assert any(c['win'] == ['n', 128, None, 64, 16] for c in c25 if c['type'] == 'breakdown_drop')
    # +32 body phrase of drop 3 (pro cues Together at bar 191)
    assert any(c['win'] == ['n', 128, None, 192, 16] for c in c25 if c['type'] == 'breakdown_drop')


def test_hole_bars_matches_recreate_and_ignores_shared_breakdown():
    lo_a, lo_b = _lows_pe_demons()
    w_bad = ['n', 176, None, 32, 16]
    w_fix = ['n', 112, None, 48, 16]
    assert WP.hole_bars(w_bad, lo_a, lo_b) > 8
    assert WP.hole_bars(w_fix, lo_a, lo_b) <= 1
    assert WP.hole_bars(w_bad, lo_a, lo_b) == R.incoming_hole_bars(w_bad, lo_a, lo_b, WP.GAP_DB)
    # both already thin: not an engine hole
    lo_a2 = lo_a.copy(); lo_a2[160:176] = -40.0
    assert WP.hole_bars(w_bad, lo_a2, lo_b) <= 1


def test_selects_drop1_end_on_the_11_14_shape():
    lo_a, lo_b = _lows_pe_demons()
    default = ['n', 176, None, 32, 16]
    ch = WP.select(default, PE, DEMONS, lo_a, lo_b)
    assert ch['type'] == 'drop1_end'
    assert ch['win'] == ['n', 112, None, 48, 16]
    assert ch['fade_env'] == {}
    assert ch['default_holes'] > WP.hole_min(16)


def test_selects_breakdown_drop_with_snap_in_on_the_11_15_shape():
    lo_a, lo_b = _lows_cin_tog()
    default = ['n', 192, None, 0, 16]
    ch = WP.select(default, CIN, TOG, lo_a, lo_b)
    assert ch['type'] == 'breakdown_drop'
    assert ch['win'] == ['n', 128, None, 192, 16]
    assert ch['fade_env'] == {'SNAP_IN': '1', 'SNAP_IN_HOLD': '16'}
    # last of 3 drops, 32 bars into the body (pro is bar 191)
    assert ch['features']['in_hit'] == 'drop3'


def test_stays_on_a_clean_default_and_on_a_mild_hole():
    # 11-14 family of "already clean" (ukf__08): both sides thin at the outro
    lo_a, lo_b = _lows_pe_demons()
    lo_a_clean = lo_a.copy(); lo_a_clean[160:185] = -40.0
    default = ['n', 176, None, 32, 16]
    ch = WP.select(default, PE, DEMONS, lo_a_clean, lo_b)
    assert ch['type'] == 'outro_intro' and ch['win'] == default
    assert ch['fade_env'] == {}
    assert ch['reason'] == 'default_clean'
    # mild hole (5 bars, joe__11 shape): not a majority, do not switch
    lo_a2, lo_b2 = _lows_pe_demons()
    # only the first 5 incoming bars of the default window are thin,
    # the rest of the 16 are at body — but default is bars 32-48 of Demons,
    # which are all intro in this fixture. Build a milder incoming intro.
    lo_b2[:48] = -19.0
    lo_b2[32:37] = -33.0
    ch2 = WP.select(default, PE, DEMONS, lo_a2, lo_b2)
    assert ch2['default_holes'] <= WP.hole_min(16)
    assert ch2['type'] == 'outro_intro'


def test_off_by_default_and_add_families_respects_the_flag():
    assert not WP.flag_on(None) and not WP.flag_on(0) and WP.flag_on(1)
    rules = json.load(open(os.path.join(ROOT, 'protrans', 'rules.json')))
    assert not WP.flag_on(rules.get('window_planner'))
    assert 'window_planner' not in rules
    assert 'WINDOW_PLANNER' not in rules
    fams = [dict(fam='nat_short', win=['n', 176, None, 32, 16], env={})]
    off = WP.add_families(fams, [], PE, DEMONS, enabled=False)
    assert off == fams
    on = WP.add_families(fams, None, PE, DEMONS, enabled=True)
    names = [c['fam'] for c in on]
    assert 'nat_short' in names
    assert WP.FAM_DROP1 in names and WP.FAM_BREAKDOWN in names


def test_engine_cands_include_mid_track_before_half_track_cutoff():
    # pair_cands usually starts e at emin ~ half the track; PE drop1_end is 112
    got = WP.engine_cands(PE, DEMONS, 16, e_max=176, ia=0)
    assert ('n', 112, 48) in got
    got25 = WP.engine_cands(CIN, TOG, 16, e_max=200, ia=0)
    assert any(e == 128 and ib >= 64 for _, e, ib in got25)


def test_classify_pro_shape():
    assert WP.classify_pro_shape('breakdown>drop') == 'breakdown_drop'
    assert WP.classify_pro_shape('drop>intro') == 'outro_intro'
    assert WP.classify_pro_shape('drop>drop', pair_id='hybrid_minds_ukf__19') == 'drop1_end'
    assert WP.classify_pro_shape('drop>drop') == 'drop_drop'


def test_hint_family_and_snap_in_still_off_in_rules():
    rules = json.load(open(os.path.join(ROOT, 'protrans', 'rules.json')))
    assert not R._flag_on(rules.get('hint_family'))
    assert 'SNAP_IN' not in rules


def test_bass_cover_fallback_is_not_used():
    """Thin-intro stays no longer get BASS_COVER. That fallback pulled
    held-out under the 34.05 floor and was dropped. The 6 dB thin line
    itself is unchanged.
    """
    import fade_long as FL
    sa = dict(n_bars=120, intro_end=16, drop1=16, breakdown=None, drop2=None,
              outro_start=88, music_end=104, drops=[[16, 104]])
    sb = dict(n_bars=96, intro_end=48, drop1=48, breakdown=None, drop2=None,
              outro_start=80, music_end=96, drops=[[48, 96]])
    lo_a = np.full(120, -17.5)
    lo_b = np.full(96, -19.0)
    lo_b[:48] = -33.0  # fully thin intro
    default = ['n', 96, None, 32, 16]
    assert WP.incoming_all_thin(default, lo_b, db=6.0)
    assert FL.incoming_no_bass(lo_b, list(range(32, 48)), 16, db=6.0)
    assert WP.hole_bars(default, lo_a, lo_b) > WP.hole_min(16)
    ch = WP.select(default, sa, sb, lo_a, lo_b)
    assert ch['type'] == 'outro_intro' and ch['win'] == default
    assert 'BASS_COVER' not in (ch.get('fade_env') or {})
    assert not ch.get('bass_cover')
    lo_pe, lo_de = _lows_pe_demons()
    ch3 = WP.select(['n', 176, None, 32, 16], PE, DEMONS, lo_pe, lo_de)
    assert ch3['type'] == 'drop1_end'
    assert 'BASS_COVER' not in (ch3.get('fade_env') or {})


def test_bass_cover_still_off_in_rules_and_thin_line_unloosened():
    rules = json.load(open(os.path.join(ROOT, 'protrans', 'rules.json')))
    assert 'BASS_COVER' not in rules and 'BASS_COVER_DB' not in rules
    import fade_long as FL
    src = open(os.path.join(ROOT, 'src2', 'fade_long.py')).read()
    assert 'db=6.0' in src or 'db=6' in src
    # incoming_all_thin default is the same 6 dB line
    import inspect
    assert WP.incoming_all_thin.__defaults__ == (6.0,)


def test_apply_choice_stay_keeps_default():
    """A mid-track family that only won on hint cost must not replace a stay.
    sneak_in / swap_* share the default window and must not win the stay either.
    """
    default = ['n', 96, None, 0, 32]
    mid = ['n', 88, None, 24, 16]
    scored = [
        (0.0, dict(fam='sneak_in', win=default, env={})),
        (0.1, dict(fam=WP.FAM_DROP1, win=mid, env={})),
        (0.4, dict(fam='nat_long', win=default, env={})),
    ]
    stay = dict(type='outro_intro', win=default, fade_env={}, reason='default_clean')
    pick = WP.apply_choice(scored, stay, default)
    assert pick['fam'] == 'nat_long' and pick['win'] == default
    mid_ch = dict(type='drop1_end', win=mid, fade_env={}, reason='drop1_end')
    pick2 = WP.apply_choice(scored, mid_ch, default)
    assert pick2['win'] == mid and pick2['planner']['type'] == 'drop1_end'
    # chosen mid-track window missing from the shortlist -> default
    other = dict(type='drop1_end', win=['n', 112, None, 48, 16], fade_env={}, reason='drop1_end')
    pick3 = WP.apply_choice(scored, other, default)
    assert pick3['win'] == default


def test_add_families_skips_windows_not_in_cs():
    fams = [dict(fam='nat_short', win=['n', 176, None, 32, 16], env={})]
    # empty cs: nothing extra is legal
    on = WP.add_families(fams, [], PE, DEMONS, enabled=True)
    assert [c['fam'] for c in on] == ['nat_short']
    # a legal drop1_end in cs is added
    cs = [dict(win=['n', 112, None, 48, 16], cost=10)]
    on2 = WP.add_families(fams, cs, PE, DEMONS, enabled=True)
    wins = [c['win'] for c in on2]
    assert ['n', 112, None, 48, 16] in wins


def test_apply_rules_maps_window_planner_flag():
    """Cohort trials set rules['window_planner']; mix_simple reads WINDOW_PLANNER."""
    env = R.apply_rules({'window_planner': 1, 'FADE': 'long'})
    assert str(env.get('WINDOW_PLANNER')) not in ('', '0', 'None', 'None')
    assert R._flag_on(env.get('WINDOW_PLANNER'))
    env0 = R.apply_rules({'FADE': 'long'})
    assert not R._flag_on(env0.get('WINDOW_PLANNER'))
    # later-drop body cue must be a legal engine cand (past the bar-80 cap)
    got = WP.engine_cands(CIN, TOG, 16, e_max=200, ia=0)
    assert ('n', 128, 192) in got


def test_snap_in_hold_only_on_three_plus_drops():
    """SNAP_IN_HOLD is only for breakdown_drop when the incoming has 3+ drops
    and the outgoing still has runway. Other breakdowns get SNAP_IN alone.
    """
    feat3 = dict(n_in_drops=3, out_left=77, to_outro=56)
    assert WP.fade_env('breakdown_drop', feat3) == {'SNAP_IN': '1', 'SNAP_IN_HOLD': '16'}
    feat1 = dict(n_in_drops=1, out_left=77, to_outro=56)
    assert WP.fade_env('breakdown_drop', feat1) == {'SNAP_IN': '1'}
    feat2 = dict(n_in_drops=2, out_left=77, to_outro=56)
    assert WP.fade_env('breakdown_drop', feat2) == {'SNAP_IN': '1'}
    short = dict(n_in_drops=3, out_left=10, to_outro=10)
    assert WP.fade_env('breakdown_drop', short) == {'SNAP_IN': '1'}
    assert WP.fade_env('drop1_end', feat3) == {}


def test_apply_choice_skips_windows_only_legal_via_alias():
    """drop1_end / 2-drop windows that only entered cs past emin or bar 80
    stay on the default (v1 behaviour). The 3+ last-drop cue may use them.
    """
    default = ['n', 320, None, 48, 16]
    mid = ['n', 184, None, 64, 16]
    scored = [
        (0.4, dict(fam='nat_short', win=default, env={})),
        (0.1, dict(fam=WP.FAM_DROP1, win=mid, env={})),
    ]
    ch = dict(type='drop1_end', win=mid, fade_env={}, reason='drop1_end',
              features=dict(n_in_drops=2))
    pick = WP.apply_choice(scored, ch, default, base_wins={tuple(default)})
    assert pick['fam'] == 'nat_short' and pick['win'] == default
    # in the default shortlist: still applied
    pick_ok = WP.apply_choice(scored, ch, default, base_wins={tuple(default), tuple(mid)})
    assert pick_ok['win'] == mid
    # ukf__25 last-drop body cue may sit past bar 80
    mid25 = ['n', 128, None, 192, 16]
    default25 = ['n', 192, None, 0, 16]
    scored25 = [
        (0.4, dict(fam='nat_short', win=default25, env={})),
        (0.01, dict(fam=WP.FAM_BREAKDOWN, win=mid25, env={'SNAP_IN': '1'})),
    ]
    ch25 = dict(type='breakdown_drop', win=mid25,
                fade_env={'SNAP_IN': '1', 'SNAP_IN_HOLD': '16'},
                reason='short_intro_bd',
                features=dict(n_in_drops=3, in_drop=3))
    assert WP.is_extended_ok(ch25)
    pick25 = WP.apply_choice(scored25, ch25, default25, base_wins={tuple(default25)})
    assert pick25['win'] == mid25
