---
name: build-dj-mix
description: >-
  Use this when building a tested, continuous DJ mix (drum & bass or similar)
  from a tracklist with the open-source grokbot-mixer pipeline.
---
# Build a DJ mix with grokbot-mixer

1. Clone https://github.com/davidgeorgehope/grokbot-mixer and read AGENTS.md first, then SETUP.md, docs/PROCESS.md, docs/MIXING_RULES.md and docs/GUARDRAILS.md. Copy config.example.env to config.env and fill in the owner's settings. Copies of this skill live in `skills/` in that repo; keep them in sync when the process changes, and snapshot the mixer to git.
2. Pick 18-22 tracks (about 60 minutes) from the owner's taste profile with an emotional arc and harmonic flow (Camelot steps of 1-2 between neighbours). Never invent tracks. Plan the whole order and every blend window on paper before rendering. Verify true tempos and use drum-and-bass-tempo versions only.
3. Fetch audio only from official uploads, on a machine YouTube doesn't block (cloud IPs usually are), and prep each track: BPM, beat grid, key, sections, stems.
4. Write the plan JSON (format in AGENTS.md) and render with the mix engine. Run long steps in the background through `jobs/runjob.sh` (status file, log, and an optional webhook on finish or failure) and checkpoint progress to a notes file so interruptions lose little. Check the status file; never guess.
5. Blend defaults: one monotonic equal-power crossfader with channel faders at unity, a phrase-snapped bass swap, and a separate high-band swap a few bars later when both tracks have drums. Set `BASS_SWAP_BARS` explicitly so the planner and renderer agree (planner default is 2 as of 2026-11-09; `mix_simple.py` still falls back to 4 if the variable is unset). Use echo-outs rarely (at most ~10% of blends, spaced apart, only where the outgoing track runs out of music). Older mixes rebuild with these switched off.
6. Loop render -> tests + guardrails + listening (ears) check until every test passes and there are ZERO guardrail failures. A listening flag only fails a blend when the direct drum-alignment check agrees; otherwise it's a warning to mention. If a pair fails in every window, change the track order rather than forcing it. For a single off-beat bar, nudge that source bar (small negative or positive offsets) and re-render. Never loosen a threshold unless you prove the flag is a measurement artifact, and say so. If a mix fails tests for two or more rounds, send failing clips instead of silently iterating.
7. Hard rules: no stop/start changes; every transition is a real overlapping beat-matched blend with the outgoing groove still playing; never fade toward silence; loops may only repeat the phrase right before the loop point; never two lead vocals at once; keep the owner's approved mastering chain unchanged.
8. Score with the eval scorer, make a share copy (128k MP3), and deliver it with a timestamped tracklist, keeping only the latest version in each destination. The default visual is the twin-turntable renderer in `visuals/code/turntable_viz` (groove-dives on). Render it on a rented GPU after audio delivery (`runpod_render.sh` via `runjob.sh`) so the video never delays the MP3. Upload to YouTube as public by default, confirm with oembed, and use the title format in AGENTS.md. Decks alternate by construction (track k on deck k % 2, playing record never moves; `build_segs.py` gate + `src/tests/test_turntable_decks.py`). Record fly-off/spin-in (`FX_RECORD_SWAP`) and lights (`FX_LIGHTS`) are on by default (approved 2026-11-11); preview a window on CPU with `preview_window.sh`.
9. After delivery, and whenever the process or skills change, snapshot the mixer to git with `backup_mixer_to_git.sh` (no audio, video, or secrets). Clean up scratch files.
10. Log the owner's per-timestamp feedback to the ratings file, use it to calibrate the listening check, and turn every repeated complaint into a new guardrail.

## Variety, ratings and cleanup (2026-10-31)
- Ratings: 5 = good, 4 = OK, 3 or below = bad (src2/techniques.py pref_score). Never treat 3/5 as a pass.
- No 32-bar outgoing loops (LOOP32=0): they replayed the outgoing's last phrase 3x and sounded echoey. Echo-outs capped at ECHO_MAX=2 per mix.
- Technique menu + diversity rule in techniques.py (no technique on >40% of blends, never 3 in a row). Pinned plans with 32-bar 'la' windows are refused: re-run plan_search.py.
- render_and_test.sh restores stems/decodes first (restore_audio.py, bit-exact) and runs src/cleanup_after_build.sh at the end (AUTO_CLEAN=1). After delivery only sources, json/guard data, ratings and deliverables remain.
- Structure first (STRUCT=1): outro-over-intro, incoming drop on the outgoing's music end; blend length per pair (16 or 32) from structure + fit.
- Hard rule: no abrupt outgoing fade. FADE=tail, phrase-snapped bass handoff; test_structure_tail.py gates fader (<=3 dB/bar) and rendered tail (<=6 dB/bar).
- Gold reference blend: Mix 05 55:10, goddard. - Lilies -> Just Hold On (incoming loops 48-64, drop at 64 lands as Lilies ends). Lilies is a loved track (track_prefs.json).

## Beat grid, half-beat gate and diagnostics (2026-11-11)
- Prep runs a half-beat grid check (src2/halfbeat.py: snare-on-2-and-4 template vs the grid shifted half a beat) and moves an off-beat grid; re-check the whole library with halfbeat_library.py via runjob.sh after prep changes.
- Every render checks each blend for decks half a beat apart (drum phase AND onset xcorr must agree); mix_simple.py exits 3 with HALFBEAT FAIL and build QA gates it (test_release_halfbeat.py). Never disable the gate to ship.
- Every build writes one diagnostic figure per blend to deliver/<mix>/diagnostics (src2/blend_diag.py; generate-only); the daily protrans round writes deliver/protrans/diagnostics/daily_<date>.png.
- RCA by default: a mix or blend rated below 4, or a test that keeps failing during mix creation, gets a full root-cause pass (diagnostic figure, compare with the pro/gold blend, find the code path, fix the general rule, re-render, report before/after numbers).

## Long blends (2026-11-11)
- Window length (XBARS, length_pref) does not set how long a blend sounds; the fader shape and the low lanes do. FADE=long (src2/fade_long.py: early-in plateau + decisive outgoing exit on a phrase, one crossfader, guard-clean) is opt-in. It didn't hold on held-out (30.09 -> 29.61 / 26.47), so rules.json and the full-mix default FADE=tail are unchanged.
- The protrans event detector (blend_length / outgoing_cut) is noisy on NNLS gains: judge length/cut changes by the diagnostic figure and ears, not by those subscores alone.
- Long-blend RCA #2 (2026-11-11): FADE=long + LONG_SOLO_STRUCT=1 (exit ends where the outgoing's own energy drops) + LONG_SWAP=exit (bass swap at the exit start) holds held-out (30.09 -> 30.75). Adopted 2026-11-11 for practice blends, daily A/B and hill-climb (listener: "best one yet"); full mixes stay FADE=tail. Per-bar beat offsets on sparse intros and the snare band are not evidence of a half-beat; use the kick band on both-drum bars with xcorr r >= 0.15.
