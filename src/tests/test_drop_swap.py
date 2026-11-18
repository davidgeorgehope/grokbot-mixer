"""DROP_SWAP (2026-11-18 research, off by default): re-cue a thin-intro outro-over-intro window so the
incoming drop lands on the bass handoff. Pure-function tests; no audio."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src2'))
import drop_swap as DS


def _intro_track(intro=48, n=200, thin=-28.0, full=0.0):
    lo = np.full(n, full)
    lo[:intro] = thin
    return lo


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv('DROP_SWAP', raising=False)
    assert DS.flag_on() is False
    assert DS.flag_on('1') is True and DS.flag_on('0') is False


def test_rules_json_does_not_enable_drop_swap():
    import json
    rules = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'protrans', 'rules.json')))
    assert not rules.get('DROP_SWAP')


def test_drop_bar_phrase_after_handoff_start():
    assert DS.drop_bar(7.0, 4, 16) == 8      # handoff 5..9 -> drop on bar 8
    assert DS.drop_bar(6.5, 4, 16) == 8
    assert DS.drop_bar(2.0, 4, 16) == 4      # never on bar 0
    assert DS.drop_bar(15.0, 4, 16) == 12    # never in the last phrase
    assert DS.drop_bar(23.0, 4, 32) == 24


def test_recue_thin_intro_lands_drop_on_swap():
    lo = _intro_track()
    assert DS.recue(lo, 48, 16, 32, 7.0, 4, len(lo)) == 40


def test_recue_skips_when_incoming_has_bass():
    lo = _intro_track(thin=-3.0)
    assert DS.recue(lo, 48, 16, 32, 7.0, 4, len(lo)) is None


def test_recue_skips_partial_thin_window():
    lo = _intro_track()
    lo[40] = 0.0   # one body-level bar inside the default overlap -> gate off (no loosening)
    assert DS.recue(lo, 48, 16, 32, 7.0, 4, len(lo)) is None


def test_recue_skips_misdetected_drop():
    lo = _intro_track(intro=60)  # bass really starts at 60, sections said 48
    assert DS.recue(lo, 48, 16, 32, 7.0, 4, len(lo)) is None


def test_recue_bounds():
    lo = _intro_track(intro=4)
    assert DS.recue(lo, 4, 16, -12, 7.0, 4, len(lo)) is None  # would start before bar 0
    assert DS.recue(None or lo, None, 16, 32, 7.0, 4, len(lo)) is None
