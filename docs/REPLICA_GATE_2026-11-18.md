# REPLICA=gated, pro-decision eval, and what to try next (2026-11-18 night, ET)

All of this is behind flags. `protrans/rules.json` is unchanged: REPLICA is off, and the eval asserts that on startup.
Nothing was promoted. The pre-registered criteria in `protrans/replica/promotion_criteria.json` (written before the locked-holdout check) were not met.

## What was built
- `src2/replica_rule.py`:
  - `mode()` returns off, on or gated.
  - `gate()` passes a pair only when the primary sections detector finds two separate drops, the breakdown is at least 16 bars long, and the low band dips at least 6 dB versus drop 1. These a-priori constants are the sections.py drop margin and the minimum blend length.
  - `REPLICA_X` is a research override for blend length.
  - Hooks are in `src2/mix_simple.py` (via `engine_cands`) and `protrans/recreate.py`. In gated mode there's no fine-fallback breakdown.
- `protrans/replica/hardcheck.py` has three hard checks:
  - **Beat clash:** halfbeat fail, or BLEND_LOCK's own confident 15–150 ms lag still present on the final decks.
  - **Bass hole:** summed-lows dip in the blend, threshold set at the pro p95 of 45.3 dB.
  - **Pumping:** V-dip in the full-band level, threshold set at the pro p95 of 4.54 dB.
  - The p95s come from the 33 pro clips and are stored in `hardcheck_calib.json`.
  - The same file measures our decisions in the pro's terms: exit and cue bar at audible entry, overlap, swap bars after entry, and fader curves.
  - **Caveat:** in the judge pilot these checks missed most injected bass holes and clashes. A "pass" is weak evidence.
- `eval_gate.py` renders each variant through the real engine, checkpointed to `gate_ckpt/<variant>.jsonl`.
- `analyze.py` reports grouped (by-mix) bootstrap CIs.
- `policy.py` holds the nested leave-one-DJ-out chooser (logistic regression; inner CV picks C and the conformal level), plus split-conformal abstention, the baselines and tolerance hit rates.
- `tight_gate.py` does a nested-CV gate search.
- `relabel.py` does the DAgger-style relabel.
- `melclose.py` computes mel and chroma closeness to the pro audio.
- `fresh_mixes.py` collects fresh test mixes. It now uses isolated work dirs.

## Data and splits
- Eval set frozen at 20:31 ET (`frozen_ids.json`): 103 pairs, made up of the 33 protrans pairs plus 70 corpus_v2 transitions with local audio.
- The other ~19 corpus rows had no local sources and were not used.
- **Locked final holdout:** the Liquicity and Hospital Records corpus mixes, picked at random with seed 20261118 before any results (`holdout.json`). 12 pairs, 4 mixes, checked once.
- **Dev:** 91 pairs, 18 mixes, 11 DJs. Outer CV is leave-one-DJ-out.
- **Fresh mix:** John B "Night Drive DnB" (frbb5gILfjo), 6 admitted transitions, ingested after the freeze. It was not used for fitting.
  - A second fresh mix was still ingesting at report time.
  - The John B pairs have now been looked at for diagnosis, so they no longer count as an unseen test.

## Results
Errors are in bars against the pro. Deltas are variant minus default, with grouped bootstrap 95% CIs. "Better" means the CI excludes 0.

### Dev (91 pairs, outer leave-one-DJ-out)

| policy | exit median | exit hit @4/8/16 | cue hit @16 | exit+cue delta vs default [CI] | hard fails |
|---|---|---|---|---|---|
| default | 49.1 | .01/.02/.19 | .64 | – | 18 |
| always replica (REPLICA=1) = majority | 31.5 | .12/.17/.31 | .54 | −4.8 [−14.1, 8.2] | 30 |
| REPLICA=gated (a-priori gate, 80/91 used) | 34.0 | .12/.17/.30 | .53 | −3.7 [−13.1, 9.1] | 29 |
| learned + conformal, no style (abstains 68%) | 60.5 | .02/.06/.17 | .59 | +1.8 [−3.9, 10.0] | 22 |
| learned + conformal + style setting (abstains 46%) | 20.6 | .11/.13/.35 | .62 | **−8.8 [−12.9, −4.0]** | 25 |
| learned plain + style setting | 17.4 | .12/.15/.41 | .60 | **−10.7 [−14.2, −6.5]** | 26 |

- The cue is consistently a little worse for every replica policy: +3.4 [1.2, 5.3]. The replica only moves the exit.
- Acceptable-set hit @16 (any section boundary within 8 bars of the pro counts) follows the same order: default .24, gated .31, style model .41.
- Conformal coverage was 0.66 without the style setting and 0.75 with it.
- **The style-setting variant wins only when it gets one bit per mix: "does this DJ exit mid-track?"** That bit is taken from that mix's own pros, so it needs a real per-mix setting from the listener. Without it, the learned chooser doesn't beat the default.

### Locked holdout (12 pairs, 4 mixes, checked once)
- Default: exit median 26.1, exit hit@16 0.17, 0 hard fails.
- Gated: exit+cue −6.0 [−14.4, 4.6], exit hit@16 0.33, 0 hard fails.
- Style + conformal: −7.9 [−14.4, 0.0], hit@16 0.42, abstains 67%.
- Nothing has a CI that excludes 0, so there's no win.

