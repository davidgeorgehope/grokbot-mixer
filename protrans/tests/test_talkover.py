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

def test_thresholds_unchanged():
    assert T.TALK_MIN_S == 4.0
    assert T.TALK_MIN_FRAC == 0.15


def test_separate_budget_allows_work_under_the_cap():
    assert T._separate_budget(1, 1.0, dur_s=64.0, n_limit=32, t_limit=900) == 1.0
    assert T._separate_budget(32, 900.0, dur_s=64.0, n_limit=32, t_limit=900) == 900.0


def test_separate_budget_raises_on_too_many_chunks():
    try:
        T._separate_budget(33, 1.0, dur_s=64.0, n_limit=32, t_limit=900)
    except T.TalkoverSeparateError as e:
        assert 'talkover_separate_budget' in str(e)
        assert 'chunks=33' in str(e)
    else:
        raise AssertionError('expected TalkoverSeparateError')


def test_separate_budget_raises_on_timeout():
    try:
        T._separate_budget(3, 901.0, dur_s=64.0, n_limit=32, t_limit=900)
    except T.TalkoverSeparateError as e:
        assert 'talkover_separate_timeout' in str(e)
        assert 'after 901s' in str(e)
    else:
        raise AssertionError('expected TalkoverSeparateError')


def test_check_clip_rejects_on_separate_timeout(monkeypatch, tmp_path):
    pro = tmp_path / 'clip' / 'pro.wav'
    pro.parent.mkdir()
    pro.write_bytes(b'')
    monkeypatch.setattr(T, 'check_clip', T.check_clip)  # keep real function
    import score
    monkeypatch.setattr(score, '_load', lambda *a, **k: np.zeros(44100, np.float32))
    monkeypatch.setattr(score, 'locate_offset', lambda *a, **k: 0.0)
    def boom(*a, **k):
        raise T.TalkoverSeparateError('talkover_separate_timeout after 900s chunks=3 audio=64.0s')
    monkeypatch.setattr(T, '_vocals', boom)
    r = T.check_clip(str(pro), str(tmp_path / 'a.m4a'), str(tmp_path / 'b.m4a'))
    assert r.get('flagged') is False
    assert 'talkover_separate_timeout' in r.get('error', '')


def test_wait_or_kill_terminates_a_stuck_worker():
    import subprocess, sys
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])
    try:
        T._wait_or_kill(proc, 0.4, label='test', dur_s=64.0)
    except T.TalkoverSeparateError as e:
        assert 'talkover_separate_timeout' in str(e)
    else:
        raise AssertionError('expected TalkoverSeparateError')
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait(timeout=2)
    assert proc.poll() is not None


def test_stem_worker_is_standalone_script():
    path = T._stem_worker_path()
    assert path.endswith('talkover_stem_worker.py')
    assert os.path.isfile(path)
    src = open(path).read()
    assert "if __name__ == '__main__'" in src
    assert 'T._IN_VOCALS_WORKER = True' in src


def test_vocals_rejects_overlong_audio():
    y = np.zeros(int(T.TALK_MAX_AUDIO_S * 44100) + 44100, np.float32)
    try:
        T._vocals(y, label='long')
    except T.TalkoverSeparateError as e:
        assert 'talkover_input_too_long' in str(e)
    else:
        raise AssertionError('expected TalkoverSeparateError')
