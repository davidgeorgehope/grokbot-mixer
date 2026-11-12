"""Unit tests for the diagnostic-only spectral collision / continuity scorer.

These test the scorer itself on synthetic signals. They must never fail a mix
build and they do not change any existing gate or rules.json default.
"""
import os, sys, json
import numpy as np
ROOT = '/workspace/mixes'
sys.path.insert(0, os.path.join(ROOT, 'src2'))
import spectral_score as S

SR = S.SR
BAR = 4 * 60 / 174


def _tone(freq, n, amp=1.0, sr=SR):
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def _noise(n, rng, amp=0.05):
    return amp * rng.standard_normal(n)


def _fade(n, start, end, incoming=True):
    """Equal-power fade of length n, rising if incoming else falling, over [start, end) samples."""
    x = np.zeros(n)
    span = max(end - start, 1)
    t = np.clip((np.arange(n) - start) / span, 0.0, 1.0)
    x[:] = np.sin(0.5 * np.pi * t) if incoming else np.cos(0.5 * np.pi * t)
    return x


def _pair(a, b, start_s, end_s, **kw):
    return S.score_decks(a, b, sr=SR, bar_s=BAR, start_s=start_s, end_s=end_s,
                         already_gained=True, scales=dict(s_col=0.02, s_cty=0.30, source='test'),
                         **kw)


def test_double_bass_collides_more_than_a_bass_swap():
    """Both decks sitting on the same low band should beat a clean bass handoff."""
    rng = np.random.default_rng(0)
    n = int(16 * BAR * SR)
    swap0, swap1 = int(6 * BAR * SR), int(10 * BAR * SR)
    bass_a = _tone(55, n, 1.0) + _tone(80, n, 0.5)
    bass_b = _tone(60, n, 1.0) + _tone(90, n, 0.5)
    mid_a = _tone(1200, n, 0.15)
    mid_b = _tone(1800, n, 0.15)
    # clean swap: A's lows leave as B's lows arrive; mids stay light
    ga, gb = _fade(n, swap0, swap1, False), _fade(n, swap0, swap1, True)
    clean_a = (bass_a * ga + mid_a * (0.3 + 0.7 * ga)) + _noise(n, rng, 0.01)
    clean_b = (bass_b * gb + mid_b * (0.3 + 0.7 * gb)) + _noise(n, rng, 0.01)
    # crash: both lows stay at unity the whole blend
    crash_a = bass_a + mid_a + _noise(n, rng, 0.01)
    crash_b = bass_b + mid_b + _noise(n, rng, 0.01)
    t0, t1 = 4 * BAR, 12 * BAR
    good = _pair(clean_a, clean_b, t0, t1, pre_s=4 * BAR, post_s=4 * BAR)
    bad = _pair(crash_a, crash_b, t0, t1, pre_s=4 * BAR, post_s=4 * BAR)
    assert bad['pcol'] > good['pcol'] * 1.5, (bad['pcol'], good['pcol'])
    assert bad['banger_clash_rate'] > good['banger_clash_rate']
    assert bad['Scol'] < good['Scol']


def _tilt_noise(n, cutoff, rng, amp=0.6):
    """White noise through a 1-pole lowpass, so two nearby cutoffs have related spectra."""
    x = rng.standard_normal(n).astype(np.float64)
    rc = 1.0 / (2 * np.pi * cutoff)
    a = 1.0 / (rc * SR + 1.0)
    y = np.zeros(n)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    y /= (np.sqrt(np.mean(y ** 2)) + 1e-12)
    return amp * y


def test_hard_cut_is_less_continuous_than_a_glide():
    """A lurch between two related tilts should cost more than a slow crossfade of the same pair."""
    rng = np.random.default_rng(1)
    n = int(16 * BAR * SR)
    cut = n // 2
    dark = _tilt_noise(n, 400, rng, 0.8)
    bright = _tilt_noise(n, 5000, np.random.default_rng(11), 0.8)
    fade0, fade1 = int(4 * BAR * SR), int(12 * BAR * SR)
    glide_a, glide_b = dark * _fade(n, fade0, fade1, False), bright * _fade(n, fade0, fade1, True)
    cut_a, cut_b = dark.copy(), bright.copy()
    cut_a[cut:] = 0
    cut_b[:cut] = 0
    t0, t1 = 4 * BAR, 12 * BAR
    glide = _pair(glide_a, glide_b, t0, t1, pre_s=4 * BAR, post_s=4 * BAR)
    hard = _pair(cut_a, cut_b, t0, t1, pre_s=4 * BAR, post_s=4 * BAR)
    assert hard['pcty'] > glide['pcty'], (hard['pcty'], glide['pcty'], hard['continuity_fallback'], glide['continuity_fallback'])
    assert hard['Scty'] < glide['Scty']


def test_continuity_penalty_is_low_when_the_master_tracks_the_template():
    """Direct check of eq. 22: a master that follows u* beats one that jumps."""
    n_fr, n_b = 80, len(S.BAND_EDGES_24) - 1
    uA, uB = np.linspace(-2, 1, n_b), np.linspace(1, -2, n_b)
    alpha = np.linspace(0, 1, n_fr)
    log_follow = (1 - alpha)[:, None] * uA + alpha[:, None] * uB
    log_jump = np.where(alpha[:, None] < 0.5, uA, uB)
    nu = S.band_weights(S.BAND_EDGES_24, 'continuity')
    p_follow, _ = S.continuity_penalty(log_follow, uA, uB, nu)
    p_jump, _ = S.continuity_penalty(log_jump, uA, uB, nu)
    assert p_follow < 1e-9
    assert p_jump > 0.2 and p_jump > 20 * p_follow