### Fresh mix (6 John B pairs; 1 group, so no CI is possible)
- Default exit+cue mean is 34.0. Gated and always-replica are worse at 44.3 (+10.3). The style model is worse at 41.7. Conformal without style is worse at 43.3.
- The gate applied the replica on 5 of 6 pairs.
- John B rides the outro much like Alpha Rhythm. The breakdown exit was 47, 90, 54 and 74 bars off the pro on 00, 05, 06 and 14 (default: 15, 30, 10, 38). Pair 01 was the only exit hit, 1 bar off.
- This is the same failure as Alpha Rhythm in dev: technique is DJ habit, and the track structure can't tell you which habit applies.

### Hard checks (103 pairs, per pair, deduped)
- Default fails 18: 7 beat clash, 3 bass hole, 9 pumping.
- REPLICA=1 fails 30: 19 new versus default, 7 fixed, 11 shared.
- Gated fails 29: 18 new (all on pairs where the window changed), 7 fixed.
- The new fails are mostly pumping and bass hole, which fits the shape: leaving at a breakdown blends two thin sections.
- Fresh: default and gated each fail 3/6, on different pairs.

### Tightened gate (`tight_gate.json`)
- Nested leave-one-DJ-out over a 60-point grid: minimum dip 6–18 dB × minimum breakdown length 16–32 bars × minimum breakdown position 0–0.5.
- Constraint: no more new hard fails than fixed ones.
- In 10 of 11 folds no setting qualified, so the gate abstains, which means the default.
- Result: exit+cue −0.7 [−2.2, 0.0], with 2 replica uses. On all dev data the selection also returns "none".
- **So the honest confidence gate, under the hard-check rule, is "never".** Structural confidence alone can't make the breakdown exit safe.

### Ideas tried (27 protrans pairs where the gate passes; these are dev pairs, not held out)
- (a) `gcover` (gated + BASS_COVER=1):
  - The exit is the same as gated.
  - Hard fails dropped from 13 to 11 (fixed ukf__10, ukf__23, maduk__03; broke ukf__28).
  - Lows-dip median went from 30.4 to 27.3 dB.
  - Overlap and fade were unchanged.
  - It helps but doesn't get back to the default's 8 fails, so it's not kept.
- (a) An earlier swap wasn't run as its own variant. Swap error is 7 bars median for every variant, and pros swap about 1 bar after entry. That's still open.
- (b) DJ style as an input: this is the only thing that beats the default in dev (table above). It's not significant on the holdout, and it needs a real style setting.
- (c) `gx32` (REPLICA_X=32, so longer blends like the pros' median overlap of 34 bars):
  - Overlap −0.6 and fade −0.4 versus gated, both CIs include 0.
  - Hard fails went from 13 to 14.
  - It loses.
- Per-bar pro deck curves exist for only 11 corpus transitions plus the 33 protrans pairs. The fade-shape error is about 6.3 dB for every variant, so the fade shape isn't what separates us from the pros yet.

### DAgger relabel (`relabel_dev.jsonl`, 186 rows)
- The default exit lands in the pro's section only 25 of 91 times. Gated does the same at 24 of 91.
- Default misses, ours → pro: outro → drop1 (21), outro → breakdown (14), outro → drop2 (12).
- Gated misses: breakdown → drop1 (24), breakdown → outro (15), breakdown → drop2 (14).
- Cue: 20 of the 27 misses are ours in the intro while the pro came in at the incoming's drop1 (a drop-on-drop / mid-track cue). The engine never proposes that cue.
- **Next idea:** add drop1-exit and drop-cue candidates, plus a style setting, and score them the same way.

### Audio closeness to the pro (diagnostic only; ViSQOL not installed)
- Over 33 protrans pairs, mel distance is 6.74 dB for default and 6.72 for gated.
- Chroma distance is 0.206 for default and 0.221 for gated.
- No meaningful difference.

## Incidents
- The `rubberband` CLI was missing on the box, so 25 corpus default renders failed. I installed the Debian .deb at 20:51 ET and re-rendered them (`replica-fill-1118`).
- **The fresh-mix ingest shared `corpus_v2/work/lib` with the running corpus-v2 job.** `archive_mix()` deletes every .m4a there. At about 21:57 ET it removed sources corpus-v2 was using, and `mrmommusic_nodB5gqt_mU__49` was rejected on a missing file. That reject is spurious and should be retried.
- I killed that fresh job and restarted it as `replica-fresh2-1118` with isolated dirs (`replica/fresh_work`, sources in `replica/fresh_src`).

## FYI blind clips (not a decision step)
- These are gated vs default on two pairs the listener hasn't heard, where both versions pass the hard checks and the gate's exit is closer to the pro.
- Pairs: netsky_hospital_classics__17 (exit error 146.6 → 45.4) and pola_bryson_puzzlewood__02 (59 → 21, but the cue is worse, 22 → 38).
- Files are in `deliver/research/2026-11-18/replica_gated/` (mp3 + png + json). The key is in `/workspace/private/research_2026-11-18_replica_gated_key.json`.
