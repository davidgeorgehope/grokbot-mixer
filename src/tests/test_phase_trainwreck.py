"""Regression: Mix 07 r12 Daydreaming→Parallel is a heard trainwreck that the old
±40 ms / corr>=0.65 mixdown check reported as a single −11 ms bar.

The clip is the before-fix reference:
  /workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.mp3
"""
import os, json, numpy as np, librosa
import checks as C

CLIP = '/workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.mp3'
TIMING = CLIP.replace('.mp3', '.timing.json')

def test_r12_parallel_trainwreck_fails_phase_check():
    from conftest import require_fixtures
    require_fixtures(CLIP, TIMING)
    os.environ.setdefault('NUDGE', 'nudge07.json')
    tim = json.load(open(TIMING))
    require_fixtures(*(f"{C.SRC}/st/{d['id']}.wav" for d in tim['decks']))
    y, _ = librosa.load(CLIP, sr=22050, mono=True)
    hop = 64
    o = librosa.onset.onset_strength(y=y, sr=22050, hop_length=hop)
    fr = 22050 / hop
    pad = int(round(tim['clip_start_bar'] * C.BAR * fr))
    o_pad = np.concatenate([np.zeros(pad, dtype=o.dtype), o])
    orig_onset = C.onset
    if hasattr(C.onset, 'cache_clear'):
        C.onset.cache_clear()
    C.onset = lambda: (o_pad, fr)
    try:
        rows = C.bar_alignment_report(deck_pair=(tim['decks'][0], tim['decks'][1]))
        bad = C.alignment_failures(rows)
    finally:
        C.onset = orig_onset
        if hasattr(C.onset, 'cache_clear'):
            C.onset.cache_clear()
    assert rows, 'phase report produced no rows'
    t0 = int(tim['trans']['end_bar'])
    tail_bad = [r for r in bad if r.get('tail') or r['bar'] >= t0 - C.TAIL_BARS]
    assert tail_bad, (
        f'known trainwreck tail (last {C.TAIL_BARS} overlap bars ending {t0}) '
        f'produced no phase failures (old overlap-average / low-corr-skip bug). '
        f'bad={bad[:12]} sample={rows[:6]}')
    # Heard failure mode: Parallel drifts vs the mix in the last ~5 bars
    # (r12 looped Day 123-127 over Parallel intro 11-15), not a whole-overlap
    # average and not inter-deck source-vs-source alone.
    assert any(r.get('kind') != 'interdeck' and abs(r.get('lag_0', r['lag'])) > C.TOL_DRIFT_MS
               for r in tail_bad), tail_bad[:12]