def test_collision_monotonic_in_shared_occupancy():
    """Manabe proposition 2: raising min(qA, qB) must not decrease pcol."""
    n_fr, n_b = 40, len(S.BAND_EDGES_24) - 1
    rA = np.full((n_fr, n_b), 0.5)
    rB = np.full((n_fr, n_b), 0.5)
    qA = np.full((n_fr, n_b), 1.0 / n_b)
    qB = qA.copy()
    omega = S.band_weights(S.BAND_EDGES_24, 'collision')
    p0, _ = S.collision_penalty(rA, rB, qA, qB, omega)
    qA2, qB2 = qA.copy(), qB.copy()
    # dump more occupancy into the lowest band on both decks, then renormalize
    qA2[:, 0] += 0.2
    qB2[:, 0] += 0.2
    qA2 = qA2 / qA2.sum(1, keepdims=True)
    qB2 = qB2 / qB2.sum(1, keepdims=True)
    assert np.all(np.minimum(qA2, qB2)[:, 0] > np.minimum(qA, qB)[:, 0])
    p1, _ = S.collision_penalty(rA, rB, qA2, qB2, omega)
    assert p1 >= p0 - 1e-12, (p0, p1)


def test_scores_are_diagnostic_only():
    n = int(4 * BAR * SR)
    a, b = _tone(100, n, 0.4), _tone(1000, n, 0.4)
    res = _pair(a, b, 0.5, 3.0)
    assert res['diagnostic_only'] is True
    assert 'fail' not in res
    for k in ('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate', 'collision_bar', 'continuity_bar'):
        assert k in res, k
    assert 0 <= res['Scol'] <= 1 and 0 <= res['Scty'] <= 1
    assert res['pcol'] >= 0 and res['pcty'] >= 0
    assert len(res['collision_bar']) >= 3


def test_silent_or_tiny_inputs_do_not_raise():
    n = int(2 * BAR * SR)
    z = np.zeros(n)
    res = _pair(z, z, 0.2, 1.5)
    assert res['diagnostic_only'] is True
    assert np.isfinite(res['pcol']) and np.isfinite(res['pcty'])
    tiny = _pair(z + 1e-12, _tone(440, n, 1e-8), 0.2, 1.5)
    assert np.isfinite(tiny['pcol'])


def test_gained_decks_match_fitted_contributions_on_a_summed_master():
    """When C = A+B and the decks already include gain, fitting should recover a similar pcol."""
    rng = np.random.default_rng(2)
    n = int(8 * BAR * SR)
    # overlapping lows (the collision) plus a unique mid on each deck so the fit is identifiable
    a = (_tone(55, n, 0.9) + _tone(1200, n, 0.3)) * _fade(n, int(2 * BAR * SR), int(6 * BAR * SR), False) + _noise(n, rng, 0.01)
    b = (_tone(65, n, 0.9) + _tone(3500, n, 0.3)) * _fade(n, int(2 * BAR * SR), int(6 * BAR * SR), True) + _noise(n, rng, 0.01)
    scales = dict(s_col=0.02, s_cty=0.30, source='test')
    gained = S.score_decks(a, b, sr=SR, bar_s=BAR, start_s=2 * BAR, end_s=6 * BAR,
                           already_gained=True, scales=scales, yc=a + b)
    fitted = S.score_decks(a, b, sr=SR, bar_s=BAR, start_s=2 * BAR, end_s=6 * BAR,
                           already_gained=False, scales=scales, yc=a + b)
    assert np.isfinite(gained['pcol']) and np.isfinite(fitted['pcol'])
    assert gained['pcol'] > 0
    # STFT magnitudes are not strictly additive, so fitted pcol can be lower, but not a different regime
    ratio = fitted['pcol'] / max(gained['pcol'], 1e-9)
    assert 0.15 < ratio < 3.0, (gained['pcol'], fitted['pcol'], ratio)


def test_module_is_not_a_gate():
    src = open(S.__file__).read()
    assert 'NEVER a failing test' in src or 'diagnostic only' in src.lower()
    assert 'rules.json' in src  # it documents that it does not write it
    # the scorer itself never returns a fail flag
    n = int(3 * BAR * SR)
    res = S.score_decks(_tone(80, n), _tone(90, n), start_s=0.3, end_s=2.0,
                        already_gained=True, scales=dict(s_col=0.02, s_cty=0.30, source='test'))
    assert res.get('fail') in (None, False)
    assert res['diagnostic_only'] is True


def test_scales_from_penalties_maps_median_to_target():
    p = [0.01, 0.02, 0.04]
    sc = S.scales_from_penalties(p, p, target=0.70)
    assert abs(np.exp(-0.02 / sc['s_col']) - 0.70) < 1e-9
    compact = S.compact(S.score_decks(_tone(200, int(2 * BAR * SR)), _tone(300, int(2 * BAR * SR)),
                                      start_s=0.2, end_s=1.4, already_gained=True,
                                      scales=dict(s_col=0.02, s_cty=0.30, source='test')))
    dumped = json.dumps(compact)
    assert 'collision_frame' not in dumped
    assert json.loads(dumped)['diagnostic_only'] is True
