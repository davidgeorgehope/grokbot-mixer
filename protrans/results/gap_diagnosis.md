# Pro-transition gap diagnosis

Admitted clips analysed: **33** (train 25, test 8).

## Ceiling vs current

- Current recreation mean: **25.19** / 100 (held-out test 28.83).
- Oracle mean (perfect per-band gains of our studio copies): **63.59** / 100 (median 63.0, IQR 51.36–76.95).
- Mean technique gap (oracle − current): **38.39** points.
- Oracle if the event detectors agreed (perfect bass-swap / cut / length terms, gated as in score.py): **73.09** / 100 (mean event-term drag **9.5** points).
- Mean unexplained energy after the gain fit: **18.6%**.

The oracle fits time-varying bass/mid/high gains of the two aligned studio
tracks to the pro clip, then runs the same scorer used for recreations
(band proxies, fixed weights). It is the realistic ceiling for an engine
that can only fade and EQ our copies — not invent a third track or a different master.
The oracle is also shown which phrase of each track the DJ used; the engine only
gets a tracklist-time hint, so the +38 includes wrong-window picks as well as
wrong fader shapes. Train oracle mean is 68.0; held-out is 49.8, pulled down by
three Netsky version mismatches rather than by harder mixing.

## Primary-cause buckets

- **technique**: 27
- **version_mismatch**: 3
- **extra_material**: 1
- **tempo_pitch**: 1
- **scorer_limit**: 1

A clip is `technique` when a perfect gain-curve of our sources would beat
the current recreation by 20+ points (or 8+ after other flags are ruled out).
`version_mismatch` is a weak match between a studio copy and the pro clip
outside the blend. `extra_material` is leftover energy the two sources cannot
explain (third track, acapella, samples, FX, MC). `tempo_pitch` is a CDJ-style
rate offset of about 2% or more. `scorer_limit` is a clean fit whose oracle
score is still low — the metric itself is leaving points on the table.

## What each cause costs

Mean points of the 100 − current gap attributed to each cause
(the extra_material figure below spreads residual energy across every clip;
only one clip is primarily leftover audio, which costs about 2 points on the corpus mean):

- technique: 38.66
- version_mismatch: 2.0
- extra_material: 20.49 (shared residual; bucket cost ~2)
- tempo_pitch: 4.98
- scorer_limit: 8.94

Estimated lift of the corpus mean if we fixed that cause:

- Perfect gain-curves / EQ fades (engine): **+38.39**
- Better matching source versions (data): **+2.38**
- Tempo/pitch matching (engine): **+0.38**
- Extra material left unexplained (unfixable): costs **1.99** vs 100
- Scorer ceiling (metric): **8.94**

Engine-fixable scorer terms (mean weighted points, oracle vs current):

- stem_curves: +12.497
- deck_curves: +9.534
- outgoing_cut: +6.445
- bass_swap: +4.703
- beat_align: +4.17
- blend_length: +3.145

## Technique observations on the pro clips

- Mean fitted blend length: 22.41 bars
- Outgoing fader shapes: {'linear': 8, 'equal_power': 7, 'cut': 11, 'curve': 6, 'unknown': 1}
- EQ swap (high vs bass half-cross ≥ 2 bars): 20 / 33
- Filter sweep (highs out well before bass): 5
- Echo-out after the outgoing fade: 0
- Possible outgoing loop (8/16/32-bar jump): 1
- Pitched incoming / outgoing: 5 / 4
- Incoming drop lands on outgoing breakdown / drop / outro: 10 / 16 / 2

## Recommended next steps

The oracle is allowed to see *where* each studio track sits in the pro clip; the engine only gets a tracklist-time hint. So the +38 point gap is both "we mixed a different phrase" and "we faded it differently". Engine rules were not changed in this pass.

1. Engine, biggest lever (~+38 on the corpus mean): hill-climb toward the oracle.
   - Phrase / window picking first. Several clips have oracles in the 80s–90s (Joe Syntax 18 at 94, Hybrid Minds 40 at 92) while our recreation scored 12–21, with the scorer locking 20 s away. Phase-aware planning (incoming drop vs outgoing drop/breakdown/outro) is the right next rule family. Fitted pro behaviour: incoming drop lands on an outgoing drop 16 times, a breakdown 10 times, an outro twice — awareness, not a hard "always drop on the breakdown" rule. Fitted blend length averages 22.4 bars, not a flat 32.
   - Then fader technique. 20 of 33 clips show an EQ swap of 2+ bars between the high and bass handoffs; outgoing shapes are mixed (11 cuts, 8 linear, 7 equal-power, 6 curves). Independent bass / mid / high handoffs and allowing a shorter cut (not only a long tail) should move stem_curves (+12.5) and deck_curves (+9.5), the two terms that account for most of the oracle gap. Filter sweeps are uncommon (5); echo-outs were not found; a loop showed up once.
   - Keep the existing train/test-by-DJ gate. Only keep a change if held-out does not drop. Do not retune score.py weights.

2. Metric, second lever (~+9.5): the scorer's bass-swap / outgoing-cut / blend-length detectors. A perfect gain-curve still loses about 10 points here (oracle 63.6 vs 73.1 if those event terms matched and were gated as they are today). The detectors sometimes read a real pro blend as 1 bar long or a bass swap at bar 0. Fixing the event detectors would make nightly hill-climbs steer toward real fade errors instead of measurement noise. This is not an engine-rule change.

3. Data, third lever (~+2.4 on the whole set, much more on held-out): three Netsky test clips are version mismatches (`netsky_hospital_classics__15`, `__16`, `__24`). Test oracle mean is 49.8 vs train 68.0 mainly because of those copies, not because the held-out DJs are harder to mix. Re-find the matching studio/edit and re-admit. Tempo/pitch offsets exist (5 incoming, 4 outgoing flagged) but only one clip is primarily a pitch problem (~+0.4 if we added a ±3% rate search).

