"""Half-beat grid detection (2026-11-11 RCA: Nu:Tone 'Shine In' locked onto the off-beat, decks 158 ms apart).
Synthetic drum loops at 174 BPM: the grid check must keep a correct grid, flag one shifted half a beat and move it back;
the render-time deck check must fail two decks half a beat apart and pass aligned ones."""
import os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src2'))
import halfbeat as H

SR = 44100; BEAT = H.BEAT; BAR = H.BAR


def drums(nbars=48, t0=0.5, two_step=True, seed=0, sr=SR):
    """kick on beat 1 (+ the 'and' of 3 when two_step, else beat 3), snare on 2 and 4, closed hats on every 8th"""
    rng = np.random.default_rng(seed); n = int((t0 + nbars * BAR + 1) * sr); y = np.zeros(n, np.float32)
    tk = np.arange(int(0.12 * sr)) / sr
    kick = (np.sin(2 * np.pi * (55 + 90 * np.exp(-tk * 40)) * tk) * np.exp(-tk * 18)).astype(np.float32)
    ts = np.arange(int(0.15 * sr)) / sr
    snare = ((rng.standard_normal(len(ts)) * 0.6 + np.sin(2 * np.pi * 190 * ts)) * np.exp(-ts * 25)).astype(np.float32)
    th = np.arange(int(0.03 * sr)) / sr
    hat = (np.diff(rng.standard_normal(len(th) + 1)) * np.exp(-th * 150) * 0.25).astype(np.float32)
    def put(x, t):
        i = int(round(t * sr)); y[i:i + len(x)] += x[:max(0, n - i)]
    for k in range(nbars):
        b = t0 + k * BAR
        put(kick, b); put(kick, b + (2.5 if two_step else 2) * BEAT)
        put(snare, b + BEAT); put(snare, b + 3 * BEAT)
        for h in range(8):
            put(hat, b + h * BEAT / 2)
    return y


def grid(t0, nbars, shift=0.0):
    downs = t0 + shift + np.arange(nbars) * BAR
    return dict(downs=downs.tolist(), beats=(t0 + shift + np.arange(nbars * 4) * BEAT).tolist(),
                phrases=downs[::8].tolist(), bar=dict(all=[-10.0] * nbars, drums=[-12.0] * nbars))


@pytest.mark.parametrize('two_step', [True, False])
def test_correct_grid_is_kept(two_step):
    y = drums(two_step=two_step); r = H.analyse(y, grid(0.5, 46))
    assert not r['half_off'] and r['margin'] < 0, r


@pytest.mark.parametrize('two_step', [True, False])
def test_off_beat_grid_is_flagged_and_moved_back(two_step):
    y = drums(two_step=two_step); g = grid(0.5, 46, shift=BEAT / 2)   # grid locked onto the off-beat (hats)
    r = H.analyse(y, g)
    assert r['half_off'] and r['margin'] >= H.MARGIN, r
    assert abs(abs(r['shift_sec']) % BEAT - BEAT / 2) < 0.03 and abs(r['shift_sec']) <= BAR / 2, r
    g2, _, new = H.shift_grid(g, y, SR, r)
    err = ((np.array(g2['downs']) - 0.5) / BEAT + 0.5) % 1 - 0.5   # distance to the true beat grid, in beats
    assert np.max(np.abs(err)) * BEAT < 0.006, err
    if two_step:  # kick on 1 only (2-step): the downbeat is unambiguous and must land on it
        ph = (np.array(g2['downs']) - 0.5) / BAR % 1
        assert ((ph < 0.01) | (ph > 0.99)).all(), ph
    assert H.analyse(y, g2)['half_off'] is False


def test_prep_entry_without_bar_features():
    y = drums(); g = grid(0.5, 46, shift=-BEAT / 2); g.pop('bar')
    g2, r = H.fix_grid(g, y, SR)
    assert r['half_off'] and g2['halfbeat']['applied']
    g3, r3 = H.fix_grid(grid(0.5, 46), y, SR); g3.get('halfbeat')
    assert not r3['half_off'] and g3['downs'][0] == pytest.approx(0.5)


