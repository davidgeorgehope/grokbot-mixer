# DJ docket (keep current; update after every step)

## Now
- DONE 2026-10-28: Mix 03 refill delivered (58:52, Drive + iCloud, real titles). Passes everything except beat-on-beat (9/19, needs 10).
- IN PROGRESS: fix the Ember blends (34:56, 38:15) with a replacement or a track with long drum intros to reach 10/19.
- Mix 03 refill to ~60 min with 3-5 new liquid tracks, built on the mixT baseline (additive, nothing thrown away).
  - Must pass: all current guardrails and pytest, E4 long-lull, loud-section coverage (avg >=0.80, each >=0.50), half the blends >=32 bars, no 8+ drums-only bars.
  - New targets: >=1/2 of blends with 16+ straight bars of both decks drumming (beat-on-beat); <=1/3 of blends mostly beatless.
  - Tracklist uses real Artist - Title. Deliver to Drive (latest only) and iCloud DJ Mixes, then clean up the disk.

## Next
- Re-render Mix 03 visuals and the private YouTube video for the final version.
- Update the build-dj-mix skill: crossfader-only approach, Mix 01/02 reference traits, beat-on-beat target, beatless cap, keep it simple.
- TRAIN ON THE MIX CATALOG: DONE (57 reliable transitions, out-cue ranker 0.535 vs 0.478 rule, CUEW flag default off, pro_likeness report-only)

## Later
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
