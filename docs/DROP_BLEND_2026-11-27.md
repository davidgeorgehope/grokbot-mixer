# The 11-27 drop-over-drop blend: what made it, and whether the picker can learn it (2026-11-27)

the listener's verdict on the 11-27 daily blind test (`joe_syntax_hospital__00`, Fred V & Grafix "Find My Way" into Nu:Tone "The Feeling"): ours (clip B) was "honestly awesome, way better than the pro", and he asked for "more of that". Per his 6:03 PM redirect, **no hand-coded style, candidate or weight was added**. No default change was made.

## What our blend did

- Window `['n', 112, None, 32, 16]`. A plays bars 96 to 112, which is its last 12 drop bars plus its 4-bar outro, so it runs to the end of the track. B comes in at bar 32 of its drop 1 (16 to 47), and the blend ends right as B reaches its breakdown at bar 48. For 16 bars both tracks are in their drops, and then B drops into its breakdown the moment A is gone.
- Curves (meta `lcb_1120`): B's fader is up within about 2 bars. A sits near −2.5 dB until bar 104, then fades slowly to about −23 dB at bar 112. A's >2 kHz band swaps out over 100 to 102, and the lows swap over 101 to 105 (BASS_SWAP_BARS 3, SWAP_POS 0.21). The summed lows dip about 9 dB with no hole. Mid-blend beat offset reached about ±150 ms and passed the lock preview.
- Code path: the `ridegate_live` family, from the default live pack (`ridegate_live_pack`, n1126). With RIDEGATE off, the engine picks `nat_short` instead (29.36 vs 40.96).

## Which learned signals made it (LightGBM contributions, `prefs_1127/explain.py`)

- **Exit ranker**: picked exit 97 over the default 81. The main reasons are that only 15 bars are left, so A plays to its end (+0.44), the later bar (+0.25), the distance from drop start (+0.21), and that the window ends in the outro (+0.17). The ride gate is irrelevant here: the exit is not "mid-track", and p_leave is 0.18.
- **Cue ranker**: picked cue 33, a plain 16-bar grid candidate, over the default 1. The reasons are its relative position, 19% into B (+0.95), and being 17 bars past B's drop-1 start (+0.20).
- **Length**: 16 is the engine default, not a model choice.
- **Fade shape**: the global `rules.json` constants (FADE long, LONG_XP 0.45, HIGH_OFS 8, ...), the same for every pair.

So the drop-over-drop result emerged from **two independent choices** that happened to line up. The cue model does not know that A is still in its drop.

## Structural problems (report, not fixed)

1. **Blend length is not learned live.** dX = 16 on 1,133 of 1,134 built dev/fresh/protrans pairs. Pro overlaps vary: on dev, 46% are ≤10 bars, 31% are about 16, and 23% are 32. The picker's `fitX` classifier exists but the live pack does not use it.
2. **Fade shape is global.** FADE, LONG_XP, HIGH_OFS, BASS_SWAP_BARS, SWAP_POS and TAIL_EXIT are single hill-climbed constants. Nothing chooses them per pair from track features.
3. **Exit and cue are ranked separately** over hand-built menus. Cues sit on a 16-bar grid plus section anchors, and drop+8, the most common pro cue in pro drop-over-drop blends, is not on the menu. No feature couples the cue to the chosen exit, so a coherent "both in drop" placement cannot be learned as such.
4. **The picker is unstable under retraining.** Adding any single row to the 1,001 dev rows changes about 30% of fresh decisions (three random duplicated dev rows: 32, 29 and 31 of 100 fresh flips). Retraining on the same rows reproduces the pack exactly (0 flips). Adding the listener's preference row flipped 22 of 100, the same size as noise. **So one listener verdict cannot be learned meaningfully by the current picker**, and many live decisions sit near ties.

## Preference signal, recorded

`protrans/replica/listener_prefs.jsonl` and `listener_prefs.py` turn a "preferred ours" verdict into a training row: the same built features, with labels set to our placement instead of the pro's. Today's verdict is entry 1. This has **no effect on the default pack** and is used only if a pack is trained with these rows. With one row, its measured effect is within retrain noise (above). For the 33-pair official set, it changed drop>drop from 9% to 12%, which is noise-level too.

## How often the current default does this style (decision level, before lock/pump previews)

The census classifies a window as "drop" when at least 75% of a deck's overlap bars are in its drops. The tool is `prefs_1127/census.py`.

| set | ours drop>drop | drop>in | out>drop | out>in | pro drop>drop |
|---|---|---|---|---|---|
| dev (in-sample, 1001) | 17% | 17% | 28% | 38% | 22% |
| fresh (100) | 12% | 20% | 26% | 42% | 24% |
| official 33 | 9% | 15% | 24% | 52% | 15% |

