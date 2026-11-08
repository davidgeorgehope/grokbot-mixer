# Engine test fixture audit (8 November 2026, ET)

Before: 17 failed, 42 passed, 21 skipped, 4 setup errors (84 collected). Two release-fixture gate regressions were added (86 now collected).
After (no selected render): 14 passed, 72 skipped, zero failures/errors.
This is NOT a passing rendered-mix release certification. MIX_NAME was unset.
The old suite implicitly selected stale mixS metadata, while mixS_master.wav,
the default mix03 MP3, various stretched sources, and separation outputs had
been cleaned. Integration QA now requires explicit MIX_NAME. When a build is
explicitly selected, missing required metadata fails; calibrated assertions
and all checks.py thresholds are unchanged.

| Original failure/error | Verified cause |
|---|---|
| beatmelody::bm1_detector_flags_beats_into_melody | Missing cached drum+bass fixture. Attempted separation then read nonexistent /tmp/dnb_*/htdemucs/7Itbo72XEz4/drums.wav; require both source and dnb cache before archival regression. |
| ears::backbeats_line_up_through_every_blend | Old mixS source st/N4mzOUMNsuI.wav absent during deck render. |
| ears_gate::ears_and_direct_drums_agree_no_blend_is_off | Same missing deck-render source through ears.scores(). |
| guardrails::zero_failures | No guard_mixS/guardrails.json; no active build was selected. |
| guardrails::catch_listener_bad_spots | Historical bad-spots fixture assertions passed; subsequent current-mix assertion required nonexistent guard_mixS JSON. |
| mix::global_grid_no_drift | Deleted mixS_master.wav. |
| mix::anchor_tracks_long_enough | Stale mixS plan/metadata judged against current anchor-length assertions; not a selected render. |
| mix::no_unintentional_energy_drops | Deleted mixS_master.wav. |
| mix::no_abrupt_cuts | Deleted mixS_master.wav. |
| mix::true_peak | ffmpeg couldn't inspect deleted default dj-mix-03-60.mp3, leaving no parsed peak. |
| mix::every_deck_on_its_planned_bar | Deleted mixS_master.wav. |
| mix::no_vocal_clash | Old mixS metadata contains vocal-clash failures; not a new-engine regression or a selected current build. |
| mix::mixdown_beats_aligned_every_overlap_bar | Missing stretched source WAV for old mixS. |
| mix02_traits::loops_only_repeat_the_phrase_just_played | Stale mixS mapping violates the newer loop-phrase assertion; no selected build. Assertion retained. |
| phase_trainwreck::r12_parallel_trainwreck_fails_phase_check | Reference MP3 and timing JSON exist, but st/MoYkYkoeb84.wav needed for source onsets is deleted. Now checks all referenced deck WAVs. |
| pref_card::publish_writes_sidecars | Archived MP3 exists but its source st/sObzaBqaBRQ.wav is deleted; card renderer could not generate PNG. Now checks timing sidecar's deck fixtures. |
| seesaw::beat_outro_remedy_ignite | Archival plan render requires deleted stretched/DnB source fixtures. Now checks both decks' WAV and DnB fixtures before invoking render. |
| setup mix::beat_drift_across_transitions | Shared T fixture read deleted mixS_master.wav. |
| setup mix::downbeats_aligned | Same shared T fixture. |
| setup mix::beat_overlap_16_bars | Same shared T fixture. |
| setup mix::no_key_clash | Same shared T fixture. |

No real mix-engine bug was established by this run. The actual fixes are test
fixture selection/lifecycle. Existing archived metadata failures have NOT been
re-labelled as passing audio. Integration-only tests without MIX_NAME skip;
the release runner already provides MIX_NAME and its fresh-render fixtures.
