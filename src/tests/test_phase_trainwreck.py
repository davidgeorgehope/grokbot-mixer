"""Phase regression: a short end-of-overlap drift must not hide in an average.

Synthetic onset envelopes replace the deleted copyrighted r12 render. These
exercise the actual wide-search and per-bar scoring, not mocked score rows.
"""
import numpy as np
import pytest
import checks as C

@pytest.mark.parametrize('drift_ms', [0, 24, -24])
def test_tail_phase_drift_is_detected(monkeypatch, drift_ms):
    fr = 22050 / 64
    n = int(20*C.BAR*fr)
    rng = np.random.default_rng(19)
    source = np.zeros(n)
    for i in range(100, n-100, 29):
        source[i:i+3] = rng.uniform(.2, 1)
    shifted = np.interp(np.arange(n)+drift_ms*fr/1000, np.arange(n), source)
    mix = source.copy()
    boundary = int(7*C.BAR*fr)
    mix[boundary:] = shifted[boundary:]
    monkeypatch.setattr(C, 'onset', lambda: (mix, fr))
    monkeypatch.setattr(C, 'src_onset', lambda b: (source, 0))
    monkeypatch.setattr(C, 'nudge_ms', lambda b,k: 0)
    def deck(name):
        return dict(id=name, start_bar=0, end_bar=12,
                    full_map=[[i,'mix'] for i in range(12)], auto={'gain':[[0,1]]})
    rows = C.bar_alignment_report(deck_pair=(deck('A'), deck('B')))
    assert rows
    failures = C.alignment_failures(rows)
    if drift_ms:
        assert any(r['tail'] and r['kind']=='mix' and abs(r['lag_0'])>C.TOL_DRIFT_MS
                   for r in failures), failures
    else:
        assert not failures, failures
