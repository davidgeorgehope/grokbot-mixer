# DJ docket (keep current; update after every step)

## Now
- DONE 2026-10-28: Mix 03 refill delivered (58:52, Drive + iCloud, real titles). Passes everything except beat-on-beat (9/19, needs 10).
- IN PROGRESS: mixLenSd render (plan_60sd: Sweet Lies blend redone without loop per the listener, +Galaxy Bladerunner rmx, dry 60.7 min 11/20 beat16).
- Mix 03 refill to ~60 min with 3-5 new liquid tracks, built on the mixT baseline (additive, nothing thrown away).
  - Must pass: all current guardrails and pytest, E4 long-lull, loud-section coverage (avg >=0.80, each >=0.50), half the blends >=32 bars, no 8+ drums-only bars.
  - New targets: >=1/2 of blends with 16+ straight bars of both decks drumming (beat-on-beat); <=1/3 of blends mostly beatless.
  - Tracklist uses real Artist - Title. Deliver to Drive (latest only) and iCloud DJ Mixes, then clean up the disk.

## Next
- "Ears": note-level clash check (chroma dissonance between the two decks) + beat-by-beat drum alignment check, calibrated on 34:05 (bad) vs 30:56 (good). Later: a learned blend-quality model trained on Raveform + the listener's ratings.
- IN PROGRESS: precomputed planner (src2/plan_search.py + new src2/pair_feats.py). 2026-10-28 22:10: pair table now carries melodic clash (bars where both decks' melody layer is loud + chord rub) and grid-phase drift per window; hard cap MELMAX=8 (34:05 Bad To Me->Blame You had 11, rated 1/5; 30:56 Parallel->Bad To Me had 0, rated 5/5). Far-back loops already banned in engine. Search on plan_60v: 10.6k of 18.9k complete orders pass on paper; dry-verified plan_60pl2 (21 tracks, 58 min, beat16 17/20, all meta tests). Render mixPlan2 still fails 5 audio guardrails (entry level steps N1 x3, L1, E2) the paper model doesn't predict yet. 2026-10-28 23:35: table now also has entry step (cap 9.5 dB, rated 4+ exempt), near-silent solo bars, beat-off bars (ears test predictor, matches renders within 3 bars), render-proven bad windows, pair_prefs.json (Parallel->Bad To Me 5/5). mixPlan3: 1 guardrail + 4 tests. Fixing paper E4 model (rJuyd8koFAU breakdown missed), then mixPlan4.
  - Was: Pre-score every track pair, search for the order that meets all targets at ~60 min, render only after the plan passes on paper.
- Re-render Mix 03 visuals and the private YouTube video for the final version.
- Update the build-dj-mix skill: crossfader-only approach, Mix 01/02 reference traits, beat-on-beat target, beatless cap, keep it simple.
- TRAIN ON THE MIX CATALOG: DONE (57 reliable transitions, out-cue ranker 0.535 vs 0.478 rule, CUEW flag default off, pro_likeness report-only)

- Ears step 2 BUILT 2026-10-28 (ears/ears.sh, see EARS.md): refill fails 33:50 (target) + 11:02, 34:56, 40:49, 43:02, 51:51 (unconfirmed by ear; likely downbeat-phase errors in track grids). Next: wire as planner cost + trait test after the planner/Mix 03 workers land; verify the 40:49/43:02/51:51 downbeat phases. Original spec: per-deck Beat This grid compare (phase ms + downbeat agreement, gated on both decks drumming) as a test + planner cost; per-deck Basic Pitch cross-deck dissonance; re-check on 34:05 bad vs 30:56 good.

## Later
- Ears probe done 2026-10-28: Beat This flags 34:05 (beat CV 0.34 vs 0.03 good); Basic Pitch mixdown, CLAP and MERT distance don't separate. Embeddings only as features for the trained classifier.
- Ears v2 (the listener OK to invent; run embeddings/training on the home GPU box via MPS, box does planning+render): blend-quality model from audio embeddings (e.g. pretrained music model) of 16-bar blend windows; positives = Raveform pro blends + the listener 4-5 ratings, negatives = synthetic bad blends (off-key, off-grid, double bass, far-back loops) + his 1-2 ratings. Used as eval AND planner cost.
- Pro DJ techniques, added one at a time on top of the baseline, each with its own test and only where Raveform data says pros use it: mid/high EQ swaps, filter sweeps, echo/reverb outs, double drops, intentional phrase cuts, loops/rolls. First measure in Raveform how often each one is used in DnB. Start with EQ swaps + echo-outs.
- Blend scorer trained on the listener's 1-5 ratings.
- Mix 04 from fresh finds, end to end on the new setup (target: Mix 01 feel + more overlapping beats).
- Offline music pack for the flight; Mix 01 visuals.
- Old v3 YouTube video https://youtu.be/hsMGVeo8tMQ is still up (my access can't delete it).

## Reference / decisions (2026-10-28)
- Mix 01 is still the best; Mix 02 also very good. We overcomplicated things after them. Keep the engine simple.
- Mix 01 = near-whole tracks, 16-bar swaps, no FX. It lacked overlapping beats, which the listener wants more of.
- Beatless blends are OK as one option, never the only way.
- Findings: /workspace/mixes/MIX_REFERENCE.md.

## Running on their own
- Friday fresh finds, Saturday weekly mix + offline sync, nightly disk cleanup (3 AM Central).
