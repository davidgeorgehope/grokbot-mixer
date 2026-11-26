# Midnight Mixer Technique Research — 2026-11-26 (ET)

**Outcome: needs more data. `HIGH_GATE` stays off by default. `protrans/rules.json` and all defaults/thresholds are unchanged.** The two declared offsets (`HIGH_OFS=8` and `HIGH_OFS=-4`) produced identical audio on all 33 pairs, so this run does not pick an offset. No promotion and no default change.

## 1. What was tested

Carry-over from `docs/RESEARCH_2026-11-25_midhold.md`: default `HIGH_SWAP` is gated by `bob()` (drums-on-drums for at least half the blend), which fired a high-band swap on only **2/33** cohort pairs. Prototype `HIGH_GATE=1` (off by default, `src2/mix_simple.py` `above_both()`, passed through `protrans/recreate.py`) also allows the `>2 kHz` high swap when both decks carry above-bass energy (within 6 dB of their 75th-percentile body) for at least half the blend, not only drums-on-drums.

Job `highgate-cohort-1126` (`protrans/research_1126/eval_highgate.sh`, `done rc=0` at 3:18:25 AM ET) rendered a like-for-like 33-pair cohort, same windows as the base, for:

- `hgb1126_base` — current rules, `HIGH_GATE` unset
- `hg8_1126` — `HIGH_GATE=1`, `HIGH_OFS=8` (the value already in `rules.json`)
- `hgm4_1126` — `HIGH_GATE=1`, `HIGH_OFS=-4` (prefer highs 4 bars before the bass swap)

Temp rules files only (`/tmp/rules_highgate_1126_{8,-4}.json`). Then `eval_tailexit.py` and official `v2` (`protrans/score_v2.py`, `official_v2-place8c`) via `protrans/research_1126/eval_v2.py`.

Earlier smoke `highgate-smoke-1126` (`done rc=0` 11:58 PM ET 11/25) on train pair `joe_syntax_hospital__12`: official `v1` **32.29 → 35.59**, same window. The cohort reproduced that exact pair score.

**Metric direction: higher is better** for both official `v1` (`protrans/score.py`, `gain-events-v3-beatid`, remains official) and official `v2` (`official_v2-place8c`). These are not error metrics. A webhook note that treated "all 34.02 vs 33.93", "train 34.26 → 35.11", "test 33.62 vs 31.86" as a highgate-vs-base comparison, and assumed lower is better, was comparing `v1` vs `v2` *inside* `hg8_1126` and had the direction backwards. The numbers below are arm minus `hgb1126_base`.

## 2. Cohort results (33 pairs: 21 train / 12 held-out test)

CIs are 4000-draw mix-grouped bootstrap deltas vs `hgb1126_base` (seed 20261126, `protrans/promotion_judge.py`). Train is only 2 mixes (Hybrid Minds, Joe Syntax) and test is 4 mixes, so the train CI is tight because there are two groups, not because every pair moved the same amount. `hg8_1126` and `hgm4_1126` are one column: all 33 rendered mp3s had identical full-file hashes, and every `v1`/`v2` score matched.

| Variant | `v1` Train | `v1` Held-Out | `v1` All | `official_v2` Train | `official_v2` Held-Out | `official_v2` All | Must-Pass (`eval_tailexit`) |
|---|---:|---:|---:|---:|---:|---:|---|
| `hgb1126_base` (default) | 33.30 | **33.92** | 33.53 | 34.84 | **32.15** | 33.86 | **29/33** (test **12/12**, train 17/21: `L1:1`, `N1:3`, `X1:0`) |
| `HIGH_GATE=1` (`hg8_1126` / `hgm4_1126`, identical) | **34.26** (+0.95 [+0.85, +1.02]) | 33.62 (−0.30 [−0.53, +0.02]) | 34.02 (+0.50 [−0.37, +0.88]) | **35.11** (+0.27 [−0.35, +1.27]) | 31.86 (−0.29 [−0.47, −0.09]) | 33.93 (+0.07 [−0.38, +0.83]) | **29/33** (same four fails, `X1:0`) |

Windows (`pick.win`) were identical on all 33 pairs. Official `v1` changed on **14/33** pairs (9 better, 5 worse, 19 unchanged). On those 14 treated pairs only: train (8) +2.50, test (6) −0.61, all +1.17 [−0.74, +2.23].

