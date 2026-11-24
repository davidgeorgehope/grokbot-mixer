"""official_v2 placement term (2026-11-24 RCA, ukf__10).

v1 compared clip-relative curve shapes after a free +-24 s shift, so where the blend sat in each track was
invisible. These tests pin: identical placement scores 100, a near miss in the same section scores high,
the same fade shape 32 bars away in both tracks scores low, and two cheap tricks (both decks up for the
whole clip, or one deck missing) cannot score well."""
import os, sys, json, tempfile
import numpy as np
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
import score_v2 as S2

def _ev(ea, eb, ga, gb, sa, sb, sec=('breakdown', 'intro')):
    mk = lambda a, b: dict(a=a, b=b, sec_a=sec[0], sec_b=sec[1])
    return dict(entry=mk(ea, eb), gone=mk(ga, gb), swap=mk(sa, sb))

PRO = _ev(129, 21, 149, 41, 143, 35)

def test_identity_is_100():
    assert S2.placement_score(PRO, PRO) == dict(entry=100.0, gone=100.0, swap=100.0)

def test_near_miss_same_section_scores_high():
    p = S2.placement_score(_ev(131, 23, 151, 43, 145, 37), PRO)
    assert min(p.values()) > 80, p

def test_far_placement_scores_low():
    # the ukf__10 default: A's outro (bar 241+) instead of its breakdown (129+)
    far = _ev(241, 33, 262, 54, 247, 39, sec=('outro', 'intro'))
    p = S2.placement_score(far, PRO)
    assert p['gone'] < 30 and p['entry'] < 40, p

def test_monotone_in_distance():
    s = [S2.placement_score(_ev(129 + d, 21 + d, 149 + d, 41 + d, 143 + d, 35 + d), PRO)['gone'] for d in (0, 2, 4, 8, 16, 32)]
    assert all(x >= y for x, y in zip(s, s[1:])), s

def test_missing_events():
    p = S2.placement_score(dict(error='a not located'), PRO)
    assert p == dict(entry=0.0, gone=0.0, swap=0.0)
    assert S2.placement_score(PRO, dict(error='x')) is None   # pro unmeasurable -> caller falls back to v1
    o = _ev(129, 21, None, None, 143, 35)
    assert S2.placement_score(o, PRO) == dict(entry=20.0, gone=20.0, swap=20.0)   # A never leaves: no handoff, no credit
    pro_open = _ev(129, 21, None, None, 143, 35)                                    # pro clip ends with A still up
    p = S2.placement_score(_ev(129, 21, 149, 41, 143, 35), pro_open)
    assert p['entry'] == 100.0 and p['swap'] == 100.0 and p['gone'] == 20.0, p

def test_weights_keep_v1_budget():
    # placement replaces v1's three clip-relative event terms with the same total weight; nothing else moved
    import score
    assert abs(sum(S2.W2.values()) - 1.0) < 1e-9
    assert S2.W2['stem_curves'] == score.W['stem_curves'] and S2.W2['deck_curves'] == score.W['deck_curves'] and S2.W2['beat_align'] == score.W['beat_align']
    assert abs(S2.W2['place_swap'] + S2.W2['place_exit'] + S2.W2['place_entry'] - (score.W['bass_swap'] + score.W['outgoing_cut'] + score.W['blend_length'])) < 1e-9

def test_section_label():
    sec = dict(drops=[[64, 128], [176, 240]])
    assert [S2.section_label(sec, b) for b in (10, 64, 133, 176, 241)] == ['intro', 'drop1', 'breakdown', 'drop2', 'outro']

# ---- real audio (ukf__10 sources, pinned grids). Skipped when the box lacks them. ----
UKF = ('ksVDZt9_0J4', 'Vwb-3pAvOVk')

def _have_audio():
    import paths
    return all(os.path.exists(os.path.join(paths.SRC2, 'st', y + '.wav')) for y in UKF)

def _synth(path, bar_a0, bar_b0, gain_a, gain_b, n_bars=32):
    """two st sources placed at engine bars bar_a0 / bar_b0 at clip t=0, per-bar fader gains"""
    import soundfile as sf, score
    B = score.BAR_SEC; SR = score.SR; n = int(n_bars * B * SR); ys = []
    for yt, b0 in zip(UKF, (bar_a0, bar_b0)):
        wav, grid, _ = S2._st(yt); dn = S2._downs(grid)
        t0 = float(np.interp(b0, np.arange(len(dn)), dn))
        y = score._load(wav, t0=t0, t1=t0 + n / SR + 1)[:n]; ys.append(np.pad(y, (0, n - len(y))))
    t = np.arange(n) / SR / B
    ga = np.interp(t, np.arange(len(gain_a)), gain_a); gb = np.interp(t, np.arange(len(gain_b)), gain_b)
    sf.write(path, (ga * ys[0] + gb * ys[1]).astype(np.float32) * 0.7, SR)

def _blend(k0, k1, n=33):
    k = np.arange(n); return np.clip(1 - (k - k0) / (k1 - k0), 0, 1), np.clip((k - k0) / (k1 - k0), 0, 1)

def test_audio_placement_rewards_position_not_shape():
    if not _have_audio():
        print('skip (no ukf__10 st audio)'); return
    d = tempfile.mkdtemp(prefix='sv2_test_')
    ga, gb = _blend(8, 16)
    ref, near, far, full = (os.path.join(d, f'{k}.wav') for k in ('ref', 'near', 'far', 'full'))
    _synth(ref, 122, 14, ga, gb)          # A's breakdown into B's intro (the ukf__10 pro shape)
    _synth(near, 124, 16, ga, gb)         # same shape, 2 bars later in both tracks
    _synth(far, 122 + 112, 14, ga, gb)    # same shape on A's outro
    _synth(full, 122, 14, np.ones(33), np.ones(33))   # both decks up the whole clip: no transition at all
    cache = os.path.join(d, 'c')
    ev = {k: S2.placement_events(p, *UKF, cache=cache) for k, p in (('ref', ref), ('near', near), ('far', far), ('full', full))}
    m = lambda k: float(np.mean(list(S2.placement_score(ev[k], ev['ref']).values())))
    assert m('ref') == 100.0
    assert m('near') > 75, (m('near'), ev['near'])
    assert m('far') < 45, (m('far'), ev['far'])
    assert m('full') <= 20, (m('full'), ev['full'])
    assert abs(ev['near']['entry']['a'] - ev['ref']['entry']['a'] - 2) <= 1.5, (ev['near']['entry'], ev['ref']['entry'])

if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_') and callable(f):
            f(); print('ok', k)
