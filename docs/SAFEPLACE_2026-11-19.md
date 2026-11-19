# PLACE=safe and the per-deck clash check: 2026-11-19 (day)

All times are ET. Research only: `rules.json` and the defaults are untouched, and everything sits behind flags (`PLACE=safe`, `HC_DECKCLASH=1`).
The locked Liquicity/Hospital holdout was not opened. The spent fresh mixes (John B frbb5gILfjo, OffbeatDooter L0O51m1Ow7I) were not reused.

## 1. Fault-avoiding placement (PLACE=safe)

How it chooses a window. It doesn't use a style knob, and it doesn't flip a coin.
1. **Candidates.** Swap and ride windows are both considered, but only legal ones:
   - the exit window ends on the 16-bar phrase grid;
   - the window doesn't run past the outgoing track's music end or its last loud bar plus 8;
   - the cue lands on the incoming track's 16-bar grid, counted from bar 0 or from drop 1;
   - the blend length X is 16 or 32;
   - the default window is always a candidate too.
2. **Score.** score = learned hard-fail risk + 0.15·(cue off-phrase) + 0.1·(1 − musical fit) + 0.1·(exit more than 4 bars from a section boundary).
   - Musical fit comes from the style-free pro-placement rankers. It's a secondary signal only.
3. **Render check.** Render the top 2 non-default picks and keep the first one that passes HC_A and HC_B. If neither passes, keep the default.

**Risk model.** LightGBM trained on the rendered dev blends, labelled with HC_A|HC_B, cross-validated grouped by mix (557 blends, 20.5% fail).

| features | AUC by mix | AUC by DJ |
|---|---|---|
| window and section features | 0.70 | 0.70 |
| + see-saw simulation features (PUMPF) | 0.79 | 0.77 |
| + the sp1119a renders (variant b) | 0.71 | 0.75 |

**Dev eval.** Leave-one-DJ-out on 91 dev pairs that have local audio and a rendered default (15 mixes, 8 DJs). The CIs are mix-grouped bootstrap 95% (4000 draws).

| arm | any hard fail | Δ vs default [95% CI] | HC_A | HC_B | off section |
|---|---|---|---|---|---|
| default | 15.4% | – | 14.3% | 12.1% | 70% |
| a: rank-1 raw (no render check) | 18.7% | +0.03 [−0.08, +0.13] | | | 79% |
| a: final (render check) | 3.3% | −0.12 [−0.21, −0.06] | | | |
| **b: rank-1 raw** | 14.3% | −0.01 [−0.12, +0.09] | 8.8% | 12.1% | 3.3% |
| **b: final** | **2.2%** | **−0.13 [−0.21, −0.07]** | 1.1% | 2.2% | |

- **Phrase alignment.** 0% off-phrase in every arm.
- **Pro bar error** (secondary). 42.5 vs 37.5 bars, +5.0 [−4.2, +18.3]. That's not significant, but it's worse.
- **Swap share.** 87% of b's picks are swaps (mid-track exits).
- **Why a missed.** Its raw picks were mostly pumping fails (15 of 17), a level see-saw that the window features couldn't see. Variant b added see-saw simulation features computed from the per-bar source curves, plus the section penalty.
- **Where b's raw fails still come from.** clash_v2 6, clash_v1 4, pump 4, halfbeat 2.
- **Caveats:**
  - b was designed after seeing a's results on the same pairs (a second look), but leave-one-DJ-out stayed intact.
  - The final arm uses up to 3 renders per pair.
  - Pairs without local audio (29%) aren't covered.
- **Takeaway.** Ranking by risk alone doesn't lower the fail rate. Rank by risk, then render-check: that's what wins.

**Fresh validation.** New mix, isolated ingest in `fresh_work_s`. Model frozen and trained on all dev. Scored once at 08:52, now marked spent.
- Mix: Alpha Rhythm "'Etherwood' Liquid Drum and Bass Mix 95", https://www.youtube.com/watch?v=u3OiUhgnfkE (checked via oEmbed). It's a new mix, but Alpha Rhythm is a dev DJ.
- 7 pairs:
  - **default** hard-fails 3 of 7 (all pumping);
  - **b rank-1 raw** fails 2 of 7;
  - **b final** fails 1 of 7.
