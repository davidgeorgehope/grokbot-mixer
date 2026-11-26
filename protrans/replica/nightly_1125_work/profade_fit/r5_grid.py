"""Round 5 (2026-11-26): fixes aimed at the r4_fit2 L1 fails. One idea per arm on top of fit2.

r4 diag (diag_fade.txt, rows.jsonl): L1 = summed <120 Hz minus the louder deck's lows (two basses at
equal level), NOT a level dip. fit2's two NEW fails vs base:
  - liquiddnbftw__16 (cue_early, 32-bar blend): outgoing's -24 dB residual bass sits on the bass-light
    incoming intro (-37..-42 vs -37..-38 dB) for bars 19-23 while the shelf holds (l1 3.0). rel8 fixed it (1.84).
  - sirenity__56: residual meets incoming at bar 17 (-47.0 vs -47.8 dB), inside the handoff-ramp tail,
    before the end-of-ramp rel cap starts, so rel8 did not help (3.22).
  - liquiddnbftw__10 fails in base too (4.21 -> 3.7), at -66 dB in a breakdown.
All three sit 20-50 dB under the body bass (l1a, the audible L1, is 0 in every arm). No threshold changes.
"""
import sys; sys.path.insert(0, '/workspace/mixes/protrans/replica')
import pro_fade_fit as F
B = {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -8.5, 'PRO_FADE_SHELF_DB': -10.0, 'PRO_FADE_EXIT_SLOPE': 2.5, 'PRO_FADE_HIGH_OFS': 7.0, 'PRO_FADE_BASS_CUT_DB': -24.0}
def c(**k): d = dict(B); d.update(k); return d
F.run_grid([
    ('r4_base', {}),                                   # control (cached in rows.jsonl)
    ('r4_fit2', c()),                                  # control (cached)
    ('r5_rel4', c(PRO_FADE_BASS_REL=4)),               # lighter cap: keep rel8's L1 fix, lose less bass MAE
    ('r5_rel8_mid', c(PRO_FADE_BASS_REL=8, PRO_FADE_BASS_REL_MID=1)),  # rel8 + cap starts mid-handoff (sirenity)
    ('r5_rel4_mid', c(PRO_FADE_BASS_REL=4, PRO_FADE_BASS_REL_MID=1)),  # same, lighter cap
    ('r5_b30', c(PRO_FADE_BASS_CUT_DB=-30)),           # residual 6 dB lower, still partial (no kill)
    ('r5_ex35', c(PRO_FADE_EXIT_SLOPE=3.5)),           # shorter shelf tail -> shorter residual overlap
])
print('DONE_R5', flush=True)
