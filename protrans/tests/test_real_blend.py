import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
import pytest
import real_blend as R


def test_true_blend_and_scale_invariance():
    a = np.r_[np.ones(48), np.zeros(16)]
    b = np.r_[np.zeros(16), np.ones(48)]
    r = R.assess(a, b * .02, .25, 1)
    assert not r['flagged']
    assert r['longest_overlap_bars'] == 8


def test_fade_gap_drop():
    a = np.r_[np.linspace(1, 0, 24), np.zeros(40)]
    b = np.r_[np.zeros(40), np.ones(24)]
    assert R.assess(a, b, .25, 1)['overlap_bars'] == 0
    assert R.assess(a, b, .25, 1)['flagged']


def test_short_overlap_and_disconnected_snippets():
    a = np.ones(100)
    b = np.tile(np.r_[np.ones(10), np.zeros(10)], 5)
    r = R.assess(a, b, .25, 1)
    assert r['overlap_bars'] > 8
    assert not r['flagged']  # musical gaps do not erase measured simultaneous audio
    assert r['longest_overlap_bars'] < 8


def test_inaudible_leakage_and_missing_deck():
    a = np.ones(100)
    b = np.r_[np.ones(8), np.ones(92) * .1]
    assert R.assess(a, b, .25, 1)['flagged']
    assert R.assess(a, b * 0, .25, 1)['flagged']


def test_threshold_boundary():
    assert not R.assess(np.ones(10), np.ones(10), .25, 1)['flagged']
    assert R.assess(np.ones(9), np.ones(9), .25, 1)['flagged']


def test_bad_measurement_rejected():
    with pytest.raises(ValueError):
        R.assess([float('nan')], [1], .25, 1)


def test_admission_and_daily_share_gate(monkeypatch, tmp_path):
    import admit, run_admitted_tune as T
    p = tmp_path / 'admitted.json'
    p.write_text('[{"id":"good"},{"id":"bad"}]')
    monkeypatch.setattr(admit, 'ADMITTED', str(p))
    import talkover
    monkeypatch.setattr(talkover, 'flagged_ids', lambda: set())
    monkeypatch.setattr(R, 'eligible', lambda r: r['id'] == 'good')
    assert [r['id'] for r in admit.load_admitted()] == ['good']
    monkeypatch.setattr(admit, 'load_admitted', lambda: [])
    assert T.load_recs() == []


def test_source_fitted_audio_real_blend_vs_fade_gap():
    import diagnose_gap as D
    t = np.arange(int(40 * D.SR)) / D.SR
    a = .2 * np.sin(2 * np.pi * 430 * t)
    b = .2 * np.sin(2 * np.pi * 1130 * t)
    for overlap, reject in ((16, False), (-4, True)):
        ga = np.clip((24 - t) / 2, 0, 1)
        gb = np.clip((t - (24 - overlap)) / 2, 0, 1)
        mix = ga * a + gb * b
        gains, _, _, hop = D.band_gains(mix, a, b)
        result = R.assess(gains['all']['a'], gains['all']['b'], hop / D.SR, D.BAR_SEC)
        assert result['flagged'] is reject


def test_tune_decisions_cannot_cross_cohorts(monkeypatch, tmp_path):
    import json
    import run_admitted_tune as T
    monkeypatch.setattr(T.paths, 'LOGS', str(tmp_path))
    (tmp_path / 'tune_log.jsonl').write_text(json.dumps(dict(
        name='old', delta={}, scorer_version=T.score.SCORER_VERSION,
        cohort_ids=['a', 'b'])) + '\n')
    assert T.decided_variants(['a']) == []
    assert len(T.decided_variants(['b', 'a'])) == 1


def test_calibration_boundary_separates_radio_gap_and_tight_cut():
    # 13 frames at 174 BPM = 2.356 bars (Hospital excerpt), 18 = 3.262 (Netsky).
    bar_sec = 240 / 174
    assert R.assess(np.ones(13), np.ones(13), .25, bar_sec)['flagged']
    assert not R.assess(np.ones(18), np.ones(18), .25, bar_sec)['flagged']
    assert R.assess(np.zeros(18), np.ones(18), .25, bar_sec)['flagged']


@pytest.mark.parametrize('failure', ['version', 'talkover', 'real_blend', None])
def test_ingestion_applies_all_admission_gates(monkeypatch, tmp_path, failure):
    import admit, talkover
    clipdir = tmp_path / 'clip'
    clipdir.mkdir()
    pro = str(clipdir / 'pro.wav')
    monkeypatch.setattr(admit.extract, 'extract_one', lambda r, m: dict(r, pro_clip=pro))
    monkeypatch.setattr(admit, 'ensure_source', lambda yt: yt)
    monkeypatch.setattr(admit.version_match, 'match_pair', lambda *a, **k:
                        dict(passed=failure != 'version', reasons=[]))
    monkeypatch.setattr(talkover, 'check_row', lambda r:
                        dict(flagged=failure == 'talkover', talk_s=10, talk_frac=.2))
    calls = []
    def real(row):
        calls.append(row['id'])
        return dict(flagged=failure == 'real_blend', reason='insufficient_overlap')
    monkeypatch.setattr(R, 'check_row', real)
    monkeypatch.setattr(admit, '_log', lambda row: None)
    c = dict(id='new', mix_id='set', dj='new-heldout-dj', split='test',
             t_a=0, t_b=120, t_next=240,
             a=dict(title='A', yt='a'), b=dict(title='B', yt='b'))
    row = admit.process_pair(c, 'mix')
    assert row['verdict'] == ('admit' if failure is None else 'reject')
    assert bool(calls) == (failure in ('real_blend', None))