- Outcomes: 3 rank-1 passes, 1 rank-2 pass, 2 kept the default, 1 where both picks failed and it fell back to a failing default.
- Off-section: 2 of the 5 changed picks, vs 5 of 7 defaults.
- One mix gives no valid CI. The direction agrees with dev.

**Why fresh pair __11 still fails.** Etherwood "Begin By Letting Go" into "You're Missing Life". Every window tried fails the pump check:
- default 161–176 with the cue at bar 33: 5.2 dB;
- rank-1 177–192 / cue 49: 5.2 dB;
- rank-2 177–192 / cue 65: 5.4 dB;
- a diagnostic render, 161–176 / cue 48 (A at full level, B already in its drop): 6.1 dB. It's labelled diagnostic and wasn't scored.

Per-bar levels show the reason. The crossfader gains are close to equal-power (0.71/0.71 at mid-blend), but around blend bar 7 the bass swap and the high-band swap overlap:
- A's low and high bands are cut there;
- B's lows and highs are still ramping in;
- for about one bar both decks are mostly mids, so the sum dips about 6 dB and comes back.

So this one isn't a placement fault. Moving the window doesn't help, and the planner's risk model said 0.06–0.07 because its see-saw simulation assumes plain equal-power fades without the EQ swaps.

Two smaller issues on the same pair:
- The default's cue sits in B's quiet pre-drop build, about 8 dB under A.
- The rank-1 and rank-2 exits run into A's own fade to silence. The end constraint (last loud bar + 8, with loud meaning within 20 dB of the track's normal level) is too loose.

Fixes:
- (a) put the engine's real gain and EQ lanes into the risk simulation;
- (b) never let the high-band swap and the bass swap both open a gap in the same bar;
- (c) tighten the end constraint to "no fading tail inside the blend".

## 2. Clash check measured per deck (HC_DECKCLASH)

Our renders have the two decks separately, so a clash can be measured per deck, not from the summed audio.

| version | what it measures | clean renders: typical / worst 5% | result |
|---|---|---|---|
| mixed-audio flam/grid recalibration with the 127 new renders | summed mix | – | failed: grid flags clean about as often as clash (dev 14–25%), flam ≤ 9% everywhere |
| v1 deck A vs deck B kick phase | absolute | 17 / 161 ms | confounded by different drum patterns and half-beat ambiguity |
| v2 each deck vs itself (solo vs overlap), bar-folded | self-referenced | 17 / 168 ms | 38–53% recall at ≤ 5% clean |
| **v3 raw decks, per bar** (FP0, engine as is) | self-referenced, EQ off | 4.5 / 34 ms | D 52 ms: held-out recall 57% (60 ms), 83% (110), 75% (−60); clean 7.4% |
| v3 with the existing per-phrase finephase on (FP1) | | 9.4 / 86 ms | worse: finephase *adds* timing error |
| **v3 on per-bar re-synced decks** (RS prototype) | | 2.1 / 22 ms | D 42 ms: held-out recall 82% / 85% / 85%; clean 9.1% (dev 5.0%) |

Splits are md5%3 by pair: 300 dev, 175 held-out renders. The threshold is chosen on dev with clean ≤ 5%. 475 renders in total.

**Are the "clean" renders clean?** I checked per bar (`deckdrift_1119*.py`, PNGs in Drive).
- **Mostly measurement artifacts.** v2's ~168 ms "drifts" were mostly fake. The bass-swap EQ mutes one deck's kick band during the overlap, so the bar-folded profile locks onto the snare half a beat away. On raw decks (same timing, EQ off), 5 of the top 10 dropped to 0–7 ms, and the rest had small per-bar offsets.
- **But some real faults exist.**
  - 39 of 610 deck overlaps (6.4%) have a steady trend of more than 20 ms (R² > 0.5).
  - Example: kushsessions_yaWXrFBRYrM__18. The outgoing deck's kicks step **−26 ms at source bar 144** and stay there. Source bars are contiguous, there's no nudge, and the grid is constant, so the phase change is in the track audio itself. It could be an edit or a different kick sample. The per-bar re-sync takes it to 0 ± 2 ms (before/after mp3s and PNGs are in Drive).
