# Ears: first tool probe (2026-10-28)

Setup: home GPU box (Apple MPS), venv `~/ears/.venv` (py3.11, torch 2.15, beat_this final0, basic-pitch CoreML, laion/larger_clap_music, MERT-v1-95M). Script: `ears/ears_probe.py`, raw scores: `ears/probe_results_2026-10-28.json`.
Calibration windows cut from dj-mix-03-60-refill mixdown: BAD 33:50-34:40 (1/5), BAD-ish 14:42-15:20 (far-back loop), GOOD 30:31-31:30 (5/5), 7 neutral blends, 2 solo (non-blend) windows, 40 Raveform pro transition segments as the reference set.

| metric (mixdown) | BAD | BAD-ish | GOOD | neutral range | pro median / p90 | verdict |
|---|---|---|---|---|---|---|
| Beat This beat-interval CV | **0.337** | 0.028 | 0.029 | 0.026-0.179 | 0.069 / 0.331 | separates BAD; false hits on beatless/breakdown windows |
| Beat This off-grid beats | **0.21** | 0.00 | 0.006 | 0-0.228 | 0.017 / 0.187 | same |
| Beat This bad bars (downbeats not 4 apart) | **0.25** | 0 | 0 | 0-0.318 | 0.015 / 0.29 | same |
| Basic Pitch dissonance (mean) | 0.013 | 0.010 | 0.013 | 0.004-0.023 | 0.002 / 0.009 | no separation on the mixdown |
| CLAP kNN distance to pro | 0.020 | 0.018 | 0.017 | 0.006-0.028 | 0.008 / 0.021 | no separation |
| MERT kNN distance to pro | 0.084 | 0.094 | 0.089 | 0.075-0.125 | 0.077 / 0.093 | no separation |

Takeaways
- Beat This works: it gets confused when two drum grids disagree. Use it gated on "both decks drumming" (else breakdowns trip it). Best as a per-deck check: run it on each deck's rendered signal and compare the grids (phase offset in ms + downbeat agreement).
- Basic Pitch on the mixdown can't tell whose notes are whose. Next: run it per deck (render A and B separately for the blend window, ideally the melodic stems) and score cross-deck intervals only.
- Off-the-shelf embedding distance doesn't hear "bad". They're only useful as features for a trained classifier (positives = pro + 4-5 ratings, negatives = synthetic bad blends).
- The far-back loop (BAD-ish) isn't an acoustic problem. Catch it with the structural rule (only loop the phrase right before the out point), not with ears.

Runtime for 52 files (~60 min audio), GPU box: MPS Beat This 18 s, Basic Pitch 56 s (CoreML), CLAP 51 s, MERT 86 s, about 3.5 min total. Same box CPU-only: see CPU line below.
CPU-only on the same box: Beat This 68 s, Basic Pitch 51 s, CLAP 46 s, MERT 209 s, about 6.2 min total. MPS is about 3.8x faster for Beat This and 2.4x for MERT. The box CPU wasn't benchmarked because two render workers were using its RAM.

## Ears step 2: per-deck check (2026-10-28)
`EARS_HOST=<gpu ssh alias> bash ears/ears.sh src2/<prefix>_meta.json [src2/nudgeX.json]` writes `ears/<prefix>_ears_report.json` and prints a verdict per blend.
- `ears_cut.py` (box, light): rebuilds each deck's ungained audio for the blend bars from the meta (full_map + nudges) and records the per-bar crossfader gains. Its output matches the master within about 1 ms.
- `ears_check.py` (GPU, about 1.6 min for 19 blends: demucs 75 s, Beat This 5 s, Basic Pitch 16 s): splits each deck with htdemucs. Beat This runs on the drums stem and Basic Pitch on vocals+other. Everything is scored only on bars where both decks are audible (gain 0.2 or more) and both drum stems are active.
- Verdict: FAIL if there are at least 4 both-drum bars and either the downbeats agree on less than 50% of bars or the median beat offset is over 45 ms. Note dissonance (`diss`) is report-only because it didn't separate bad from good. `--rescore report.json` re-applies the thresholds without a GPU.

