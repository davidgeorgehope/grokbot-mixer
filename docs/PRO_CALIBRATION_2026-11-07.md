# Pro calibration 2026-11-07 (America/New_York)

37 admitted pro transitions from `protrans/results/admitted.json`.

## Non-phrase energy drop (`checks.DROP_DB`)

the listener heard the Mix 07 r12 Just Hold On → Solitude 6.2 dB dip and called it fine, so the 6.0 dB gate was over-strict.

| threshold | pro transitions passing |
|---|---|
| 6.0 dB (old) | 27/37 (73%) |
| 12.2 dB (p95, new) | 35/37 (~95%) |

Per-transition max non-phrase drop among the 37: p50=0.0, p90=9.58, p95=12.2, p100=14.98 dB.

The 10 that fail at 6.0 dB: 6.04, 6.26, 7.44, 7.75, 8.01, 9.52, 9.66, 11.93, 13.27, 14.98
(hospital_podcast393__04, joe_syntax_hospital__00/08/11/13, hybrid_minds_ukf__11/19/20, netsky_hospital_classics__17/24).

`DROP_DB` set to **12.2**. This does not loosen a check that pros already passed cleanly.

## Beat / downbeat phase (`test_mixdown_beats_aligned_every_overlap_bar`)

10 ms `TOL_DRIFT_MS` is **unchanged**. Pros were not used to widen the millisecond gate.

The Mix 07 r12 Daydreaming → Parallel clip (`deliver/ab/mix07r12_grid_Parallel_25m23.mp3`) is a heard trainwreck that the old check reported as a single bar at −11 ms. Cause:

- `bar_alignment_report` searched only ±40 ms, so a 1-beat (345 ms) or half-bar (690 ms) error collapsed to a local peak near 0 ms.
- Rows with corr < 0.65 were dropped, so most of the clash was invisible.
- Each deck was compared only to its own source. Once Parallel dominates the fade, it matches itself at ~0 ms even while it is a half-bar/beat off Daydreaming.
- Guardrail F1 folds phase into a 16th-note period, which also hides whole-beat and half-bar errors (N sixteenths ≡ 0).

Clip kick-onset autocorr during the blend: 1-beat ac=0.029 vs 1.5-beat ac=0.452.

The detector now:

1. Searches ±40 ms around 0 **and** around ±1..4 beats.
2. Treats audible low-corr mix-vs-source bars as failures (`CORR_MIN=0.65`).
3. Adds an inter-deck planned-source phase row (fail if corr ≥ 0.35 and |lag| > 10 ms).

Regression: `src/tests/test_phase_trainwreck.py` (this clip must fail loudly).

## Detector follow-up (same day, after r17)

Beat-align under-report on the heard Daydreaming→Parallel trainwreck (`deliver/ab/mix07r12_grid_Parallel_25m23.mp3`):
old check searched only ±40 ms, dropped corr<0.65, and compared each deck only to the mix (the louder deck matches itself at ~0 ms). A 1-beat / half-bar / 1.5-beat error therefore hid as ~0 ms (r12 reported one bar at −11 ms). F1’s 16th-fold has the same hole.

Fixes in `src/tests/checks.py`:
- `DROP_DB=12.2` (p95 of 37 admitted pro non-phrase drops; 35/37 ≈ 95% pass). JHO→Solitude 6.2 dB is now in range. `TOL_DRIFT_MS=10` unchanged.
- Mix-vs-source searches ±40 ms around 0 and around ±1..4 beats. Fail a bar when 0 cannot lock within 10 ms (`corr_0 < 0.65` and `|lag_0| > 10`), or when an *odd-beat* (1, 3, or half-beat 0.5/1.5) peak is the lock and 0 is not. Even-beat 2/4 peaks are DnB snare/bar aliases and are not fails by themselves.
- Inter-deck source-vs-source is recorded but not used as a hard fail (two different tracks’ drums often xcorr better at ±1/±3 even when each is correctly locked to the mix).
- Off-by-one mix-window length (`int(bar*BAR*fr)` vs `nb*round(BAR*fr)`) no longer skips every lag and returns corr=−1e9.
- `transitions()` downbeats use the fine ±40 ms search (a ±3-beat default was reporting +328 ms / 1-beat aliases at corr 0.52).
- Regression: `src/tests/test_phase_trainwreck.py` on the r12 Parallel clip (restores `C.onset` after).

Pro corpus re-run (`mix07/pro_phase_check.py`): energy 34/37 (91.9%) at 12.2 dB (fails: hybrid_minds_ukf__11 14.98, __20 16.01, joe_syntax_hospital__13 13.27). Presence-proxy overlap on isolated clips produced 32/37 empty align rows — not equivalent to planned-deck mix checks. Did not write `protrans/rules.json`.

