"""Sanity: a clip vs itself is ~100; a different clip scores much lower."""
import os, sys, tempfile, subprocess, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import score

def _tone(path, f, secs=4.0, sr=22050):
    t = np.arange(int(sr*secs))/sr
    y = 0.2*np.sin(2*np.pi*f*t) + 0.05*np.sin(2*np.pi*(f*2)*t)
    # add a beat so alignment isn't undefined
    y += 0.15*((np.sin(2*np.pi*(174/60)*t)>0.9).astype(float))
    sf.write(path, y.astype(np.float32), sr)

def test_identity_and_mismatch():
    d = tempfile.mkdtemp(prefix='protrans_test_')
    a = os.path.join(d,'a.wav'); b = os.path.join(d,'b.wav')
    _tone(a, 110); _tone(b, 330)
    same = score.score(a, a, use_demucs=False, cache=d)
    diff = score.score(a, b, use_demucs=False, cache=d)
    assert same['score'] >= 90, same
    assert diff['score'] <= 70, diff
    assert same['score'] - diff['score'] >= 20, (same['score'], diff['score'])

if __name__ == '__main__':
    test_identity_and_mismatch()
    print('ok')