The locked holdout was not opened. Diversity is healthy, with no style above 52%. Pros blend drop-over-drop about twice as often as we do on fresh pairs. On the 24 fresh pairs where the pro did, our picker also did on only 4.

## Proposed structural change (not built)

Train a joint placement model instead of two independent rankers plus constants:

- a (exit, cue, length) triple scored jointly, with cross-deck features such as both decks' section at each overlap bar and where each deck's next boundary falls;
- length chosen over {8, 16, 32} from features;
- fade-shape parameters (LONG_XP, HIGH_OFS, bass-swap position) regressed per pair from the pro gain fits we already have (`pro_fade_fit.py`);
- variance reduction through seed/bag averaging, so single-row changes do not flip 30% of decisions;
- listener preferences as a weighted pairwise term ("ours over pro on pair X"), which needs a handful of verdicts before it can matter. The daily survey (now rate A, rate B, prefer) collects exactly that.

## Ship-it check

Nothing was changed in the default, so there is no rollback to note. No A/B was rendered: no candidate change exists, and rendering the same default twice would give near-identical clips.

## Build, chunk 1 (6:14–6:50 PM ET, 11-27): joint picker (`JOINT_PICKER`, not wired into render yet)

the listener approved the proposal at 6:11 PM ET. Code: `protrans/replica/joint_picker.py` (export / cv / train / stab), `joint_eval.py` (decision-level eval), and `joint_work/train_remote.sh` (training on the home Mac).

- **Joint candidates**: the existing exit and cue menus crossed with blend length 8, 16 or 32, giving about 465 legal triples per pair. The engine default is always candidate 0.
- **Features**: what both tracks contain across the whole blend. That includes each deck's section mix, its section at every quarter of the blend, where each deck's next and previous boundary falls relative to the blend start and end, what B goes into after the blend, the A-vs-B section bass and energy levels, and the cross terms of A's drop and outro share against B's intro, drop and breakdown share. Nothing is style-coded.
- **Labels**: exit relevance + cue relevance + 2 when the length bucket matches the pro's.
- **Ensemble**: 8 LambdaMART seeds averaged. The model abstains to the default unless it wins by τ; τ = 1.0 was picked on 5-fold DJ-grouped dev CV. One DJ is 614 of the 1,001 dev rows, so one fold is large.
- **Listener prefs**: rows weighted `5 × ramp(n)`. The ramp is 0 below 3 verdicts and reaches full weight at 6, so today's single verdict has weight 0.

### Decision-level results (no renders yet)

Placement error is the summed exit + cue error in bars, with boundary tolerance, lower is better. Dev is out-of-fold; fresh and the official 33 are out-of-sample. The locked holdout was not opened.

| set | engine default | ridegate (current default) | joint | joint − ridegate, 95% CI |
|---|---|---|---|---|
| dev OOF (1001) | 71.5 | (in-sample, n/a) | 65.8 | — |
| fresh (100) | 86.6 | 64.2 | 61.2 | −3.0 [−9.2, +3.0] |
| official 33 | 99.1 | 78.5 | 75.6 | −2.9 [−15.1, +8.7] |

Style shares, fresh: ridegate drop>drop 12%, drop>in 20%, out>drop 26%, out>in 42%. Joint: 16%, 21%, 25%, 38%. Pro: 24%, 6%, 23%, 47%. Drop-over-drop rises modestly toward the pro share, and no style dominates. Official 33: ridegate 9% drop>drop, joint 15%, pro 15%.

Length shares, fresh: ridegate is 100% 16 bars. Joint is 57% 8, 42% 16 and 1% 32. Pro is 42% 8, 39% 16 and 19% 32. Length is now chosen per pair, but **32 is almost never picked**, and the length hit rate is lower than always-16 (0.35 vs 0.40 on fresh). The length label weight needs work.

Stability, with one duplicated dev row added and fresh argmax picks counted, before τ abstention:

- single joint model: 47, 47 and 50 of 100 change;
- 8-seed ensemble: 18, 20 and 20;
- the old ridegate pack, for comparison: about 30.

Seed averaging more than halves the churn but is still above target.

### Verdict so far

**Not shipped.** Placement improves on fresh and the official 33, but both CIs include 0. Nothing has been rendered or scored yet (official v1/v2, hard fails, audio). Length skews short, and stability is not good enough yet.

### Per-pair fade settings: not started

The only per-clip pro fade fits are `pro_curves_33.json`, which covers the official 33 (the scoring set, so training on it would leak), and the 27 dev-pair fits in `nightly_1125_work/profade_fit`. That is too few to learn fade parameters from features. Fitting pro band gains on more dev pro clips is a data job that comes first.

### Next steps (chunk 2+)

