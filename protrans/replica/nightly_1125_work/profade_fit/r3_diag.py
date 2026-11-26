import sys; sys.path.insert(0, '/workspace/mixes/protrans/replica')
import pro_fade_fit as F
B = {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -8.5, 'PRO_FADE_SHELF_DB': -10.0, 'PRO_FADE_EXIT_SLOPE': 2.5, 'PRO_FADE_HIGH_OFS': 7.0, 'PRO_FADE_BASS_CUT_DB': -24.0}
F.run_grid([('full27_base', {}), ('full27_b24_e85_s10_l25_h70', B)])
print('DONE_R3', flush=True)