- **Noise exists too.** In suicidesheeep_R8MWKsheHxk__25, deck B's intro offsets jump ±100 ms bar to bar, even in its solo bars. That's noise, and a naive re-sync made it worse. Re-sync has to act only on stable, confident offsets.

**Wired up.** `final_eval.flags` adds `deckclash` to HC_A and HC_B only when `HC_DECKCLASH=1` and the arrays carry `deck_lag`. The value comes from `deckclash3_1119.annotate(variant)`, and D is 52 ms, chosen on dev. It's off by default because it doesn't meet the bars yet: held-out clean is 7.4% against a target of ≤ 5%, and 60 ms recall is 57% against a target of ≥ 80%.

## 3. Update 09:00–10:15: lanes, tail, variants c and d, placement quality, BAR_RESYNC

**Lane simulation (`lanesim_1119.py`).** Rebuilds each blend's level per bar from the source curves using the engine's real
crossfader and EQ lanes (median lane templates from 455 dev renders, low < 150 Hz and high > 2 kHz swaps). Against the measured pump
it ranks blends with Spearman 0.89. Flagging "simulated dip ≥ 4.54 dB" (the pro p95) catches 88.5% of measured pumps; 85% of flagged
blends pump vs 1.5% of the rest. On fresh pair __11 it predicts 5.1/4.9/5.2/6.0 dB vs measured 5.2/5.2/5.4/6.1, so the swap-lane valley
is now visible to the planner (feature `sim2_vdip`, the top feature of the c risk model).

**New constraints (flags).** `GAPX=1` drops any non-default window whose simulated sum dips ≥ 4.54 dB for even one bar.
`TAIL6=1` ends the exit window by the last outgoing bar within 6 dB of the track's body level (was: within 20 dB, + 8 bars).

**Variant c** = b + lane features + GAPX + TAIL6. Risk model AUC 0.82 by held-out mix, 0.86 by held-out DJ.
The first c render job failed because my shell leaked the fresh-ingest paths (`GATE_FEAT`/`GATE_FLIB`) into it, so it rendered only 7
fresh pairs; `run_renders.sh` now unsets them. Only the c renders were rerun.

**Variant d** = c + a placement-quality term (`PAYPEN=0.3`, `payoff_miss()` in `safeplace_1119.py`): a penalty for the share of the
outgoing track's last drop (its main payoff, usually drop 2) not heard before the blend starts (the blend may cover its last 8 bars),
plus a penalty if the cue skips the incoming track's first drop. Weight set once, before any d render; it is not a pro-habit target.

Dev eval, leave-one-DJ-out, 91 pairs, 15 mixes, mix-grouped 95% CIs:

| arm | any hard fail | Δ vs default | outgoing track played | its last drop heard before blend | cue skips B's drop 1 | mid-track exits |
|---|---|---|---|---|---|---|
| default | 15.4% | – | 94% | 74% | 4% | 17% |
| b final | 2.2% | −0.13 [−0.21, −0.07] | 68% | 12% | 33% | 87% |
| c raw | 9.9% | −0.05 [−0.18, +0.04] | 66% | 3% | 20% | 95% |
| c final | 1.1% | −0.14 [−0.23, −0.08] | 66% | 6% | 19% | 92% |
| **d raw** | **4.4%** | **−0.11 [−0.19, −0.04]** | **94%** | **74%** | **0%** | 30% |
| **d final** | **3.3%** | **−0.12 [−0.20, −0.06]** | 94% | 73% | 0% | 30% |
| pros (reference) | – | – | 69% | 31% | 33% | – |

- c vs b: final −0.011 [−0.04, 0.00], raw −0.044 [−0.14, +0.03]: no clear difference.
- d vs c: final +0.022 [0.00, +0.055]: no clear difference, d slightly worse on paper, but d plays the tracks as written.
- **c was cutting tracks short.** It left the outgoing track at ~66% on average and blended out before its last drop could play in ~94% of pairs (it never reached that drop at all in 59%)
  (10th percentile: only 55% of the track played). b did the same. Listening clips + PNGs for 3 typical cases are in Drive
  (`research/placement_2026-11-19`): in each, c blends out exactly where drop 2 would start.