1. On the home Mac, run `train_remote.sh train 32`, then `train_remote.sh stab 32`, and re-measure churn. Target: ≤5 of 100 fresh flips after τ.
2. Rebalance the length label (bucket-match weight, or a separate length ranker conditioned on the chosen exit+cue), then re-run cv and eval.
3. Wire `JOINT_PICKER=1` into `ridegate_live.maybe_apply`, keeping the lock and pump previews, and only for windows legal under `_legal_natural`. Render dev-27 and fresh with eval_gate against the current default, and score official v1/v2, hard fails and the 90 Hz holes. Spot-check audio.
4. Fade: band-gain fits on dev pro clips, then a per-pair `PRO_FADE_*` regressor.
5. Ship-it rule. If it is not met, it stays a flag.


## Chunk 2 (6:39–7:15 PM ET, 11-27): stability, length, live wiring

### Stability (fixed)

- r1 config: 32 seeds; per-model regularization of 7 leaves, min 100 rows per leaf, 150 trees and L2 5; τ = 1.0. Adding one duplicated dev row now changes **2 of 100** fresh decisions in all three tests, down from 18–20 (8 seeds, no τ) and about 30 (old ridegate pack).

### Placement with a stable ensemble (out of sample): worse than the current default

The chunk-1 gain (−3.0 bars on fresh) was partly a lucky 8-seed draw. With 32 seeds:

| config | fresh err (ridegate 64.2) | official-33 err (ridegate 78.5) |
|---|---|---|
| r0 params, 32 seeds | 69.2 (+5.0, CI −2.9..+12.6) | 94.4 (+15.9, CI +1.7..+32.4) |
| r1 regularized, 32 seeds | 67.6 (+3.4, CI −4.7..+11.1) | 91.7 (+13.2, CI −1.8..+30.0) |

Fresh style shares (r1): drop>drop 15%, drop>in 27%, out>drop 20%, out>in 38%. Ridegate is 12/20/26/42, pro 24/6/23/47. The r0 config at 32 seeds gives 17/25/19/39. Diversity holds and drop>drop rises a little, but the joint picker places blends worse than the current factored ridegate picker.

### Length: 32 bars is not predictable from the tracks

- The joint picker almost never picks 32: r1 chose it on 1 of 177 dev pairs where the pro used 32, and 0 of 20 on fresh. Raising the length label weight from 2 to 4 did not change that.
- A direct classifier for pro length bucket, using track features plus features of the pro's own placement, reaches 45% on fresh vs 40% for always guessing the majority (AUC for "32 vs rest" is 0.67).
- Length is mostly a **DJ habit**: KushSessions is 61% ≤10 bars, TheHeshBesh 59% 32 bars, and the official 33 is 64% 32 bars. Learning it from pro placements alone cannot work. It needs a style input (listener preference, mix context) rather than more track features.

### Live wiring (flag only)

- `JOINT_PICKER=1`, with rollback `JOINT_PICKER_OFF=1`, is off by default. It is passed through `recreate.apply_rules` and replaces the factored pick inside `ridegate_live.maybe_apply`; the lock and pump previews still apply.
- `mix_simple.py` admits the injected 8-bar window only when JOINT_PICKER is on.
- The committed pack is `protrans/replica/joint_pack/` (r1). `measure_joint_1127.py` renders dev-27 (base arm with `BASE_ARM=1`), and `joint_work/render_eval.sh` runs dev-27 plus the fresh ukf 18 through eval_gate.

### Compute incidents on the home Mac (both ours)

- 6:21 PM ET reboot: about 20 GB per worker from re-reading the compressed `.npz` per group. Fixed by loading once (memmap `.npy`).
- About 7:00 PM ET, load ~258 and ssh timeouts: LightGBM `Booster.predict` defaults to every core. Each of 5 workers predicted 32 models with 10 threads, so about 50 threads ran on 10 cores. The job was killed, not rerun (its config already lost on placement).
- Fix: `JOINT_THREADS` sets `num_threads` for both fit and predict. `train_remote.sh` sizes workers by RAM (half of free) and by CPU (workers × threads ≤ cores − 4), and runs detached with `nohup`, polling for a done file so an ssh drop cannot kill it.

### First render (dev-27, r1 pack, before the abstain fix)

- All 27 rendered: v1 42.72, v2 41.99, 4 hard fails (3 pump, 1 hole).
- Paired with the 18 pairs the 6:27 AM ET default run scored: Δv1 −0.11, Δv2 −1.65, 6 wins and 8 losses. Hard fails were 3 vs 3, with one new pump fail on Ic7M__10 (6.1 dB) and one cleared elsewhere.
- **Bug found:** when the joint picker abstained (16 of 27), the live path fell back to the bare engine window (`nat_short`) instead of the ridegate decision. That understates the joint arm, so it is fixed in `ridegate_live.maybe_apply`. dev-27 is also in-sample for the picker.

