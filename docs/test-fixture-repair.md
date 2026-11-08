# Fixture-suite repair, 2026-11-08

## Results and scope (do not confuse regressions with release certification)

- Before: `python3 -m pytest src/tests -q -rs`: **14 passed, 72 skipped, 0 failed** (86 cases).
- After: same command: **52 passed, 0 skipped, 0 failed**.
- **44 live-build acceptance checks were moved, not deleted**, to `src/build_qa`.
  They all collect successfully; they were NOT run on a real mix in this repair.
  This is NOT a claim that all original 86 cases passed or any real mix is certified.
- `src/render_and_test.sh`, all four autoloop variants and three historical build
  shell runners explicitly run BOTH directories before cleanup. The planner's
  four imports were migrated too. A regression test protects these entry points.
- A negative selected-build smoke test proves missing metadata fails closed; unit safety regressions also require the selected master WAV, MP3 and every full source stem.
- No obsolete tests/code were identified, so none were deleted as obsolete.
  Historical tempo/phase/outro tests were replaced with honest synthetic equivalents,
  not represented as rerenders of named commercial tracks or heard old clips.
- Remaining default-suite skips: **none**. Real-build QA can still report genuinely
  inapplicable optional techniques (no echo/high swap, legacy engine, etc.).
  No full real-build QA run occurred here, so those are not counted as passes.

## What was actually wrong

The original explanation that all 72 skips came from cleanup was false. Fourteen
self-contained crossfader/variety cases plus five small-data structure cases were
being suppressed by a blanket no-MIX_NAME hook. Nine missing-audio archival cases
needed synthetic replacements. Forty-four cases are acceptance questions about a
specific real mix, and cannot truthfully certify that mix from a synthetic fixture.
Those four groups total the original 72 skips; two extra phase parameters and eight new regressions explain the final 96 cases across both directories.

## Fixtures and disk use

- Fixture-source directory: **134197 bytes** total, including the existing
  historical guardrail report, four small grid JSONs, preference JSON and generator.
- Generated two-track source/stem workspace: **3565010 bytes** (~3.57 MB),
  compressed FLAC containers; .wav names retain the engine path contract.
- No binary audio committed. `src/tests/fixtures/generate.py` is deterministic,
  copyright-free, offline, and creates sources only inside pytest-owned temporary dirs.
- Generated stems, cards and copies are removed at fixture teardown. Tempo pulse
  files are unlinked at teardown. No dependency on deleted archival WAVs remains
  in the default fixture-backed suite.
- Phase: aligned and +/-24 ms delayed-tail envelopes run actual alignment scoring.
- Tempo: 124 BPM negative and 174/176 BPM positive pulse probes.
- Beat/melody: real engine render, incoming beat-loop fill, dswap exemption and
  full-mix hard-cut negative tests. Beat-only outro starts before the blend.
- Additional measured engine tests cover low-EQ attenuation with melody retained,
  filtered/decaying delay with bit-identical dry audio, and bass-gap detection plus
  intentional-source-breakdown exemption. Blend cards render real audio and PNG.

## Evidence

`jobs/fixture-before.xml`, `jobs/fixture-after.xml`, and the `fixture-*.log/.status`
files record actual runs. Long commands were launched through `jobs/runjob.sh` in
background. Detailed baseline JSON: `docs/test-fixture-baseline.json`.

## Every original skipped test and its exact reason