Mix 03 refill (mixLen21b) results. Calibration: 33:50 FAIL (B's downbeat lands 1 beat late, agreement 0.00), 30:31 PASS (agreement 0.72, offset 20 ms).
PASS: 5:08, 8:49, 18:23, 21:42, 24:16, 27:35, 30:31, 45:36, 55:10, 56:38. Not enough both-drum bars to judge: 14:42, 38:15, 48:33.
FAIL: 11:02 (only 4 both-drum bars, beats half a beat apart), 33:50 (downbeats), 34:56 (7 bars, downbeats + offset), 40:49 (B 3 beats off), 43:02 (A 3 beats off + offset), 51:51 (A 2 beats off).
The FAILs at 40:49 onward come before the listener's listening notes, so they are predictions: the likely cause is a downbeat that is off by a beat or a half bar in that track's grid in st/<id>.json. Check them by ear before trusting them. Demucs adds a little run-to-run jitter, so borderline values can move.

Integration (not wired): planner: run ears_check per candidate pair window offline, cache per (a,b,out_bar,in_bar), and add a cost when the verdict is FAIL. A downbeat FAIL also suggests correcting that track's `downs` phase. Tests: test_mix02_traits could load `<prefix>_ears_report.json` and assert no FAIL on blends with 4 or more both-drum bars.

## Suspected false positive: recalibrate (2026-10-29)
- mixPlan6d (delivered as Mix 04), blend 8 at 24:16, Culture Shock – U & I -> Grafix ft. Ruth Royall – Alone (OPuVVhbkicU, incoming from bar 16): FAIL, 96 ms median beat offset, p90 172 ms, downbeats agree on 0.5, phase_A = phase_B = 0, 12 both-drum bars.
- Direct check disagrees: cross-correlating the two cut decks' onset envelopes gives a 1.5 ms lag (blends 7/9/10: 0/1.5/-1.5 ms), and OPuVVhbkicU's own grid sits within ~15 ms of its kicks. The same 96 ms showed up with a different U & I window (mixPlan6e), so the fail follows OPuVVhbkicU's intro: Beat This most likely tracks its intro drums off the beat.
- To do: before a FAIL, cross-check Beat This against direct onset xcorr of deck A vs deck B; FAIL only if both agree (e.g. xcorr lag > 20 ms), else report "suspect". Ears is not yet part of the official suite.

## Mix 03 refill v2 (mixLenMl, 2026-10-29)
- ears.sh: PASS 13, n/a 3, FAIL 4: k0 2:57 Supernova->Solitude (down_agree 0.41, 172 ms), k6 19:52 U & I->Alone (the known OPuVVhbkicU intro false positive, 96 ms), k17 51:52 When My Love->Half Life (downbeats only, 0 ms offset), k18 54:04 Half Life->Sweet Lies (only 4 both-drum bars).
- Direct drum checks disagree on all four: test_mixdown_beats_aligned_every_overlap_bar (each deck vs master <=10 ms) passes, guardrail F1 passes, and the kick/snare per-bar beat_off (src/tests/ears.py; 34:05 bad blend = 21 bars) is 1/2/4/0 bars. Treated as suspect per the rule above, not real fails. Worth an ear check at 2:57 and 51:52.

## Official gate (2026-10-29)
- `src/tests/test_ears_gate.py`: ears FAIL + direct drum check (deck-vs-deck onset lag > 20 ms, or > 8 kick/snare beat-off bars) = confirmed -> test fails, planner bans the window. Ears FAIL alone = suspect (warning).
- Calibration vs listener: 24:16 U & I->Alone 3.5 (lag 0, 2 bars), 2:57 Supernova->Solitude 3 (lag 0, 1 bar), 51:52 When My Love->Half Life 4 (lag 0, 4 bars) -> all suspects; bad 34:05 had 21-25 bars. Mild 'a little weird' cases are planner costs (SUSPPEN for suspects rated <=3), not fails.
- Run with the render's NUDGE env so decks match the master. The GPU host comes from EARS_HOST or config.env.
