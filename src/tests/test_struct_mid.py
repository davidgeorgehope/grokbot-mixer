"""STRUCT_MID detector: tight post-drop half-time pocket on outgoing tracks.
Pro labels are not inputs. Exit/cue numbers elsewhere are errors (lower is better)."""
import os, sys
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
sys.path.insert(0, '/workspace/mixes/src2')
import struct_mid as SM

def test_should_fire_defaults():
    # LOMO default: gap >= 16 and at least 24 bars of half-time in the gap.
    assert SM.should_fire(32, 31) is True    # S.P.Y
    assert SM.should_fire(48, 24) is True    # havey__00
    assert SM.should_fire(32, 25) is True    # outer__15
    assert SM.should_fire(16, 15) is False   # outer__24: short HT pocket, mid-track but loose gate
    assert SM.should_fire(16, 0) is False    # yolowich__09: mid-track, no HT in the gap
    assert SM.should_fire(16, 16) is False   # typical false fire on the loose 16-or-8 gate
    assert SM.should_fire(32, 0) is False
    assert SM.should_fire(0, 0) is False

def test_spy_seconds_to_midnight_pocket():
    p = SM.pocket('u6cggHmZEAs')
    assert p and p['fire']
    assert p['gap'] == (128, 160)
    assert p['sd_in_gap'] >= 24
    assert 128 in p['anchors'] and 160 in p['anchors']
    assert SM.mid_exit('u6cggHmZEAs', 128)
    assert SM.mid_exit('u6cggHmZEAs', 160)
    assert not SM.mid_exit('u6cggHmZEAs', 256)

def test_no_pro_labels_imported():
    src = open(SM.__file__).read()
    for banned in ('protrans_decisions', 'out_bar_at_entry', 'outgoing_bar', 'pro_out'):
        assert banned not in src