r17 mixdown still had 20/914 mix-vs-source flags on *other* pairs (mid-fade low-corr / leftover odd-beat aliases). Day-Par bars 1088–1104 were not among them.

## End-of-overlap tail / rolling window (same day, after the listener’s listen)

the listener listened again: the r12 Daydreaming→Parallel trainwreck is only in the **last ~5 bars** of the overlap; the rest of the blend is fine. The failure mode is end-of-overlap drift or phase slip (tempo ramp, loop splice, `swap_pos`, or a grid ending), not a whole-overlap 1-beat flip. The six r17 phase-flag clips he heard (Trip→Souvenirs, Souvenirs→White Lies, Parallel→Inside, Inside→Ember, Skyline→When My Love, Sweet Lies→Just Hold On) are **not** trainwrecks.

### r12 tail root cause vs r17

r12 used `la 128,112,0,16`: Daydreaming plays to bar 128, then **loops phrase 112–128** under the blend while Parallel’s **intro 0–16** comes in. Last 5 overlap bars are mix 1115–1119 = Day source 123–127 (nudges +11…+13 ms) over Parallel source 11–15 (nudges bar 11: −24 ms, bar 12: −22 ms). Mix-vs-Parallel on those tail bars:

| mix bar | Parallel `lag_0` | `corr_0` | notes |
|---|---|---|---|
| 1115 | −24 ms | 0.62 | fail (tail floor 0.55) |
| 1116 | −14 ms | 0.73 | fail; xcorr also prefers a 2-beat alias at −702 ms |
| 1117 | −9 ms | 0.86 | pass |
| 1118 | −6 ms | 0.93 | pass |
| 1119 | −4 ms | 0.97 | pass |

Early-overlap Day lock on the same clip is −0 to −3 ms at corr 0.93–0.99 — matching “the rest was fine.”

r17 uses natural `n 128,32,16` (no loop) with per-plan `swap_pos=0.25`, landing Parallel’s **drop** (32–48), not the intro. Last 5 bars are mix 1099–1103 = Day 123–127 over Parallel 43–47 (those Parallel bars have no intro nudges). Mix-vs-Parallel tail: −4…+1 ms at corr 0.99–1.0. The loop-over-intro pairing and the opposing tail nudges are gone.

### Detector (still 10 ms `TOL_DRIFT_MS`)

`bar_alignment_report` already scored a rolling 2-bar window per mix bar; it now also scores the **last overlap bar** (`nb=1`) so the tail is not cut off by the window. There is **no overlap-wide average**.

`alignment_failures`:

1. Inter-deck source-vs-source is recorded, not a hard fail.
2. `corr_0` below the audible floor is **no-info** (skip), not a fail. Body floor `CORR_MIN=0.65`; last `TAIL_BARS=5` use `TAIL_CORR_MIN=0.55` so a late fade that still locks (r12 bar 1115 at 0.62 / −24 ms) cannot hide.
3. An audible bar (`corr_0` ≥ floor) with `|lag_0| > 10` ms fails (drift / phase slip).
4. A stronger odd-beat xcorr peak while `|lag_0| ≤ 10` ms is a DnB alias, not a fail (r17 Parallel→Inside bar 1211: `lag_0=−2` ms / `corr_0=0.62` vs a 3-beat peak at 0.79). Even-beat 2/4 peaks are likewise aliases.

Regression `test_phase_trainwreck.py` now asserts at least one **tail** mix-vs-source `|lag_0| > 10` ms failure on the r12 clip (bars 1115 and 1116).

### Pass rates under this gate

| corpus | result |
|---|---|
| r12 Daydreaming→Parallel clip (heard trainwreck tail) | fail (2 tail bars: 1115 −24 ms / 0.62, 1116 −14 ms / 0.73) |
| 6 heard-OK r17 phase clips / their overlap tails | 6/6 pass |
| r17 all 22 planned overlaps (snippet-checked, including Day→Par tail) | 22/22 pass |
| 37 admitted pro transitions, planned decks + real sources | clip-level 8/37 (21.6%) pass if *any* audible bar with `|lag_0|>10` fails the clip; bar-level 2816/3054 mix-vs-source bars pass (92.2%). 28/37 clips have no tail fail. Many recorded fails sit at the ±40 ms search edge (e.g. `lag_0=±40` at corr 0.65–0.75) and look like locate/window-edge residuals rather than heard trainwrecks. 10 ms TOL was not widened. |

Did not write `protrans/rules.json`.
