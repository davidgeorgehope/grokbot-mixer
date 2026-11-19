"""CONSONANCE (2026-11-19 research, off by default): psychoacoustic roughness between overlapping decks
(after Gebhardt, Davies & Seeber 2016). Pure-function tests; no track audio."""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src2'))
import consonance as C


def harm(f0, n=6, roll=0.8):
    return np.array([f0 * (k + 1) for k in range(n)]), np.array([roll ** k for k in range(n)])


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv('CONSONANCE', raising=False)
    assert C.flag_on() is False
    assert C.flag_on('1') is True and C.flag_on('0') is False and C.flag_on('on') is True


def test_rules_json_does_not_enable_consonance():
    rules = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'protrans', 'rules.json')))
    assert not rules.get('CONSONANCE') and 'CONSONANCE_W' not in rules


def test_plomp_levelt_shape():
    f = 440.0
    assert C.pair_dissonance(f, f, 1, 1) == 0                      # unison: no roughness
    d = [float(C.pair_dissonance(f, f + df, 1, 1)) for df in (5, 20, 40, 200)]
    assert d[1] > d[0] and d[2] > d[3]                            # rises then falls (peak ~1/4 critical band)
    assert float(C.pair_dissonance(f, 2 * f, 1, 1)) < 0.01         # octave apart: ~0
    assert math.isclose(float(C.pair_dissonance(f, f + 20, 0.5, 1)), 0.5 * float(C.pair_dissonance(f, f + 20, 1, 1)))


def test_fifth_more_consonant_than_semitone():
    fa, aa = harm(220.0)
    r5 = C.cross_roughness(fa, aa, *harm(220.0 * 1.5))
    r1 = C.cross_roughness(fa, aa, *harm(220.0 * 2 ** (1 / 12)))
    r0 = C.cross_roughness(fa, aa, *harm(220.0))
    assert r0 < r5 < r1


def test_spectrum_peaks_find_sines_in_band_only():
    sr, n = C.SR, C.NFFT
    t = np.arange(n) / sr
    y = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 660 * t) + 2.0 * np.sin(2 * np.pi * 60 * t)  # 60 Hz sub is out of band
    mag = np.abs(np.fft.rfft(y * np.hanning(n)))
    f, a = C.spectrum_peaks(mag, np.fft.rfftfreq(n, 1 / sr))
    assert len(f) >= 2 and abs(f[0] - 440) < 3 and any(abs(x - 660) < 3 for x in f)
    assert all(x >= C.FMIN for x in f)


def test_window_roughness_prefers_consonant_bars_and_follows_fader():
    cons = [harm(220.0)] * 8; diss = [harm(220.0 * 2 ** (1 / 12))] * 8; base = [harm(220.0)] * 8
    rc = C.window_roughness(base, cons, list(range(8)), list(range(8)))
    rd = C.window_roughness(base, diss, list(range(8)), list(range(8)))
    assert rc < rd
    # one deck fully closed -> no cross roughness
    assert C.window_roughness(base, diss, [0, 1], [0, 1], gains=[(1, 0), (1, 0)]) == 0
    assert C.window_roughness(base, diss, [99], [99]) is None


def test_window_bars_layout():
    assert C.window_bars(['n', 100, None, 8, 16]) == (list(range(84, 100)), list(range(8, 24)))
    wa, wb = C.window_bars(['lb', 100, None, 40, 32])
    assert wb[:16] == wb[16:] == list(range(40, 56)) and wa == list(range(68, 100))
    wa, _ = C.window_bars(['la', 100, 84, 0, 16])
    assert wa == list(range(84, 100))


def test_cost_term():
    assert C.cost_term(1.0, 1.0, 0.3) == 0
    assert C.cost_term(2.0, 1.0, 0.3) > 0 > C.cost_term(0.5, 1.0, 0.3)
    assert C.cost_term(None, 1.0, 0.3) == 0 and C.cost_term(1.0, 0, 0.3) == 0 and C.cost_term(2.0, 1.0, 0) == 0


def test_cons_cue_picks_most_consonant_within_pen_slack(monkeypatch):
    nb = 64
    A = [harm(220.0)] * nb
    B = [harm(220.0 * 2 ** (1 / 12))] * 16 + [harm(330.0)] * 16 + [harm(220.0)] * 32  # bars 32+ are unison with A
    monkeypatch.setitem(C._MEM, 'ta', A); monkeypatch.setitem(C._MEM, 'tb', B)
    cs = [dict(win=['n', 48, None, 0, 16], pen=10.0), dict(win=['n', 48, None, 16, 16], pen=12.0),
          dict(win=['n', 48, None, 32, 16], pen=40.0), dict(win=['n', 32, None, 32, 16], pen=0.0)]
    w, r = C.cons_cue(cs, ['n', 48, None, 0, 16], 'ta', 'tb', pen_slack=15)
    assert w == ['n', 48, None, 16, 16] and r < C.win_roughness('ta', 'tb', ['n', 48, None, 0, 16])  # 32 is over slack; e=32 differs
    w2, _ = C.cons_cue(cs, ['n', 48, None, 0, 16], 'ta', 'tb', pen_slack=50)
    assert w2 == ['n', 48, None, 32, 16]
    assert C.cons_cue(cs, ['la', 48, 32, 0, 16], 'ta', 'tb') == (None, None)
