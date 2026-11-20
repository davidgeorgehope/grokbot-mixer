# Pro pick vs ours: joe_syntax_hospital__12

Cyantific - Ghetto Blaster -> S.P.Y - Seconds To Midnight. Bars are each track's own bars at mix tempo; in_next_drop_vs_blend_end < 0 means the incoming's drop lands inside the blend, 0 = right as it ends; out_time is the time in the outgoing track; mix_time is the pro's set.

| who | out_start | out_end | in_start | out_start_section | in_start_section | touches_out_slowdown | in_next_drop_vs_blend_end | out_last_drop_played | out_time | mix_time | why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pro | 189.0 | 208.0 | 140.0 | drop 2 | breakdown + slowdown/half-time | True | 1.0 | blend starts 3 bars before its end | 4:20 | 34:52 | what the DJ did |
| default | 208 | 224 | 48 | outro + slowdown/half-time | intro | True | 0 | all | 4:46 | None | outro-over-intro bonus window (A plays its outro, B's first drop lands as A ends); blend starts inside the outgoing slowdown |
| exit_only | 160 | 176 | 16 | drop 2 | intro | False | 32 | cut 32 bars early | 3:40 | None | lowest engine cost |
