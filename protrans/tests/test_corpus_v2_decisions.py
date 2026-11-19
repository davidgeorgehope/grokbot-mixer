import os, sys, types
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import numpy as np
import corpus_v2_pipeline as P


def test_pro_decision_relatives():
    feat = dict(
        cue=dict(outgoing_bar=193.76, outgoing_section='outro',
                 incoming_bar=32.18, incoming_section='build'),
        track_a=dict(sections=dict(
            music_end=220, outro_start=180,
            phases=[dict(name='drop', start=32, end=180),
                    dict(name='outro', start=180, end=220)],
        )),
        track_b=dict(sections=dict(
            drop1=40, music_end=200,
            phases=[dict(name='intro', start=0, end=24),
                    dict(name='build', start=24, end=40),
                    dict(name='drop', start=40, end=200)],
        )),
    )
    pd = P.pro_decision_from_feat(feat, bass_swap_bar=8.5)
    assert pd['outgoing_exit_bar'] == 193.76
    assert pd['outgoing_section'] == 'outro'
    assert pd['outgoing_bars_into_section'] == 13.76
    assert pd['outgoing_bars_left'] == 26.24
    assert pd['outgoing_bars_to_outro'] == -13.76  # already past outro start
    assert pd['incoming_cue_bar'] == 32.18
    assert pd['incoming_section'] == 'build'
    assert pd['incoming_bars_into_section'] == 8.18
    assert pd['incoming_rel_drop1'] == -7.82
    assert pd['bass_swap_bar'] == 8.5


class _D:
    SR = 44100
    BAR_SEC = 60.0 / 174.0 * 4


def test_bass_swap_and_per_bar():
    hop = 512
    frames_per_bar = int(round(_D.BAR_SEC * _D.SR / hop))
    n = frames_per_bar * 16
    a = np.ones(n)
    b = np.ones(n) * 1e-6
    # incoming bass silent for 4 bars, then louder than outgoing
    start = frames_per_bar * 4
    b[start:] = 2.0
    a[start:] = 0.5
    gains = dict(all=dict(a=a, b=b), bass=dict(a=a, b=b))
    swap = P.bass_swap_bar_from_gains(gains, hop, _D)
    assert swap is not None
    assert 3.5 <= swap <= 4.5
    levels = P.per_bar_deck_levels(gains, hop, _D)
    assert levels['n_bars'] == 16
    assert len(levels['bass']['a']) == 16
    # after the swap, incoming (b) should be louder (less negative / higher dB)
    assert levels['bass']['b'][8] > levels['bass']['a'][8]


if __name__ == '__main__':
    test_pro_decision_relatives()
    test_bass_swap_and_per_bar()
    print('ok')