### Next (chunk 3)

1. Re-render the joint arm on dev-27 and the fresh ukf 18 with the abstain fix. Compare against `measure_dev27_base27.json` (current default re-rendered on all 27 with the window env set) and `n1126f_rgdef`.
2. Ship-it check. On current evidence it will not ship: placement is worse out of sample, and length 32 cannot be learned from tracks.
3. If the arm stays off, propose length as a style input (listener and mix context) rather than a track feature.

## Chunk 3 (7:12–7:40 PM ET, 11-27): both engines, fair re-render, ship-it

listener: for tonight and tomorrow, run both engines. Default is unchanged. `JOINT_PICKER=1` is the second engine (`JOINT_PICKER_OFF=1` rolls it back). The daily harness path is `protrans/replica/render_joint_ab.py --test-daily <pick>` (check only) or `--ab <pick>` (writes a 40 s loudness-matched A/B and a PNG if the clips differ; key in `/workspace/private` only).

### Pre-fix hard fails were almost all the abstain bug

On the first dev-27 joint render, all four official hard fails were `nat_short` windows with a joint margin under 1.0 (0.52–0.78). Those were abstentions that fell back to the bare engine window, not joint's own picks. The 11 pairs where joint actually applied had no hard fails.

On the pre-fix fresh 18 (invalid for scoring, but useful here), two of the five hard fails were joint's own 8-bar picks (pump 6.6 on `__00`, pump 7.5 on `__27`). Those can still appear after the fix.

### Fair re-render (keep-default fix)

| | official v1 | official v2 | hard fails | new hard fails | length 8 / 16 / 32 |
|---|---|---|---|---|---|
| **Dev 27, current default** | 39.11 | 39.92 | 6 | — | 0 / 27 / 0 |
| **Dev 27, joint** | 39.10 | 39.88 | 5 | 0 | 11 / 16 / 0 |
| **Fresh 18, current default (n1126f_rgdef)** | (no official score) |  | 1 (`__16`) | — | 0 / 18 / 0 |
| **Fresh 18, joint (n1127f_joint_r1fix)** | (no official score) |  | 3 (`__16`, `__00`, `__27`) | 2 (`__00` pump 6.6 dB, `__27` pump 7.5 dB) | 5 / 13 / 0 |

Dev paired Δv1 −0.01, 95% CI [−2.21, +1.82]; Δv2 −0.04 [−2.02, +1.86]. 6 wins, 5 losses, 16 ties. Cleared hard fail: `alpha_rhythm_TnnrrqVRZIM__14` (default had a beat clash on a 16-bar window; joint's 8-bar window passed). No new official hard fails on dev.

The 11 changed dev windows are all 8-bar. Official scores are mixed: `liquiddnbftw_m6m836_Ic7M__16` +12.6 v1, `sirenity_ofcHup56lME__52` +8.1, `sirenity_ofcHup56lME__57` −20.4.

Fresh placement error (exit + cue, lower is better) 73.5 → 66.0 overall, and 62.6 → 35.5 on the 5 changed pairs. Joint often nails the exit (e.g. `__00` 63.9 → 0.1 bars, `__23` 81.4 → 1.4) but two of those 8-bar picks pump.

**Style mix**

| set | drop>drop | drop>in | out>drop | out>in |
|---|---|---|---|---|
| dev 27 default | 15% | 19% | 30% | 37% |
| dev 27 joint | 22% | 15% | 26% | 37% |
| fresh 18 default | 0% | 28% | 17% | 56% |
| fresh 18 joint | 0% | 17% | 17% | 67% |

Drop-over-drop rises on dev and stays at 0 on this particular fresh mix. No style fully takes over, though fresh joint leans more out>in.

### Ship-it

**Not shipped.** Official scores on dev are a tie, and fresh adds two new pumping hard fails (`ukf __00` and `__27`), both joint's own 8-bar choices. The default stays RIDEGATE+LOCK+PUMP. Use `JOINT_PICKER=1` for the second engine.

### Daily path

Tested on `joe_syntax_hospital__00` (the 11-27 daily pick). Default stays the 16-bar window the listener liked (`['n', 112, None, 32, 16]`). Joint, with margin 2.37, shortens it to 8 bars (`['n', 104, None, 32, 8]`), the same cue, leaving 8 bars earlier. The flag is off on the default arm and on on the joint arm. Because those windows differ, a 40 s A/B was written for tonight (tick at the blend start; hop-diff across the blend: mean 2.19 dB, max 8.82 dB, 58 of 241 hops over 3 dB). Trailing silence pads the shorter 8-bar snippet to 40 s. The answer key is only in `/workspace/private`.
