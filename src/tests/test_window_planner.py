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
    assert ch['win'][0] == 'n' and ch['win'][1] == 128
    assert ch['win'][3] in (16, 64, 104, 160, 176, 192)  # an incoming drop
    assert ch['fade_env'] == {'SNAP_IN': '1'}
    # prefer a loud later drop over the short first drop when intro is short
    assert ch['win'][3] != 0


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
    on = WP.add_families(fams, [], PE, DEMONS, enabled=True)
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
