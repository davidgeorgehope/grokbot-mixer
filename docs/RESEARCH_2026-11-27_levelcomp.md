# Midnight Mixer Technique Research — 2026-11-27 (ET)

**Outcome: do not promote. `LEVEL_COMP` stays off by default. The official lows-dip hard check is unchanged.** `protrans/rules.json` and all engine defaults/thresholds are unchanged. Ridegate stays the default.

Official `v1` and official `v2` are **higher-is-better** similarity scores, not error metrics. A wrap-up that treated them as lower-is-better would flip the tiny `v1` train movement (34.17 → 34.14 looks like a win in that reading; it is a small loss). The numbers below are `lc_1127` minus `lcb_1127` (LEVEL_COMP on minus today's default).

## 1. What was tested

Chosen first because 3 of 5 default hard fails in the n1126 fresh set were pumping: `LEVEL_COMP=1` (`src2/level_comp.py`, off by default). The idea is to watch the *summed* level of the two decks, and where a predicted V-shaped dip exceeds a trigger (default 2.5 dB), pull the incoming fader forward just enough to refill it (capped, never above unity, outgoing lane untouched). Hooked through `mix_simple.py` and `recreate.apply_rules` (`LEVEL_COMP`, `LEVEL_COMP_TRIG`, `LEVEL_COMP_CAP`). Temp rules only (`/tmp/rules_levelcomp_1127.json`). `rules.json` was never written.

Job `levelcomp-cohort-1127` (`protrans/research_1127/eval_levelcomp.sh`, `done rc=0` at 12:42 AM ET) rendered a like-for-like 33-pair cohort, same windows as the base:

- `lcb_1127` — current rules (ridegate default, `LEVEL_COMP` unset)
- `lc_1127` — `LEVEL_COMP=1`

Then `eval_tailexit.py`, official `v2` (`official_v2-place8c` via `protrans/research_1126/eval_v2.py`), and official hard checks (`research_1127/hardcheck_levelcomp.json`).

A second thread, n1127 priority (a), recalibrated a bass-hole *detector* (not a render change): jobs `hchole90-1127` and `hchole150-1127` (`replica/hchole_1127.py`, both `done rc=0` at 1:41 AM ET) on the `lcb_1127` default renders. See section 5.

No fresh-set re-render: the n1127 nightly render slot was in use, and the official cohort already rules out a ship-it.

## 2. Cohort results (33 pairs: 21 train / 12 held-out test)

CIs are 4000-draw mix-grouped bootstrap deltas vs `lcb_1127` (seed from `promotion_judge.py`). Train is only 2 mixes. **Higher is better.**

| Variant | `v1` Train | `v1` Held-Out | `v1` All | `official_v2` Train | `official_v2` Held-Out | `official_v2` All | Must-Pass (`eval_tailexit`) |
|---|---:|---:|---:|---:|---:|---:|---|
| `lcb_1127` (default) | **34.17** | 33.91 | 34.07 | 33.93 | 31.72 | 33.12 | **29/33** (test 10/12, train 19/21: `L1:2`, `N1:2`, `X1:0`) |
| `LEVEL_COMP=1` (`lc_1127`) | 34.14 (−0.02 [−0.036, −0.001]) | 33.94 (+0.03 [0.0, +0.07]) | 34.07 (−0.00 [−0.03, +0.04]) | 34.42 (+0.50 [−0.0, +0.80]) | 31.73 (+0.01 [0.0, +0.01]) | 33.44 (+0.32 [−0.0, +0.65]) | **20/33** (test 7/12, train 13/21: `X1:10`, same `L1:2` `N1:2`) |

Official `v1` changed on **9/33** pairs (4 up, 5 down, 24 unchanged). Official `v2` moved on the same 9. The train official `v2` lift is almost entirely one pair: `hybrid_minds_ukf__45` 41.74 → 52.54 (**+10.80**) while official `v1` on that pair fell 41.60 → 41.07 (−0.53) and the pair newly failed `X1`. Drop that pair and train official `v2` is 33.54 → 33.51.

Must-pass `X1` is a fader-step check: "gain moves 4.6 dB within 1 beat." The incoming pull-forward tripped it on 10 pairs (9 of them newly failed the must-pass set; `hybrid_minds_ukf__10` already failed `L1` on the default). New `X1` fails: `hybrid_minds_ukf__12`, `__19`, `__23`, `__40`, `__45`, `joe_syntax_hospital__11`, `maduk_liquicity_lunar2025__02`, `__05`, `netsky_hospital_classics__06`, plus `__10`.

Official hard checks (pump / bass hole / clash / vanish) were **unchanged**: 3 hard fails on both arms (`hybrid_minds_ukf__23` pump 5.1, `__40` pump 5.0, `pola_bryson_puzzlewood__00` lows dip 45.4). Mean `pump_db` 2.25 both sides. The pumping that motivated the experiment did not move.

### Official `v1` / `v2` movers (higher = better)

Largest `v2` win: `hybrid_minds_ukf__45` +10.80 (`v1` −0.53, new `X1`). Largest `v1` win: `netsky_hospital_classics__06` 17.66 → 18.06 (**+0.40**, also a new `X1`). Next: `hybrid_minds_ukf__10` `v1` +0.18, `v2` −0.22. Largest `v1` loss after `__45`: `hybrid_minds_ukf__12` −0.13. Other moves were ±0.05 or smaller.

## 3. What actually changed in the render

`LEVEL_COMP` left windows alone and rewrote the incoming gain lane on the pairs where a predicted summed-level V-dip exceeded the trigger. That refill is what produced the 4.6 dB-in-one-beat `X1` steps. Dip median and banger-clash rate in `eval_tailexit` stayed 24.6 dB and 0.1004.

## 4. Recommendation

**Do not promote. Keep the `LEVEL_COMP` prototype, leave it off by default, do not write `rules.json`.**

- Official `v1` is not better (train CI sits entirely below zero, though the effect is tiny; held-out and overall CIs include 0).
- Official `v2` is not a clear win (overall CI includes 0; the train mean is one pair).
- Must-pass checks got worse (29/33 → 20/33) because of new `X1` fader steps. That is a new audible-style fault, not fewer hard fails.
- Official pump / hole hard fails did not improve.
- the listener's ship-it rule (meaningfully better on dev+fresh, fewer hard fails, no new audible faults) is not met. No default change, no rollback line needed.

Next useful step, when a render slot is free: rate-limit or ramp the incoming boost so it cannot move 4.6 dB in one beat, then re-check `X1` before spending another full cohort. Do not turn the flag on as-is.

## 5. Bass-hole detector (`hchole90` / `hchole150`)

The official lows-dip measure (max summed lows in the 2 bars before the blend, minus the min anywhere in the blend; p95 45.34 dB) also counts planned breakdowns, so it almost never flags an injected 4- or 8-bar hole (1/33, the already-failing `pola_bryson_puzzlewood__00`).

Candidate `lows_hole` (`replica/hchole_1127.py`): a width-aware V-dip of the summed lows *inside* the blend (a hole that comes back is scored; a lows drop that never returns is not). Threshold = pro p95 of the same measure on the 33 pro clips, same windows as `calib_pro`. Evaluated on `lcb_1127` renders, clean vs injected `hole4` / `hole8` (same injection as `hcinject`).

| Band | Pro p95 | Clean flags (official / new) | Injected hole4 | Injected hole8 |
|---|---:|---:|---:|---:|
| 90 Hz | 25.21 dB | 1/33 / **6/33** (0.182) | 1/33 / **25/33** (0.758) | 1/33 / **20/33** (0.606) |
| 150 Hz (official low band) | 30.7 dB | 1/33 / 1/33 (0.03) | 1/33 / 1/33 | 1/33 / 1/33 |

At 150 Hz the candidate matches the official flag rate and also misses the injections: a 4th-order 150 Hz low-pass still leaks 150–300 Hz kick/bass harmonics into the official band, so the cut is hard to see there. At 90 Hz (below that injection edge) it catches most injected 4-bar holes, but it also flags 5 default renders that official does not (`hybrid_minds_ukf__00`, `__09`, `__12`, `__25`, `wilkinson_boomtown2026__33`, plus the real `pola_bryson_puzzlewood__00` hole). That is too many false alarms to replace the official check.

**Leave the official lows-dip hard check alone.** A later pass can try the 90 Hz measure with a higher bar than the pro p95, or an injection whose corner sits well inside the official band. Do not change `hardcheck_calib.json` from this run.

## 6. What's next

1. If `LEVEL_COMP` is retried, make the incoming pull monotone *and* beat-rate limited so `X1` stays clean, then re-run the 33-pair cohort (and only then consider fresh).
2. Keep `lows_hole` as a research detector; do not swap it in for official `lows_dip` until false alarms on clean default renders are in line with the pro p95 policy.
3. The n1127 nightly / hill-climb was left running and was not used as a render slot for this wrap-up.
