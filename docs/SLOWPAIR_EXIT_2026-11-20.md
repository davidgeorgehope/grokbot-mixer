# SLOWPAIR exit-only (2026-11-20)

**`protrans/rules.json` is unchanged.** `SLOWPAIR` and `SLOWPAIR_EXIT` stay off by default. This arm only does Case A exit moves; Case B cue moves are off.

## What was tried
- The combined `SLOWPAIR=1` flag lost (held-out 32.11 vs 34.07) after 11 picks moved. The likely drag was Case B cue moves that fight the outro-over-intro default.
- Exit-only (`SLOWPAIR=1`, `SLOWPAIR_EXIT=1`) keeps the hard-span detector and Case A (start inside, or at least 12 bars of, an outgoing hard outro / in-drop). Starting a few bars before the slowdown is still allowed. Case B is ignored.
- Two bases: the current default, and epg_stack (`EXITPOS` + `EXITPOS_GATE` + `EXITPOS_DROP`), because drop-fade exits were preferred 5/5 on listening.
- Same 33-pair cohort and scorer. Mix-grouped bootstrap CIs (4000, seed 20261119) of arm minus the parent. Official hard-fail is HC_A / HC_B v2 on moved windows (unchanged windows keep the parent result).

## Results

| variant | held-out | train | n | n_fail | pairs changed | held-out CI (arm − parent) |
|---|---:|---:|---:|---:|---:|---|
| bfb1120_base (current rules) | **34.07** | **32.4** | 33 | 0 | 0 | — |
| spex1120_def | 32.28 | 32.91 | 33 | 0 | 3 | -1.786 [-3.572, 0.0] incl0=True |
| spex1120_stk | 33.2 | 32.97 | 33 | 0 | 1 | -0.706 [-1.412, 0.0] incl0=True |
| n1120_epg_stack (parent of the stacked arm) | 33.91 | 32.97 | 33 | 0 | 0 | — |

### On the current default (`spex1120_def`)

Decision: **lose**. Case A clashes on the parent window: 3 of 33 (held-out 2 of 12). Picks moved: 3 (held-out 2).

Hard-fail (HC_A / HC_B v2, 33 windows with a known parent and arm result; 0 unchanged windows had no cached flags and were not re-rendered): parent 8 → arm 7 (HC_A 7→6, HC_B 6→6). New fails: none. Fixed: ['joe_syntax_hospital__12']. Leave-one-DJ-out fail-delta range: [-0.05, 0.0].

Changed pairs (parent → exit-only, score parent → arm):

- `netsky_hospital_classics__17` (test, A): `['n', 256, None, 32, 16]` → `['la', 240, 224, 64, 16]` , 33.35 → 20.39 (Logistics - Together -> Apex - Just One Second (London Elektricity Remix))
- `joe_syntax_hospital__12` (train, A): `['n', 224, None, 48, 16]` → `['la', 176, 160, 16, 16]` , 32.29 → 42.85 (Cyantific - Ghetto Blaster -> S.P.Y - Seconds To Midnight)
- `netsky_hospital_classics__15` (test, A): `['n', 240, None, 0, 16]` → `['la', 192, 176, 16, 16]` , 40.9 → 32.43 (Netsky - Memory Lane -> Netsky - The Whistle Song)

Placement (pro vs parent vs exit-only). Bars are each track's own bars; out_time / in_time are track time at the blend start / cue; mix_time is the pro set time when known.

#### `netsky_hospital_classics__17` — Logistics - Together -> Apex - Just One Second (London Elektricity Remix) (test, 33.35 → 20.39)

| who | exit_bar | cue_bar | blend_start_bar | out_time | in_time | mix_time | out_start_section | in_start_section | out_last_drop_played | ht_out | ht_in | why |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pro | 128.4 | 14.6 | 94.4 | 2:10 | 0:20 | 45:14 | drop 2 | intro | cut 146 bars early | slowdown 114-122 overlaps 8 bars; slowdown 125-159 overlaps 3.4000000000000057 bars | slowdown 46-62 overlaps 2.6000000000000014 bars | what the DJ did |
| bfb1120_base | 256 | 32 | 240 | 5:31 | 0:44 | None | outro + slowdown/half-time | intro | all | slowdown 234-257 overlaps 16 bars | slowdown 46-62 overlaps 2 bars | outgoing hard slow 234-257 (in_drop,outro), overlap 16 bars, blend starts inside it |
| spex1120_def | 240 | 64 | 224 | 5:08 | 1:28 | None | drop 3 + slowdown/half-time | drop 1 | cut 16 bars early | slowdown 218-231 overlaps 7 bars; slowdown 234-257 overlaps 6 bars |  | outgoing slow 234-257 grazes 6 bars (under the Case A cover) |

#### `joe_syntax_hospital__12` — Cyantific - Ghetto Blaster -> S.P.Y - Seconds To Midnight (train, 32.29 → 42.85)

