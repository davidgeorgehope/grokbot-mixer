# Process (current)

This is the full weekly mix path as of 2026-11-09. Code, tests, visuals, skills, and this document belong in git. Audio, video, cookies, API keys, and tokens do not.

For a new checkout, start with `AGENTS.md` and `SETUP.md`, then follow the numbered recipe there. This file records the current defaults and the scheduled jobs around that recipe.

## Weekly mix

Build a new liquid/melodic drum-and-bass mix of **at least 60 minutes**, about 18–22 official-upload tracks, with an emotional arc and tight Camelot flow. Verify each track's true tempo and use drum-and-bass-tempo versions only.

1. Pick and plan on paper first (`plan_search.py`, `STRUCT=1`, `FADE=tail`, `LOOP32=0`, `ECHO_MAX=2`). Prefer unused favourites and recent finds; do not invent tracks.
2. Fetch audio on a **residential machine** with browser cookies (cloud IPs are usually blocked), then prep with `add_track.sh`.
3. Render and test through `src/render_and_test.sh` until **every test passes and there are zero guardrail failures**. Never deliver a failing mix; if a pair cannot pass, change the order or send short clips instead.
4. Long jobs run through `jobs/runjob.sh`. That writes `jobs/<name>.status` (`running`, then `done` or `failed` plus the exit code) and a `.log`. An optional job-finished webhook (`JOB_WEBHOOK_URL` and `JOB_WEBHOOK_KEY` in the environment, never committed) should fire on finish or failure. Check the status file; never guess.
5. Deliver audio first, before visuals:
   - 128k MP3 to the configured cloud drive (latest mix only)
   - 320k master and timestamped tracklist to iCloud "DJ Mixes" via `src/sync_icloud.sh` (latest only)
6. Render the **twin-turntable** visual (`visuals/code/turntable_viz`, v2 layout, `GROOVE_DIVE=1`) on a rented GPU with `runpod_render.sh` via `runjob.sh`. This is the default visual; do not switch styles. Audio must never wait on the video. Confirm no GPU pods are left running. Expected cost is about $1–2 and about 1.8 hours per hour of mix.
7. Upload the video to YouTube **public** by default (`src/yt_upload.py`, title `DJ Grok Bot – Mix NN | Liquid Drum & Bass`) with the timestamped tracklist in the description. Confirm it is public via oembed.
8. Snapshot the mixer to git with `backup_mixer_to_git.sh` (see below). Clean scratch files. Leave only sources, json/guard data, ratings, and deliverables.

Bass handoff: the planner default is `BASS_SWAP_BARS=2` (set 2026-11-09 after a held-out pro-DJ gain). `mix_simple.py` still falls back to 4 if the environment variable is unset, so set it explicitly when rendering so the plan and the mix agree. Guardrails still judge the result.

## Visuals

Default: twin-turntable renderer, driven by the mix's real timing data, with rare groove-dive camera moves at real drops or breakdowns. The rented-GPU script walks GPU types (Community first, then Secure) and always terminates the pod. Put the API key in `RUNPOD_API_KEY` or `$HOME/.runpod_api_key`; never commit it. Do not fall back to a many-hour CPU render unless there is time and the GPU path has already been reported as failing.

Decks (fixed 2026-11-11 after Mix 08 v2): a playing record never changes decks. Track 0 starts on deck A; each incoming track loads on the idle deck (the one whose record stopped), so track k is always on deck k % 2 and decks alternate A/B/A/B. `build_segs.py` writes each segment's decks in physical order (`decks[0]` = deck A) with `out_deck` saying which holds the outgoing track, and refuses to build if `deck_state.walk_segments` finds a record changing decks. Mix 08 v2 and earlier had the bug: every segment put the outgoing track on deck A, so the record that had just taken over on deck B jumped to deck A at each segment cut (midway between blends). Test: `src/tests/test_turntable_decks.py`. Old videos are not re-rendered.