def test_fold_does_not_alias_narrow_hits():
    """2026-11-11: point-sampling the flux at 64 bins/bar missed narrow peaks and read a correct grid as half off"""
    y = drums(seed=3); K, S = H.drum_envs(y); g = grid(0.5, 46)
    for nb in (32, 48, 64, 96):
        fS, _ = H.fold(S, np.array(g['downs']), [True] * 46, nb=nb)
        assert int(np.argmax(fS)) in (nb // 4, 3 * nb // 4, nb // 4 - 1, 3 * nb // 4 - 1, nb // 4 + 1, 3 * nb // 4 + 1), (nb, np.argmax(fS))


def _bar_onsets(y, d0, nbars, hop=512):
    import librosa
    L = int(round(BAR * SR)); out = []
    for k in range(nbars):
        j = int(round((d0 + k * BAR) * SR)); seg = y[j:j + L]
        out.append(librosa.onset.onset_strength(y=np.pad(seg, (0, L - len(seg))), sr=SR, hop_length=hop))
    n = min(len(o) for o in out); return np.array([o[:n] for o in out])


def test_render_time_check_fails_half_beat_decks_and_passes_aligned():
    a = drums(two_step=True, seed=1); b = drums(two_step=False, seed=2)
    oa = _bar_onsets(a, 0.5, 40); ob = _bar_onsets(b, 0.5, 40); ob_off = _bar_onsets(b, 0.5 + BEAT / 2, 40)
    w = list(range(4, 36))
    ok = H.verdict(H.deck_lags(oa, ob, w, w)); bad = H.verdict(H.deck_lags(oa, ob_off, w, w))
    assert not ok['fail'] and ok['r0'] > ok['rh'], ok
    assert bad['fail'] and bad['rh'] > bad['r0'] and abs(abs(bad['lag_ms']) - BEAT / 2 * 1000) < 25, bad
    few = H.verdict(H.deck_lags(oa, ob_off, w[:3], w[:3]))
    assert not few['fail']   # < 4 drum bars: no verdict


def _fake_tracks(monkeypatch, tracks):
    """tracks: id -> (audio, grid); blend_check then reads them instead of st/"""
    import json as _j, types
    H._ENV.clear()
    monkeypatch.setattr(H, '_load', lambda b: tracks[b][0])
    monkeypatch.setattr(H, '_drums_on', lambda b: np.ones(len(tracks[b][1]['downs']), bool))
    fr = SR / 512
    def env(b):
        y, g = tracks[b]; n = len(y) // 512
        e = np.maximum(np.diff(np.sqrt((y[:n * 512].reshape(n, 512) ** 2).mean(1)), prepend=0), 0)
        L = int(BAR * fr); return np.array([e[int(d * fr):int(d * fr) + L] for d in g['downs'][:-1]])
    monkeypatch.setitem(sys.modules, 'onsets', types.SimpleNamespace(ensure=env))
    real = open
    def fake_open(p, *a, **k):
        for b, (_, g) in tracks.items():
            if p == f'st/{b}.json':
                import io; return io.StringIO(_j.dumps(g))
        return real(p, *a, **k)
    monkeypatch.setattr('builtins.open', fake_open)


def test_blend_check_drum_phase(monkeypatch):
    """two correctly gridded decks pass; the same incoming deck on a grid half a beat off fails (the Shine In case)"""
    ya, yb = drums(two_step=True, seed=1), drums(two_step=False, seed=2)
    _fake_tracks(monkeypatch, dict(A=(ya, grid(0.5, 46)), B=(yb, grid(0.5, 46)), Boff=(yb, grid(0.5, 46, shift=BEAT / 2))))
    w = list(range(8, 40))
    ok = H.blend_check('A', 'B', w, w); bad = H.blend_check('A', 'Boff', w, w)
    assert not ok['fail'] and abs(ok['dphase_beats']) < 0.1, ok
    assert bad['fail'] and abs(abs(bad['dphase_beats']) - 0.5) < 0.1, bad
    assert not H.blend_check('A', 'Boff', w[:3], w[:3])['fail']   # < 4 drum bars: no verdict
