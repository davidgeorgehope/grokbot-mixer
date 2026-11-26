import sys; sys.path.insert(0, '/workspace/mixes/protrans/replica')
import pro_fade_fit as F
B = {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -8.5, 'PRO_FADE_SHELF_DB': -10.0, 'PRO_FADE_EXIT_SLOPE': 2.5, 'PRO_FADE_HIGH_OFS': 7.0, 'PRO_FADE_BASS_CUT_DB': -24.0}
def c(**k): d = dict(B); d.update(k); return d
F.run_grid([
    ('r4_base', {}),
    ('r4_fit2', c()),
    ('r4_rel8', c(PRO_FADE_BASS_REL=8)),
    ('r4_sw1', c(PRO_FADE_BASS_SW=1)),
    ('r4_rel8_sw1', c(PRO_FADE_BASS_REL=8, PRO_FADE_BASS_SW=1)),
    ('r4_rel12_sw1', c(PRO_FADE_BASS_REL=12, PRO_FADE_BASS_SW=1)),
    ('r4_b40_sw1', c(PRO_FADE_BASS_CUT_DB=-40, PRO_FADE_BASS_SW=1)),
])
print('DONE_R4', flush=True)