| who | exit_bar | cue_bar | blend_start_bar | out_time | in_time | mix_time | out_start_section | in_start_section | out_last_drop_played | ht_out | ht_in | why |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pro | 208.0 | 140.0 | 189.0 | 4:20 | 3:13 | 34:52 | drop 2 | breakdown + slowdown/half-time | blend starts 3 bars before its end | slowdown 198-235 overlaps 10.0 bars | slowdown 129-162 overlaps 19.0 bars | what the DJ did |
| bfb1120_base | 224 | 48 | 208 | 4:46 | 1:06 | None | outro + slowdown/half-time | intro | all | slowdown 198-235 overlaps 16 bars |  | outgoing hard slow 198-235 (outro), overlap 16 bars, blend starts inside it |
| spex1120_def | 176 | 16 | 160 | 3:40 | 0:22 | None | drop 2 | intro | cut 32 bars early |  |  | no hard-span clash |

#### `netsky_hospital_classics__15` — Netsky - Memory Lane -> Netsky - The Whistle Song (test, 40.9 → 32.43)

| who | exit_bar | cue_bar | blend_start_bar | out_time | in_time | mix_time | out_start_section | in_start_section | out_last_drop_played | ht_out | ht_in | why |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pro | 243.4 | 0.2 | 203.4 | 4:40 | 0:00 | 38:59 | drop 2 | intro | blend starts 37 bars before its end | slowdown 222-242 overlaps 20 bars |  | what the DJ did |
| bfb1120_base | 240 | 0 | 224 | 5:08 | 0:00 | None | drop 2 + slowdown/half-time | intro | cut 16 bars early | slowdown 222-242 overlaps 16 bars |  | outgoing hard slow 222-242 (in_drop,outro), overlap 16 bars, blend starts inside it |
| spex1120_def | 192 | 16 | 176 | 4:02 | 0:22 | None | drop 2 + slowdown/half-time | drop 1 | cut 64 bars early | slowdown 166-177 overlaps 1 bars |  | no hard-span clash |

### On epg_stack (`spex1120_stk`)

Decision: **lose**. Case A clashes on the parent window: 1 of 33 (held-out 1 of 12). Picks moved: 1 (held-out 1).

Hard-fail (HC_A / HC_B v2, 33 windows with a known parent and arm result; 0 unchanged windows had no cached flags and were not re-rendered): parent 5 → arm 5 (HC_A 4→4, HC_B 5→5). New fails: none. Fixed: none. Leave-one-DJ-out fail-delta range: [0.0, 0.0].

Changed pairs (parent → exit-only, score parent → arm):

- `netsky_hospital_classics__15` (test, A): `['n', 240, None, 0, 16]` → `['la', 192, 176, 16, 16]` , 40.9 → 32.43 (Netsky - Memory Lane -> Netsky - The Whistle Song)

Placement (pro vs parent vs exit-only). Bars are each track's own bars; out_time / in_time are track time at the blend start / cue; mix_time is the pro set time when known.

#### `netsky_hospital_classics__15` — Netsky - Memory Lane -> Netsky - The Whistle Song (test, 40.9 → 32.43)

| who | exit_bar | cue_bar | blend_start_bar | out_time | in_time | mix_time | out_start_section | in_start_section | out_last_drop_played | ht_out | ht_in | why |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pro | 243.4 | 0.2 | 203.4 | 4:40 | 0:00 | 38:59 | drop 2 | intro | blend starts 37 bars before its end | slowdown 222-242 overlaps 20 bars |  | what the DJ did |
| n1120_epg_stack | 240 | 0 | 224 | 5:08 | 0:00 | None | drop 2 + slowdown/half-time | intro | cut 16 bars early | slowdown 222-242 overlaps 16 bars |  | outgoing hard slow 222-242 (in_drop,outro), overlap 16 bars, blend starts inside it |
| spex1120_stk | 192 | 16 | 176 | 4:02 | 0:22 | None | drop 2 + slowdown/half-time | drop 1 | cut 64 bars early | slowdown 166-177 overlaps 1 bars |  | no hard-span clash |

## Clips

No clips: neither arm was not-worse on held-out against the 34.07 floor with no new hard fails, or no pair moved.

## Ranker features

Slow-pair and hard-section flags are in `/workspace/mixes/protrans/ranker/slowpair_features_1120.json` (`sp_case_a`, `sp_case_b`, cover, start-inside, incoming overlap, outgoing-hot, half-time, outro / in-drop / intro flags). The live v0 ranker feature width is unchanged; no retrain was run.

## Code

- `src2/slowpair.py` — `SLOWPAIR_EXIT=1` / `allowed_cases()` (Case A only)
- `protrans/recreate.py` — exports `SLOWPAIR_EXIT` when a trial sets it
- `protrans/eval_slowpair_exit.py`, `protrans/eval_slowpair_exit.sh`
- `src/tests/test_slowpair.py`
- `src2/learned_ranker.py` — `SLOWPAIR_FEATURE_NAMES` (retrain helper only)
- Flags off by default; do not put `SLOWPAIR` or `SLOWPAIR_EXIT` in `rules.json`

