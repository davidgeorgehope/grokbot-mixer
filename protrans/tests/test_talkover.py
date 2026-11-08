"""Talkover check: source vocals in the mix pass; an extra voice in neither source flags."""
import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import talkover as T

SR = T.SR
def _sung(f0, secs, phrase=(0, 64), seed=0):
    t = np.arange(int(SR * secs)) / SR
    y = sum(np.sin(2 * np.pi * f0 * k * t * (1 + 0.01 * np.sin(2 * np.pi * 5 * t))) / k for k in range(1, 6))
    gate = ((t >= phrase[0]) & (t < phrase[1])).astype(float)
    return (0.2 * y * gate).astype(np.float32)

def _speech(secs, on, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * secs)) / SR
    from scipy.signal import butter, sosfilt
    n = sosfilt(butter(4, [300, 3000], 'band', fs=SR, output='sos'), rng.standard_normal(len(t)))
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 4.5 * t)) ** 2
    gate = ((t >= on[0]) & (t < on[1])).astype(float)
    return (0.3 * n * env * gate).astype(np.float32)

def test_sung_sources_pass_and_talk_flags():
    secs = 40
    a = _sung(220, secs, (0, 20)); b = _sung(330, secs, (25, 40))
    clean = 0.8 * a + 0.6 * b
    r = T.assess(clean, a, b)
    assert not r['flagged'], r
    talky = clean + _speech(secs, (20, 26))
    r2 = T.assess(talky, a, b)
    assert r2['flagged'], r2
    assert r2['talk_s'] >= 4.0, r2
