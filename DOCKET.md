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
- IN PROGRESS: precomputed planner (src2/plan_search.py + new src2/pair_feats.py). 2026-10-28 22:10: pair table now carries melodic clash (bars where both decks' melody layer is loud + chord rub) and grid-phase drift per window; hard cap MELMAX=8 (34:05 Bad To Me->Blame You had 11, rated 1/5; 30:56 Parallel->Bad To Me had 0, rated 5/5). Far-back loops already banned in engine. Search on plan_60v: 10.6k of 18.9k complete orders pass on paper; dry-verified plan_60pl2 (21 tracks, 58 min, beat16 17/20, all meta tests). Render mixPlan2 still fails 5 audio guardrails (entry level steps N1 x3, L1, E2) the paper model doesn't predict yet. NEXT: model entry level step + bass overlap in the table, re-search, render, deliver only if all pass.
  - Was: Pre-score every track pair, search for the order that meets all targets at ~60 min, render only after the plan passes on paper.
- Re-render Mix 03 visuals and the private YouTube video for the final version.
- Update the build-dj-mix skill: crossfader-only approach, Mix 01/02 reference traits, beat-on-beat target, beatless cap, keep it simple.
- TRAIN ON THE MIX CATALOG: DONE (57 reliable transitions, out-cue ranker 0.535 vs 0.478 rule, CUEW flag default off, pro_likeness report-only)

## Later
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