Effects, **on by default (the listener approved 2026-11-11; set =0 to disable)**: `FX_RECORD_SWAP=1` (stopped record flies off its deck before the cut; the next record spins in and flips onto that deck before it starts) and `FX_LIGHTS=1` (beat-synced truss beams plus deck-coloured ambient glow, driven by the mix's low end). Both pass through `render_full.sh` and the Runpod scripts. Cheap CPU previews of a window: `visuals/code/turntable_viz/preview_window.sh` (`META MIX FROM TO OUT`, seconds) via `runjob.sh`.

## YouTube

`yt_upload.py` defaults to **public**. That replaced the old private-by-default rule (2026-10-30). Confirm publicity with oembed before sending the link.

## Git backup (required)

The working tree may live outside git. After every mix, and whenever code, skills, or process docs change, run:

```
bash /workspace/backup_mixer_to_git.sh
```

It copies allowed source files (no audio, video, or secrets) into `grokbot-mixer/` on the private crate repo and, if the public audit passes, syncs [grokbot-mixer](https://github.com/davidgeorgehope/grokbot-mixer). The public audit is fail-closed (secrets, personal machine names, and similar strings abort the public push; the private snapshot can still succeed). Skills in `skills/` are included in that snapshot.

## Other scheduled jobs

These are the assistant routines that surround the mixer. Their prompts live with the assistant; the behaviour they rely on must be in this repo.

- **Friday fresh finds** — real, verified mixes and tracks in the listener's lane; do not invent links.
- **Daily pro-transition recreation** — recreate one real pro DJ liquid transition from source tracks, score it, and try a general rule change; keep the change only if the held-out score improves. Filter out talk-over and fade-gap-talk-drop blends.
- **Nightly pro-transition hill-climb** (Sun–Fri) — bounded automatic rule search; commit a keep back to the repo.
- **Daily mix disk cleanup** — delete scratch; keep sources, json/guard data, ratings, and deliverables.
- **Weekly mix watchdog** — Saturday morning checks that the weekly mix is on track.
- **Job finished webhook** — wakes the assistant when a `runjob.sh` job finishes or fails, so the next step can run without polling.

## Hard delivery rules

- Never loosen a test threshold to ship a mix.
- Never deliver a mix that failed guardrails or tests.
- If a mix fails tests for two or more rounds, send failing clips instead of silently iterating.
- Keep the approved mastering chain unchanged.
- One monotonic equal-power crossfade per blend; no stop/start changes; no fade toward silence.

## Beat-grid and per-blend diagnostics (2026-11-11 RCA)

Shine In -> Dusk To Dawn (rated 2/5) played half a beat apart: prep only ever chose among whole-beat downbeats, so a grid locked onto the off-beat was never tested. Now:

- **Prep-time half-beat check** (`src2/halfbeat.py`, called from `prep.py` and `fixgrid.py`): folds kick (30-150 Hz) and snare (1.5-5 kHz) onsets over the drum bars and scores the grid against the same grid shifted half a beat (template: snare on 2 and 4, kick on 1). Half-beat wins by >= 0.5 z over >= 16 drum bars -> the grid is moved (old grid kept in `st/<id>.json.prehalf`, bar features resampled, caches dropped). Whole library: `cd src2 && bash ../jobs/runjob.sh <name> python3 halfbeat_library.py [--apply]` (restores cleaned audio for the check and removes it again; results in `eval/halfbeat_library.jsonl`).
- **Render-time half-beat gate** (`halfbeat.blend_check`, run on every candidate in `mix_simple.py` and in `src/build_qa/test_release_halfbeat.py`): a blend fails only when both decks' drum phases sit >= 0.25 beat apart AND the per-bar onset xcorr locks better at a half-beat lag than at lag 0. `mix_simple.py` exits 3 with `HALFBEAT FAIL` on a failing render (`HALFBEAT_GATE=0` only for diagnosis). The old drum-fight R (+-BEAT/8) is unchanged.
- **Sections vs structure** (opt-in, `SECTIONS_RECONCILE=1`): takes drop1 from `protrans/structure.py` when that drop is phrase-aligned and 1-8 bars later (Dusk To Dawn 56 -> 64). Off by default: on the held-out pro cohort it dropped test 30.09 -> 29.50 (the pro brings Dusk To Dawn in earlier, not later). The incoming-quiet-bar bass-swap guard (`SWAP_QUIET_DB`, e.g. 15) is opt-in for the same reason (Pola & Bryson swap on a bass fill, as the pro did).
- **Standard diagnostic figure** (`src2/blend_diag.py`): engine fader/low lanes, rendered lows and their sum (bass holes), per-bar deck offset with the half-beat verdict, one-bar drum fold per deck; with a pro clip also the fitted per-deck pro gains and the pro-vs-ours deck lock. Generate-only, never a gate. Mix builds write `deliver/<MIX_NAME>/diagnostics/` from the build-QA suite (`MIX_DIAG=0` skips); the daily protrans round writes `deliver/protrans/diagnostics/daily_<date>.png` (`protrans/daily_diag.py`).
- **RCA by default**: when the listener rates a mix or blend below 4, and when the same test keeps failing during mix creation, do this level of root-cause analysis by default: diagnostic figure for the blend(s), compare against the pro/gold reference, name the code path, fix the general rule, re-render, and report numbers before/after.

## Long blends (2026-11-11 long-blend RCA, Shine In -> Dusk To Dawn)

Why `length_pref` / linger / XBARS never changed how long a blend *sounds*:

- `length_pref` (protrans/recreate.py:170,178) only adds 0.15 cost to a family whose window is not 32 bars; every candidate family already shares the 32-bar `nat_long` window, so it never changes the render. `linger_pen_w` / `breakdown_pen_w` / `phase_pref_w` are absent from rules.json, so recreate.py:189-193 skip them; even set, they only re-rank the ~10 family windows.
- XBARS / the window's X (src2/mix_simple.py:23) sets the *window*, not the audible overlap. The overlap comes from the fader shape (`_xpos`, mix_simple.py:131) and the low lanes (mix_simple.py:305-313): under FADE=lin the incoming sits under -12 dB for the first ~5 bars and the outgoing is only gone at x=1, the window end; the STRUCT bonus (mix_simple.py:225) pins that end on the outgoing's music end, so it lingers through its outro.
- The scorer's events (protrans/score.py:139-170 on NNLS deck gains, protrans/diagnose_gap.py:280-302) are noisy: a muted deck still gets fitted at -7..-12 dB, so `outgoing_cut` wanders to the clip end or None, and sparse incoming intros break the "both within 12 dB" run. The pro's own events for the same clip move between runs (Joe pair blend 15 vs 17 bars, cut 23 vs 18). Measurement, not engine; flagged, scorer unchanged.

New opt-in fader shape **FADE=long** (`src2/fade_long.py`, tests `src/tests/test_fade_long.py`): same single monotonic equal-power crossfader, inside X1 and the abrupt-fade rule. Incoming up from -24 dB to about -5.6 dB over 2 bars, plateau with both decks in, then a decisive outgoing exit (linear in dB, <= 3 dB/bar, 8 bars) that ends on a 4-bar boundary `LONG_SOLO` bars before the window end. Knobs: `LONG_RISE`, `LONG_XP`, `LONG_XP2`, `LONG_EXIT`, `LONG_SOLO` (also passed through rules.json by recreate.apply_rules).

Results (33 pairs, scorer v3, baseline train 30.97 / test 30.09): `FADE=long LONG_SOLO=16` 30.89 / 29.61 and `LONG_SOLO=8` 32.35 / 26.47. Both held-out drops, so not kept (logged in protrans/logs/tune_log.jsonl). rules.json and the full-mix default (FADE=tail) are unchanged. Joe pair alone: 33.97 -> 48.22 with SOLO=16 (clip deliver/protrans/rca_2026-11-11_long.mp3, figure diagnostics/rca_2026-11-11_long.png), waiting on the listener's ears. For full mixes, SOLO>0 on a 32-bar window would also need the ride rule in test_outgoing_fader_tail_is_gradual (outgoing above -20 dB for >= 0.35 X - 1 bars after the swap), so try it there only as a 16-bar window, never by loosening the test. The 0.35 ride fraction was later calibrated against the same 33 admitted pros to 0.15 (see below); the full-mix default is still FADE=tail.
- Incoming bass level-match pre-drop: not possible inside the hard rules (deck gain comes only from the crossfader; X1 requires the low lane to go exactly 0->1), so it was not done.

### Long-blend RCA #2 (the listener rated FADE=long LONG_SOLO=16 3.5/5, 2026-11-11 13:07 ET)
Figure: `deliver/protrans/diagnostics/rca_2026-11-11_long_rca.png` (lows and outgoing level vs the pro, kick/snare-band beat offsets, which Shine In bars each plays).
- **Beat offset is fine.** Kick band (30-150 Hz) on bars where both decks drum and the xcorr locks (r >= 0.15, 8 bars): +22 ms median. The pro's own decks sit 36 ms apart (deck_lock 0.104 beat). The -151 ms half-beat "lag" and the 91 ms median come from the 1.5-5 kHz band (Dusk To Dawn's off-beat hats, -124 ms) and from sparse intro bars with r < 0.15. Measurement artifact; the drum-phase gate (ok) is the trustworthy half.
- **The 19.9 dB low-end dip is in the pro too.** Pro mix lows drop about 20 dB on its cut bar, then sit 7-15 dB down until Dusk To Dawn's drop. Dusk To Dawn has little bass before then (dry lows -24..-43 dB vs Shine In -18). Not an engine fault.
- **Exit** (ranked cause #1): Joe cuts Shine In within 1 bar at its own bar ~127, exactly where Shine In dips 4-7 dB by itself, on Dusk To Dawn's bar-31/32 phrase. Ours faded Shine In's full-energy drop (bars 216-224) over 8 bars, with the bass swap starting just before.
- **Section** (#2, by design): Joe plays Shine In bars ~109-127; we play 208-232 (play-to-outro rule). Not changed.
- **Fix (general, opt-in):** `LONG_SOLO_STRUCT=1` ends the exit where the outgoing's own level drops >= 4 dB under its body (fade_long.struct_solo; falls back to LONG_SOLO). `LONG_SWAP=exit` centres the bass swap on the exit start (fade_long.swap_pos), so the lows and the level leave together. Joe pair: exit ends at Shine In bar 232 (Dusk To Dawn phrase 48), swap 222-226; score 42.01 (SOLO=16 48.22, engine 33.97). Clip `deliver/protrans/rca_2026-11-11_long_fix.mp3`.
- **Held-out** (33 pairs, scorer gain-events-v3-beatid, same ids and splits as the v3 baseline): `FADE=long LONG_SOLO=16 LONG_SWAP=exit LONG_SOLO_STRUCT=1` train 31.14 / test 30.75 vs 30.97 / 30.09. Passes the held-out bar. **Adopted 2026-11-11 1:37 PM ET** after the listener heard `rca_2026-11-11_long_fix.mp3` ("That's the best one yet I think", better than 4/5). protrans/rules.json now has `FADE=long LONG_SOLO=16 LONG_SWAP=exit LONG_SOLO_STRUCT=1`, and recreate.py DEFAULTS carries the three LONG_* keys, so practice blends, the daily A/B and the nightly hill-climb use them. The full-mix default stays `FADE=tail`; plan_search.py is unchanged because it plans full mixes and the LONG_* keys only act when FADE=long.
- **Test fixtures and cleanup:** post-delivery cleanup deletes Mix 05-08 stems, so `test_seesaw::test_loop_fill_is_soft_penalty` restores the two Mix 06 stems it needs with `restore_audio.py` (bit-exact) and deletes them again afterwards.
- **Why SOLO=16 lost held-out (29.61):** per subscore on test, stem curves +2.5, deck curves +0.9 and blend length +5.7 all improved. The loss came from the event-timing terms: bass_swap -10.1 and outgoing_cut -4.7. Those are the NNLS event detectors, and the pro's own events move between runs for the same clip (Joe pair blend 15 vs 17 bars, cut 23 vs 18). So the scorer's event terms penalise the shape while its curve terms prefer it. Reported, not changed (no threshold edits without more evidence). The fix still loses on bass_swap timing (-8.1 test).


### Full-mix proof of FADE=long (Mix 08, 2026-11-11)

Test render: same Mix 08 v2 tracklist and plan as [mix08_r11c](https://youtu.be/jRTCAA4PpLY) (`plan_mix08_r11c.json`, `NUDGE=nudge08_r9c.json`, `HIGH_OFS=8`), audio only, with the adopted long keys (`FADE=long LONG_SOLO=16 LONG_SWAP=exit LONG_SOLO_STRUCT=1`) and a 4-bar bass handoff. Wrapper: `mix08/long_test.sh` via `jobs/runjob.sh`. The weekly full-mix default stays `FADE=tail` (render08.sh, search.sh, and `mix_simple.py`'s unset default) until the listener rates the A/B clips.

- **Ride calibration** (`src/calib/ride_vs_pro.py`, writeup `docs/PRO_CALIBRATION_2026-11-11.md`): the old ride rule (outgoing above -20 dB for >= 0.35*X - 1 bars after the bass swap) failed 5 of 33 admitted pros (p5 of pass_frac = 0.149). `RIDE_FRAC` in `src/build_qa/test_release_structure_tail.py` is now 0.15, the measured pro p5, same method as the bass-dip guards. The 3 dB/bar fader cap is unchanged. Tests: `src/tests/test_ride_calibration.py`. Not loosened by hand. FADE=long on a 32-bar window passes 0.15 and failed 0.35.
- **Planner and guard fixes** that were assuming a tail fade, or that broke under a long overlap, with tests in `src/tests/test_fade_long.py` and `src/tests/test_c2_and_high_swap.py`:
  - `high_at` checks x at the high-swap *centre* (bar+2), not the start, so a legal 16-bar high swap is not placed at x=0.90.
  - C2's "first half" is the first half of the *designed* overlap (xfader outgoing still above -10 dB), not the raw window (LONG_SOLO leaves the outgoing gone by the window midpoint). Threshold -10 dB unchanged.
  - Under FADE=long, `swap_at` returns the long fade's own swap (`fade_long.swap_pos`, exit start, x=0.5). The tail planner's 4-bar phrase snap can have an empty 0.2-0.65 candidate list on a long curve; no silent nearest-bar fallback. `exit_start` / `swap_pos` honour `hold`. `log10` in `_score` is guarded.
  - Under FADE=long, the bass handoff is 4 bars unless a pin forces 2 (a 2-bar handoff stacked on the exit took 6.4 dB off Ember, over the 6 dB/bar rendered-tail cap).
  - `cap_solo_incoming` only caps solo for a *second-half* thin stretch of the incoming, measured against the incoming's own first-half median, not the full-track body (an intro is often a few dB under the drop).
  - `vocal_hold` delays the incoming rise through the last early clash (k <= 8), not only the first contiguous run.
  - `solo_before_incoming_vocal` raises solo so the outgoing is already under VOC_GAIN 0.3 when the incoming is singing after the opening (leading clashes are `vocal_hold`'s job).
- **Test mix `mix08_long1e`:** V1 and E1, X1, C2, bass-gap and abrupt-tail all cleared after those fixes. Three official guardrail hits remain, not loosened: L1 at 2:45 (trans 0) and 16:00 (trans 6), both at the exact mid-point of the designed 4-bar bass handoff, where two similar quiet subs (~-39 dB) sum 3.1-3.5 dB over the louder deck at about -35 dB; and N1 at 13:42 (trans 5), incoming first audible 11 ms off the 10 ms grid (1 ms over the line) on a hold-delayed entry bar. Moving the swap centre one bar into the exit still includes that mid-cross bar under a 4-bar width and would put a later centre past x=0.65, so it was not blindly rebuilt. Full RCA (bar-by-bar vs v2, ranked causes, fix plan): docs/RCA_2026-11-11_mix08_long1e.md. Figures in deliver/mix08_long1e/rca/.
- **A/B clips** of four real blend windows (16 bars before the blend, 8 after; a short tick marks the blend start, always about 0:22 into the file) are in `deliver/mix08_long_ab/`. Filenames include the mix time where the blend starts. Answer keys must never live under `/workspace/mixes` or in any path `backup_mixer_to_git.sh` copies (that script includes `*.json` and `*.jsonl`); keep them outside the mixer tree or in a git-ignored path.