- `src.tests.test_bassgap::test_no_bass_gap_in_overlaps` — MIX_NAME/MIX_WAV not set
- `src.tests.test_beatmelody::test_bm1_detector_flags_beats_into_melody` — drums+bass stems not cached (python3 beatstem.py <id>)
- `src.tests.test_beatmelody::test_ib_render_keeps_beats_continuous` — drums+bass stems not cached (python3 beatstem.py <id>)
- `src.tests.test_beatmelody::test_dswap_is_not_a_full_mix_tail_fail` — drums+bass stems not cached (python3 beatstem.py <id>)
- `src.tests.test_crossfader::test_x1_passes_linear_equal_power` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_non_monotonic` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_steep_step` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_extra_automation` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_on_mix` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_passes_one_smooth_bass_swap` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_bass_swap_too_fast` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_bass_swap_too_long` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_second_bass_move` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_bass_move_outside_blend` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_passes_bass_swap_at_35pct` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_x1_fails_bass_swap_not_tied_to_crossfader` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_crossfader::test_mix_bass_swaps_monotonic_smooth` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_ears::test_backbeats_line_up_through_every_blend` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_ears_gate::test_ears_and_direct_drums_agree_no_blend_is_off` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_echo_out::test_echo_tail_lands_on_phrase_boundary` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_echo_out::test_echo_tail_clear_of_incoming_kick` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_echo_out::test_echo_tail_no_level_jump` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_echo_out::test_echo_tail_decays_within_4_bars` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_echo_out::test_echo_out_leaves_dry_deck_identical` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_bass_never_doubles` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_phrase_swaps_land_on_phrase_boundary` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_no_level_dip_at_swap` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_eq_lanes_monotonic_in_every_blend` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_high_swaps_on_phrase_apart_from_bass` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_eq_swap::test_high_swap_no_doubled_highs` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_guardrails::test_guardrails_zero_failures` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_guardrails::test_guardrails_catch_listener_bad_spots` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_stretched_sources_are_44k1` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_beat_drift_across_transitions` — integration QA needs explicit MIX_NAME
- `src.tests.test_mix::test_global_grid_no_drift` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_downbeats_aligned` — integration QA needs explicit MIX_NAME
- `src.tests.test_mix::test_beat_overlap_16_bars` — integration QA needs explicit MIX_NAME
- `src.tests.test_mix::test_no_key_clash` — integration QA needs explicit MIX_NAME
- `src.tests.test_mix::test_anchor_tracks_long_enough` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_no_unintentional_energy_drops` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_no_abrupt_cuts` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_true_peak` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_every_deck_on_its_planned_bar` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_no_vocal_clash` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix::test_mixdown_beats_aligned_every_overlap_bar` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_each_track_gets_its_body` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_blends_mostly_32_bars` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_no_long_drums_only_stretch` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_half_the_blends_beat_on_beat_16_bars` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_few_beatless_blends` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_mix02_traits::test_loops_only_repeat_the_phrase_just_played` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_pbpm::test_rejects_just_hold_on_breaks_original` — breaks wav missing
- `src.tests.test_pbpm::test_accepts_deeper_dnb` — Deeper wav missing
- `src.tests.test_pbpm::test_accepts_just_hold_on_pola_bryson_remix` — Pola & Bryson remix wav not prepped yet
- `src.tests.test_phase_trainwreck::test_r12_parallel_trainwreck_fails_phase_check` — archival fixture missing: /workspace/mixes/src2/st/MoYkYkoeb84.wav, /workspace/mixes/src2/st/2s3M6oX2lfo.wav
- `src.tests.test_pref_card::test_publish_writes_sidecars` — archival fixture missing: /workspace/mixes/src/tests/../../src2/st/sObzaBqaBRQ.wav, /workspace/mixes/src/tests/../../src2/st/q_cZZY0BehE.wav
- `src.tests.test_seesaw::test_no_seesaw_between_decks` — MIX_NAME not set: no build under test
- `src.tests.test_seesaw::test_beat_outro_remedy_ignite` — archival fixture missing: /workspace/mixes/src2/st/sObzaBqaBRQ.wav, /workspace/mixes/src2/st/sObzaBqaBRQ.dnb.wav, /workspace/mixes/src2/st/q_cZZY0BehE.wav, /workspace/mixes/src2/st/q_cZZY0BehE.dnb.wav
- `src.tests.test_structure_tail::test_sections_known_tracks[2s3M6oX2lfo]` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_sections_known_tracks[F1NCnCxyhqc]` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_sections_known_tracks[NaY3x3GRDF4]` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_sections_known_tracks[OPuVVhbkicU]` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_plan_respects_outro_and_intro` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_blend_lengths_vary` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_outgoing_fader_tail_is_gradual` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_outgoing_audio_tail_never_drops_abruptly` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_structure_tail::test_pin_exemption_only_for_5_rated_pairs` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_variety::test_ratings_scale_5_good_4_ok_3_bad` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_variety::test_pair_prefs_3_is_penalised_not_neutral` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_variety::test_diversity_rule` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_variety::test_outgoing_repeat_under_variety_rule` — integration QA needs an explicit MIX_NAME; no build selected
- `src.tests.test_variety::test_echo_outs_capped` — integration QA needs an explicit MIX_NAME; no build selected

## Preserved real-build acceptance checks (not run on a real mix)

- `src/build_qa/test_release_bassgap.py::test_no_bass_gap_in_overlaps`
- `src/build_qa/test_release_crossfader.py::test_x1_on_mix`
- `src/build_qa/test_release_crossfader.py::test_mix_bass_swaps_monotonic_smooth`
- `src/build_qa/test_release_ears.py::test_backbeats_line_up_through_every_blend`
- `src/build_qa/test_release_ears_gate.py::test_ears_and_direct_drums_agree_no_blend_is_off`
- `src/build_qa/test_release_echo_out.py::test_echo_tail_lands_on_phrase_boundary`
- `src/build_qa/test_release_echo_out.py::test_echo_tail_clear_of_incoming_kick`
- `src/build_qa/test_release_echo_out.py::test_echo_tail_no_level_jump`
- `src/build_qa/test_release_echo_out.py::test_echo_tail_decays_within_4_bars`
- `src/build_qa/test_release_echo_out.py::test_echo_out_leaves_dry_deck_identical`
- `src/build_qa/test_release_eq_swap.py::test_bass_never_doubles`
- `src/build_qa/test_release_eq_swap.py::test_phrase_swaps_land_on_phrase_boundary`
- `src/build_qa/test_release_eq_swap.py::test_no_level_dip_at_swap`
- `src/build_qa/test_release_eq_swap.py::test_eq_lanes_monotonic_in_every_blend`
- `src/build_qa/test_release_eq_swap.py::test_high_swaps_on_phrase_apart_from_bass`
- `src/build_qa/test_release_eq_swap.py::test_high_swap_no_doubled_highs`
- `src/build_qa/test_release_guardrails.py::test_guardrails_zero_failures`
- `src/build_qa/test_release_guardrails.py::test_guardrails_catch_listener_bad_spots`
- `src/build_qa/test_release_mix.py::test_stretched_sources_are_44k1`
- `src/build_qa/test_release_mix.py::test_beat_drift_across_transitions`
- `src/build_qa/test_release_mix.py::test_global_grid_no_drift`
- `src/build_qa/test_release_mix.py::test_downbeats_aligned`
- `src/build_qa/test_release_mix.py::test_beat_overlap_16_bars`
- `src/build_qa/test_release_mix.py::test_no_key_clash`
- `src/build_qa/test_release_mix.py::test_anchor_tracks_long_enough`
- `src/build_qa/test_release_mix.py::test_no_unintentional_energy_drops`
- `src/build_qa/test_release_mix.py::test_no_abrupt_cuts`
- `src/build_qa/test_release_mix.py::test_true_peak`
- `src/build_qa/test_release_mix.py::test_every_deck_on_its_planned_bar`
- `src/build_qa/test_release_mix.py::test_no_vocal_clash`
- `src/build_qa/test_release_mix.py::test_mixdown_beats_aligned_every_overlap_bar`
- `src/build_qa/test_release_mix02_traits.py::test_each_track_gets_its_body`
- `src/build_qa/test_release_mix02_traits.py::test_blends_mostly_32_bars`
- `src/build_qa/test_release_mix02_traits.py::test_no_long_drums_only_stretch`
- `src/build_qa/test_release_mix02_traits.py::test_half_the_blends_beat_on_beat_16_bars`
- `src/build_qa/test_release_mix02_traits.py::test_few_beatless_blends`
- `src/build_qa/test_release_mix02_traits.py::test_loops_only_repeat_the_phrase_just_played`
- `src/build_qa/test_release_seesaw.py::test_no_seesaw_between_decks`
- `src/build_qa/test_release_structure_tail.py::test_plan_respects_outro_and_intro`
- `src/build_qa/test_release_structure_tail.py::test_blend_lengths_vary`
- `src/build_qa/test_release_structure_tail.py::test_outgoing_fader_tail_is_gradual`
- `src/build_qa/test_release_structure_tail.py::test_outgoing_audio_tail_never_drops_abruptly`
- `src/build_qa/test_release_variety.py::test_outgoing_repeat_under_variety_rule`
- `src/build_qa/test_release_variety.py::test_echo_outs_capped`