4. Unfixable: only `netsky_hospital_classics__02` is primarily leftover energy (third track / sample / FX). Talkover was already filtered. Do not let one clip drive rule changes.

Practical target: ~64 with today's scorer if we match windows and gains; ~73 after event-detector cleanup. 80 is not reachable without better versions on the mismatched Netsky clips and some metric repair.

## Per-clip table

| id | split | current | oracle | gap | unexplained | ver A | ver B | bucket |
|---|---|---:|---:|---:|---:|---:|---:|---|
| joe_syntax_hospital__18 | train | 12.49 | 94.06 | 81.57 | 0.0113 | 0.9856 | 0.9955 | technique |
| hybrid_minds_ukf__40 | train | 20.39 | 92.39 | 72.0 | 0.0109 | 0.9879 | 0.9934 | technique |
| hybrid_minds_ukf__33 | train | 10.54 | 76.84 | 66.3 | 0.1246 | 0.7931 | 0.9618 | technique |
| joe_syntax_hospital__11 | train | 15.96 | 76.95 | 60.99 | 0.0572 | 0.8819 | 0.9899 | technique |
| hybrid_minds_ukf__45 | train | 21.56 | 81.96 | 60.4 | 0.1373 | 0.8742 | 0.9724 | technique |
| wilkinson_boomtown2026__33 | test | 20.41 | 78.89 | 58.48 | 0.1804 | 0.8825 | 0.9324 | technique |
| hybrid_minds_ukf__08 | train | 21.17 | 78.18 | 57.01 | 0.1649 | 0.8216 | 0.8378 | technique |
| hybrid_minds_ukf__28 | train | 16.93 | 73.85 | 56.92 | 0.1679 | 0.882 | 0.819 | technique |
| joe_syntax_hospital__01 | train | 29.44 | 85.82 | 56.38 | 0.0214 | 0.984 | 0.9887 | technique |
| joe_syntax_hospital__00 | train | 28.39 | 84.31 | 55.92 | 0.0346 | 0.9724 | 0.9947 | technique |
| hybrid_minds_ukf__10 | train | 15.09 | 69.69 | 54.6 | 0.1032 | 0.9355 | 0.9623 | technique |
| hybrid_minds_ukf__20 | train | 17.44 | 66.1 | 48.66 | 0.3627 | 0.945 | 0.7963 | technique |
| joe_syntax_hospital__13 | train | 34.61 | 78.42 | 43.81 | 0.1245 | 0.988 | 0.9175 | technique |
| hybrid_minds_ukf__11 | train | 16.83 | 59.34 | 42.51 | 0.2913 | 0.8495 | 0.8364 | technique |
| hybrid_minds_ukf__19 | train | 31.94 | 73.63 | 41.69 | 0.2618 | 0.9437 | 0.9028 | technique |
| joe_syntax_hospital__14 | train | 31.96 | 70.13 | 38.17 | 0.1158 | 0.9731 | 0.9213 | technique |
| hybrid_minds_ukf__25 | train | 17.56 | 53.66 | 36.1 | 0.2443 | 0.6038 | 0.912 | technique |
| joe_syntax_hospital__17 | train | 15.63 | 51.36 | 35.73 | 0.1451 | 0.8188 | 0.9752 | technique |
| hybrid_minds_ukf__13 | train | 31.16 | 66.19 | 35.03 | 0.1068 | 0.8985 | 0.9239 | technique |
| hybrid_minds_ukf__00 | train | 13.05 | 47.21 | 34.16 | 0.1668 | 0.9333 | 0.9059 | technique |
| netsky_hospital_classics__23 | test | 25.05 | 57.61 | 32.56 | 0.2207 | 0.8025 | 0.9141 | technique |
| hybrid_minds_ukf__09 | train | 32.25 | 63.0 | 30.75 | 0.1602 | 0.8979 | 0.9401 | technique |
| joe_syntax_hospital__08 | train | 26.76 | 56.61 | 29.85 | 0.2039 | 0.8949 | 0.8566 | technique |
| netsky_hospital_classics__06 | test | 28.76 | 56.25 | 27.49 | 0.2941 | 0.8681 | 0.3803 | technique |
| netsky_hospital_classics__17 | test | 29.95 | 51.25 | 21.3 | 0.0714 | 0.9045 | 0.9953 | technique |
| hybrid_minds_ukf__23 | train | 23.95 | 45.06 | 21.11 | 0.2379 | 0.731 | 0.9289 | technique |
| joe_syntax_hospital__09 | train | 32.82 | 52.88 | 20.06 | 0.4544 | 0.9796 | 0.5527 | technique |
| netsky_hospital_classics__02 | test | 16.16 | 34.35 | 18.19 | 0.3071 | 0.7199 | 0.9171 | extra_material |
| netsky_hospital_classics__24 | test | 28.74 | 46.42 | 17.68 | 0.4665 | 0.8525 | 0.2707 | version_mismatch |
| hybrid_minds_ukf__12 | train | 37.75 | 50.24 | 12.49 | 0.1322 | 0.9174 | 0.7937 | tempo_pitch |
| joe_syntax_hospital__12 | train | 45.11 | 51.92 | 6.81 | 0.0884 | 0.9832 | 0.9761 | scorer_limit |
| netsky_hospital_classics__15 | test | 45.83 | 46.84 | 1.01 | 0.2392 | 0.3403 | 0.953 | version_mismatch |
| netsky_hospital_classics__16 | test | 35.73 | 26.9 | -8.83 | 0.4117 | 0.772 | 0.2736 | version_mismatch |
