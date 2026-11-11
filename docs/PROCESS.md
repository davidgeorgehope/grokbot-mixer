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

Optional effects, **off until the listener approves them**: `FX_RECORD_SWAP=1` (stopped record flies off its deck before the cut; the next record spins in and flips onto that deck before it starts) and `FX_LIGHTS=1` (beat-synced truss beams plus deck-coloured ambient glow, driven by the mix's low end). Both pass through `render_full.sh` and the Runpod scripts. Cheap CPU previews of a window: `visuals/code/turntable_viz/preview_window.sh` (`META MIX FROM TO OUT`, seconds) via `runjob.sh`.

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
