"""Hit-preservation property of src2/drumstretch.py.

Synthetic drum hits at known sample times must be copied verbatim after a
±3% stretch, and the output length must be round(n * alpha)."""
import os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src2'))
import drumstretch as D

SR = 44100
BPM = 174.0
BEAT = 60.0 / BPM


def _kick(sr=SR, seed=0):
    """~16 ms click with a unique intra-hit pattern so a smear would fail equality."""
    rng = np.random.default_rng(seed)
    n = int(round(0.016 * sr))
    t = np.arange(n) / sr
    body = (np.sin(2 * np.pi * (70 + 120 * np.exp(-t * 50)) * t) * np.exp(-t * 40)).astype(np.float64)
    click = np.diff(rng.standard_normal(n + 1)) * np.exp(-t * 180) * 0.35
    return (body + click).astype(np.float64)


def _click_id(k, n, sr=SR):
    """Deterministic unique payload inside the hit (still a short transient)."""
    t = np.arange(n) / sr
    return 0.15 * np.sin(2 * np.pi * (900 + 70 * k) * t) * np.exp(-t * 220)


def drums(nbars=4, t0=0.4, sr=SR, stereo=False, seed=1):
    n = int((t0 + nbars * 4 * BEAT + 0.4) * sr)
    y = np.zeros(n, dtype=np.float64)
    # decaying tonal ring between hits, so HPSS has something to stretch
    t = np.arange(n) / sr
    y += 0.04 * np.sin(2 * np.pi * 220 * t) * (1 + 0.3 * np.sin(2 * np.pi * 2 * t))
    onsets = []
    k = 0
    for bar in range(nbars):
        for b in range(4):
            onset = t0 + (bar * 4 + b) * BEAT
            i = int(round(onset * sr))
            hit = _kick(sr, seed=seed + k) + _click_id(k, int(round(0.016 * sr)), sr)
            y[i:i + len(hit)] += hit[:max(0, n - i)]
            onsets.append(i)
            k += 1
    if stereo:
        y = np.column_stack([y, y * 0.85])
    return y, np.asarray(onsets, dtype=int)


@pytest.mark.parametrize('alpha', [174 / 179, 174 / 169])
@pytest.mark.parametrize('stereo', [False, True])
def test_hits_are_sample_exact_and_length_is_correct(alpha, stereo):
    y, onsets = drums(nbars=4, stereo=stereo)
    pre, post = D.HIT_PRE_MS, D.HIT_POST_MS
    out, info = D.stretch(y, SR, alpha, onsets=onsets, pre_ms=pre, post_ms=post)
    n = y.shape[0] if y.ndim == 2 else len(y)
    assert info['nout'] == D.expected_length(n, alpha)
    assert (out.shape[0] if out.ndim == 2 else len(out)) == info['nout']
    y2, _ = D.as_nc(y)
    o2, _ = D.as_nc(out)
    nout = o2.shape[0]
    checked = 0
    for w in info['windows']:
        src = y2[w['in_start']:w['in_end']]
        o0, o1 = w['out_start'], w['out_end']
        s0, s1 = 0, src.shape[0]
        if o0 < 0:
            s0 = -o0
            o0 = 0
        if o1 > nout:
            s1 -= (o1 - nout)
            o1 = nout
        if o1 <= o0 or s1 <= s0:
            continue
        got = o2[o0:o1]
        assert got.shape == src[s0:s1].shape
        np.testing.assert_array_equal(got, src[s0:s1])
        checked += 1
    assert checked >= 12  # 4 bars * 4 beats, maybe a clamp at the edge


def test_alpha_one_is_identity():
    y, onsets = drums(nbars=2)
    out, info = D.stretch(y, SR, 1.0, onsets=onsets)
    assert info.get('identity') is True
    np.testing.assert_array_equal(out, y)
    assert len(out) == len(y)


def test_stretch_tempo_matches_alpha():
    y, onsets = drums(nbars=2)
    a, info_a = D.stretch(y, SR, 174 / 169, onsets=onsets)
    b, info_b = D.stretch_tempo(y, SR, 174, 169, onsets=onsets)
    assert info_a['nout'] == info_b['nout']
    np.testing.assert_allclose(a, b, atol=0, rtol=0)


def test_detect_hits_finds_kicks():
    y, onsets = drums(nbars=3, seed=4)
    got = D.detect_hits(y, SR)
    assert len(got) >= 8
    err_ms = []
    for o in onsets:
        j = np.argmin(np.abs(got - o))
        err_ms.append(abs(got[j] - o) / SR * 1000)
    # most kicks should be found within a few milliseconds
    assert np.median(err_ms) < 3.0
    assert np.percentile(err_ms, 90) < 8.0


def test_no_onsets_still_has_correct_length():
    sr = SR
    t = np.arange(int(1.2 * sr)) / sr
    y = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)
    alpha = 1.03
    out, info = D.stretch(y, sr, alpha, onsets=np.array([], dtype=int))
    assert len(out) == D.expected_length(len(y), alpha)
    assert info['windows'] == []
