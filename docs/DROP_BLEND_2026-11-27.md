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
