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

## Next
0. **Pair __11 fix.** Simulate the real gain and EQ lanes in the risk features, stop the swap lanes from stacking into a gap, and tighten the end-of-track constraint (see above).
1. **Engine.** Add a gated per-bar re-sync behind `BAR_RESYNC`, using the engine's per-source-bar NUDGE hook.
   - Act only where 3 or more consecutive bars agree within 8 ms with r ≥ 0.3.
   - Then re-render, rather than shifting the envelope.
   - Keep FINE_PHASE off. It made timing worse here.
2. **Detector.** Recalibrate v3 on those real re-synced renders. Caveat: on re-synced renders the check mostly confirms that the re-sync worked, because both use the same per-bar measurement.
3. **PLACE=safe.** It needs 2 nightly wins before promotion. Also add the audio-less pairs once their sources are restored.

Files (protrans/replica):
- placement: `safeplace_1119.py`, `safeplace_eval.py`, `safeplace_fresh_1119s.py`, `safeplace_work/`, `safeplace_*_eval.json`, `safeplace_fresh_1119s.json`;
- clash check: `deckclash{,2,3,3_rs}_1119.py` and their `.json`;
- drift diagnosis: `deckdrift{,_raw}_1119.py`, `barsync_demo_1119.py`;
- fresh ingest: `fresh_1119s.py`.

Audio and PNGs are in Drive only: `DJ Mixes Archive/research/deckdrift_2026-11-19`.
