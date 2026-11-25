"""Tests for picker_1125_followup.py: section-aware features, Bayes-mixture risk gate, no rules.json mutation."""
import json, os, sys
import numpy as np

PT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REP = os.path.join(PT, 'replica')
sys.path.insert(0, REP)
sys.path.insert(0, PT)

import picker_1125_followup as F


def _sample_row():
    sa = dict(
        n_bars=220, music_end=220, intro_end=32, intro_len=32, drop1=32,
        breakdown=112, drop2=144, outro_start=204, drops=[[32, 112], [144, 204]],
        phases=[
            dict(name='intro', start=0, end=32),
            dict(name='drop', start=32, end=112),
            dict(name='breakdown', start=112, end=144),
            dict(name='drop', start=144, end=204),
            dict(name='outro', start=204, end=220),
        ],
        bass_by_section=dict(
            intro=dict(bass=-35.0, drums=-24.0),
            drop=dict(bass=-9.0, drums=-8.0),
            breakdown=dict(bass=-32.0, drums=-20.0),
            outro=dict(bass=-45.0, drums=-30.0),
        ),
    )
    sb = dict(
        n_bars=200, music_end=200, intro_end=32, intro_len=32, drop1=32,
        breakdown=96, drop2=128, outro_start=184, drops=[[32, 96], [128, 184]],
        phases=[
            dict(name='intro', start=0, end=32),
            dict(name='drop', start=32, end=96),
            dict(name='breakdown', start=96, end=128),
            dict(name='drop', start=128, end=184),
            dict(name='outro', start=184, end=200),
        ],
        bass_by_section=dict(
            intro=dict(bass=-34.0, drums=-25.0),
            build=dict(bass=-20.0, drums=-14.0),
            drop=dict(bass=-10.0, drums=-9.0),
        ),
    )
    r = dict(
        id='test__00', src='corpus_v2', dj='TestDJ', mix='test_mix', idx=0,
        sa=sa, sb=sb, bpm=(174.0, 174.0), pro_out=100.0, pro_in=17.0, pro_ov=16.0,
        feat_cands=[], dex=205.0, dcue=17.0, dX=16, hist=None,
    )
    import picker_1119b as B
    r['E'] = B.exit_cands(r, r['dex'])
    r['C'] = B.cue_cands(r, r['dcue'])
    r['Edix'] = next(i for i, c in enumerate(r['E']) if 'default' in c['tags'])
    r['Cdix'] = next(i for i, c in enumerate(r['C']) if 'default' in c['tags'])
    return r


def test_real_drops_filters_spurious_intro():
    sa = dict(drops=[[0, 14], [32, 112], [144, 200]])
    rd = F.real_drops(sa)
    assert rd == [[32, 112], [144, 200]]


def test_sec_features_finite_and_coupled():
    r = _sample_row()
    pf = F.sec_pair_feats(r)
    cf = F.fe_cue_sec(r, r['C'][0])
    assert len(pf) > len(F.B.base_feats(r))
    assert len(cf) > len(F.B.fe_cue(r, r['C'][0], False))
    assert np.isfinite(pf[11])  # na - d1e


def test_bayes_mixture_risk_picks_closer_to_high_prob_mode():
    r = _sample_row()
    class _DummyClf:
        def __init__(self, p): self.p = p
        def predict_proba(self, X): return np.array([[1 - self.p, self.p]] * len(X))
    class _DummyReg:
        def __init__(self, v): self.v = v
        def predict(self, X): return np.array([self.v] * len(X))
    # High probability of early exit around bar 97 -> best_c near 97, risk_gain > 30
    j, gain, p, a, b = F.predict_mix_exit((_DummyClf(0.85), _DummyReg(97.0), _DummyReg(205.0)), [r])[0]
    assert abs(r['E'][j]['v'] - 97.0) <= 8
    assert gain > 30.0
    # Ambiguous 50/50 -> staying near default or mid has small/zero gain
    j2, gain2, *_ = F.predict_mix_exit((_DummyClf(0.40), _DummyReg(97.0), _DummyReg(205.0)), [r])[0]
    assert gain2 < 5.0
