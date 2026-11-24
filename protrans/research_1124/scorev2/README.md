# official_v2 scorer (2026-11-24, ukf__10 RCA)

Code: `protrans/score_v2.py` (VERSION `official_v2-place8c`), tests: `protrans/tests/test_score_v2.py`.
v1 (`score.py`, `gain-events-v3-beatid`) is unchanged and stays official until v2 is promoted.

## Why the pro-like ukf__10 exit lost under v1
Re-rendered with the pin (`src2_pin_n1121`), HARD_FALLBACK off, the four candidates reproduce exactly:

| candidate | window [kind, A end, loop, B cue, bars] | v1 |
|---|---|---|
| default (outro-over-intro) | n 256 / 32 / 16 | 36.67 |
| replica_on ("bar 129": blend starts at A bar 128) | n 160 / 16 / 32 | 32.70 |
| replica_x16 (same start, 16 bars) | n 144 / 32 / 16 | 39.87 |
| dropcand_exit (A leaves at end of drop 1) | n 128 / 32 / 16 | 39.94 |

Pro (measured from audio): B audible at A bar ~129-133 (A's breakdown), B bar ~21-25 (intro),
bass swap at A ~143, A gone at ~145-149.

v1 terms are clip-relative shape comparisons after a free +-24 s kick-envelope shift. Nothing in v1
measures which part of each track is playing. Effects on this pair:
- the default is 111 bars away from the pro's exit (A outro vs A breakdown) yet only ~3 points below the near copy;
- replica_on's 32-bar blend makes a 48-bar clip, so the free shift picked a different lag (-8.5 s vs +7.8 s)
  and a different 58 s comparison window; stem_curves fell 59.7 -> 34.6 (drums 66 -> 32, melody 62 -> 24),
  while its bass_swap/cut/length events were measured in a different slice of the pro clip
  (pro swap/cut 17/19 vs 12/14 for the 16-bar renders): the pro's own reference events move with OUR clip length;
- forcing the alignment to the incoming entry instead (decomp_ukf10.json, "anchored") lowers all four, so the
  free shift is already the most generous time base; the missing piece is placement, not the shift.

## What v2 changes
Same weights as v1 for stem_curves 0.28, deck_curves 0.22, beat_align 0.15. The three clip-relative event terms
(bass_swap 0.13, outgoing_cut 0.12, blend_length 0.10) are replaced by the same events measured in each track's
engine bars: swap 0.13, exit 0.12, entry 0.10. Each = mean over decks A/B of
75% exp(-|bar diff| / 8) + 25% same section (intro / dropN / breakdown / outro).
Measurement runs identically on the pro clip and on ours (audio only, no engine metadata):
RANSAC chunk-line locate of each stretched source (`score._fit_chunks`), NNLS per-deck fader gains, -12 dB presence.
If our clip never completes the handoff (B never in, or A still up at the end) while the pro does, all three = 20.
If the pro itself can't be measured, v2 = v1 (1 of 33 pairs: maduk_liquicity_lunar2025__05).

## Files
- `render_ukf10.py`, `decomp_ukf10.py`, `place_ukf10.py`, `loc_test.py`, `v2_ukf10.py`: ukf__10 decomposition
- `synth_v1v2.py`: synthetic gaming checks (same fade 2 bars later / on A's outro / no transition)
- `cohort.py`: 33 pairs x {base, replica_x16, dropcand_exit}, v1 + v2 (job `scorev2-cohort-1124`)
- `ratings.py`: the clips the listener rated, v1 vs v2
- `analyze.py` -> `analysis.json`

## Validation (cohort finished 14:13 ET, 33 pairs x 3 arms, pin src2_pin_n1121)

Pinned v1 baseline matches the published floor: train 32.40 / held-out 34.07.

ukf__10 (does v2 prefer the bar-129 exit?):
| candidate | v1 | v2 |
| default outro-over-intro (A 240-256, B 32) | 36.67 | 37.43 |
| replica_on, 32-bar blend from A 128 (the 32.7 score) | 32.70 | **52.81** |
| replica_x16, 16-bar blend from A 128 | 39.87 | 50.23 |
| dropcand_exit, A leaves at end of drop 1 (bar 128) | 39.94 | 37.61 |

v2 prefers both bar-129 blends. v1 preferred dropcand and default over the closest replica.
dropcand leaves during drop 1, not the breakdown, so v2 correctly scores it like the default.

Placement vs score (96-99 renders, pair-clustered bootstrap):
- vs v2's own pro measurement: Spearman 0.285 -> 0.475, difference CI [0.085, 0.331];
  within-pair "closer placement gets the higher score" 62% -> 80%, +18 pp CI [0.08, 0.28].
- vs the older decisions file: 0.288 -> 0.378, CI [-0.009, 0.216] (touches zero).

the listener's blind ratings (7 clips, 5 pairs, cluster bootstrap by pair):
Spearman 0.655 -> 0.748, difference CI [0.00, 0.35]. Point estimate is better; the interval includes no change.
n is small. One 2/5 (js08) rose 26.96 -> 32.44 because both sits are in drop 1, 110 bars apart;
the 2/5 on js13 (outro vs the pro's mid-drop) correctly fell 29.79 -> 23.55.

Gameability (same two sources, synthetic fades):
identity 100/100; 2-bar shift 82.38/87.79; same fade 112 bars later (A's outro) 66.57/66.95;
both decks up for the whole clip, no handoff, 57.65/60.11 (placement floored at 20).
A no-fade cheat cannot beat a near-copy (~50-88). A correctly shaped fade in the wrong section
can still sit in the mid-60s because 65% of the score is still v1's curve terms.

Arms vs base (paired bootstrap). replica_x16 still overfits held-out on both scorers, less so on v2
(v1 test -2.14 CI [-7.1, 2.77]; v2 test -0.82 CI [-5.26, 3.19]). dropcand_exit is flat on v2
(test +0.10 CI [-5.62, 5.39]). Neither arm is adopted. rules.json and v1 are unchanged.

official_v2 is ready to sit beside v1 for research and nightly comparison. It is not promoted to
replace v1: promotion still needs two night wins plus a fresh mix that passes, and the ratings
sample is too small to carry that decision alone.
