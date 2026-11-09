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