`eval_tailexit` hard-check fails were unchanged: `hybrid_minds_ukf__09` `L1` (sum over 3.04 dB at bar 200); `hybrid_minds_ukf__23`, `joe_syntax_hospital__08`, `joe_syntax_hospital__11` `N1` (same half-beat lags). Test stayed 12/12. Median summed-lows dip stayed 23.6 dB. Manabe collision median stayed 0.0369; continuity 2.7599 → 2.7988; banger-clash rate 0.1004 → 0.0768.

## 3. What actually changed in the render

- Base already had a high-band swap on **2/33** pairs (`joe_syntax_hospital__08`, `__09`), both already at 4 bars before the bass swap. Those two scores and hashes were unchanged.
- `HIGH_GATE` newly fired a high-band swap on **14/33** pairs (high_bar present 2 → 16). Every new swap landed at **swap_bar − 4**, for both `HIGH_OFS=8` and `HIGH_OFS=-4`.
- Why the two offsets matched: `high_at()` first ranks legal 4-bar boundaries by "thinness" (neither top end thin next to the swap), and only then by distance to `c+HOFS` / `c-HOFS`. On this cohort the least-thin legal bar was uniquely 4 bars before the bass swap, so the offset never acted. This run does not test "highs 8 bars after the swap" vs "highs 4 bars before."

### Official `v1` highlights (higher = better)

Biggest wins (all train): `hybrid_minds_ukf__13` 33.72 → 43.81 (**+10.09**); `joe_syntax_hospital__14` 28.87 → 32.39 (+3.52); `joe_syntax_hospital__12` 32.29 → 35.59 (+3.30, matches the smoke); `hybrid_minds_ukf__23` 31.77 → 34.38 (+2.61); `hybrid_minds_ukf__11` 34.15 → 36.61 (+2.46); `hybrid_minds_ukf__00` 29.45 → 31.17 (+1.72).

Biggest losses: `hybrid_minds_ukf__09` (train) 32.58 → 28.90 (**−3.68**); `netsky_hospital_classics__06` (test) 27.58 → 25.63 (−1.95); `pola_bryson_puzzlewood__04` (test) 34.12 → 32.49 (−1.63). Other test moves were small (`maduk_liquicity_lunar2025__02` +0.14, `__03` −0.05, `netsky_hospital_classics__17` +0.04, `pola_bryson_puzzlewood__02` −0.21).

### Official `v2` highlights

Biggest wins: `joe_syntax_hospital__12` 36.43 → 41.66 (+5.23); `joe_syntax_hospital__14` 32.29 → 37.21 (+4.92); `hybrid_minds_ukf__23` +3.22; `hybrid_minds_ukf__11` +2.41.

Biggest losses: `hybrid_minds_ukf__00` 39.22 → 32.07 (**−7.15**) even though official `v1` rose +1.72 on the same pair (placement parts `entry` 57.35 → 35.53, `gone` 30.62 → 3.90, `swap` 58.49 → 35.24; this pair also flipped under `MID_HOLD` yesterday). Then `hybrid_minds_ukf__09` −3.89; `netsky_hospital_classics__06` −1.92; `pola_bryson_puzzlewood__04` −1.64. Held-out official `v2` is the one split whose CI sits entirely below zero (−0.29 [−0.47, −0.09]).

## 4. Recommendation

**Needs more data. Keep the `HIGH_GATE` prototype, leave it off by default, do not write `rules.json`.**

- Official `v1` improved on train and is not clearly worse on held-out (CI includes 0), and the must-pass checks did not regress (`X1` still clean). That is enough to keep the flag, not enough to turn it on.
- Overall official `v1` (+0.50) and official `v2` (+0.07) CIs both include 0. Held-out official `v2` is slightly but clearly down.
- The offset arm of the experiment did not actually run: both declared `HIGH_OFS` values rendered the same mixes.
- Next useful step, when a render slot is free: either change how `high_at()` uses `HIGH_OFS` so the offset is not just a thinness tie-break, or listen to the large movers (`hybrid_minds_ukf__13`, `joe_syntax_hospital__12`, and the losses `hybrid_minds_ukf__09` / `netsky_hospital_classics__06`) before spending another full cohort.