- **d keeps the fault cut without that cost.** It keeps the default window on 38 pairs and mostly moves cues and lengths
  elsewhere. Its raw picks are already much safer than default (4.4% vs 15.4%), so it relies less on the render check.
  d's remaining fails: 2 clash_v1, 1 clash_v2.
- Off-section is ~71% for d, same as the default: late exits sit in outros, not on a section boundary. Not a fault.
- **Caveats:** b, c and d were each designed after seeing the earlier variants on these same pairs (leave-one-DJ-out intact,
  but this is a repeated look). The lane templates are unlabelled medians over dev renders that include the test DJs (minor leak).
  The final arms use up to 3 renders per pair.

**Fresh validation of d.** Queued to run once, automatically, on a new mix from a DJ who is not in dev (isolated in `fresh_work_t`,
pool of 5 liquid mixes, first candidate liquiddnbftw m6m836_Ic7M). Result to be appended when it lands.

**BAR_RESYNC (engine, flag).** `src2/engine.py`: per deck, bar-vs-bar cross-correlation of the kick band (30–150 Hz onsets);
a bar counts as confident only when ≥ 40% of its pairwise lags with r ≥ 0.15 agree within 6 ms; stretches of ≥ 2 consecutive bars
within 8 ms of each other (at least half confident) with a median offset of 8–60 ms get one constant shift, then the deck is re-rendered.
- kushsessions __18: bars 16–22 moved −25 ms; deck A's overlap offset −12.7 → −1.8 ms, trend span 37.8 → 10.6 ms (clips + PNG in Drive).
- suicidesheeep __25 (noisy intro): 0 bars moved, unchanged.
- On the 39 drifting deck overlaps: median trend span 37.8 → 31.8 ms; 26 of 39 still drift > 20 ms. It fixes clean steps, not slow
  or noisy drift.

**HC_DECKCLASH on real re-synced renders (`deckclash4_1119.py`, `deckclash4b_1119.py`).** 237 renders (37 drifting + 200 clean),
split by mix (9 calibration, 8 test mixes). Best rule chosen on calibration: per-bar median, r ≥ 0.2, D = 16 ms.
Test: clean flagged 4.3% (target ≤ 5%), planted clash recall 57/56/60% (target ≥ 80%): **misses**.
Why: when the strict confidence gate judges an overlap, clean and planted clashes separate cleanly (clean p95 18 ms, planted 60 ms
p10 ≥ 38 ms), but it abstains on ~44% of overlaps. A tiered fallback to the loose gate (D up to 130 ms) still missed
(test recall 61–79%, clean 6.8%). `final_eval.DECKCLASH_D` = 16 with that note; the flag stays off.

**Banned-string cleanup.** Reworded the older docs and every tracked file in grokbot-mixer, including inside words (code uses
`np.clip` / `np.fmin`, identical results). The backup now fails closed on any case-insensitive substring hit. Remaining exceptions:
one compression crate name in `Cargo.lock` (a dependency name, cannot be reworded) and 11 files outside grokbot-mixer (patch prepared, not applied: the backup's commit
guard only allows grokbot-mixer). Git history still contains the old strings.

## Next
1. **Fresh one-shot of d** on the non-dev DJ mix (queued); then 2 nightly wins before any promotion.
2. **HC_DECKCLASH**: needs more coverage, e.g. a per-deck kick template from the track's own solo sections instead of the overlap bars.
3. **BAR_RESYNC**: handles steps; slow drift would need a per-bar tempo correction (not attempted).
4. Pairs without local audio (29%) still aren't covered.

Files (protrans/replica):
- placement: `safeplace_1119.py`, `lanesim_1119.py`, `placequal_1119.py`, `placequal_clips_1119.py`, `safeplace_cmp_1119.py`, `safeplace_eval.py`, `safeplace_fresh_1119s.py`, `safeplace_work/`, `safeplace_*_eval.json`, `safeplace_fresh_1119s.json`;
- clash check: `deckclash{,2,3,3_rs,4,4b}_1119.py`, `resync_test_1119.py` and their `.json`;
- drift diagnosis: `deckdrift{,_raw}_1119.py`, `barsync_demo_1119.py`;
- fresh ingest: `fresh_1119s.py`.

Audio and PNGs are in Drive only (private): `DJ Mixes Archive/research/deckdrift_2026-11-19` and `research/placement_2026-11-19`.
