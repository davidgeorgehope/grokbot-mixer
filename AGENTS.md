# AGENTS.md: start here

This is **grokbot-mixer**, an automated liquid drum & bass mix builder. It takes YouTube track IDs, time-stretches every track to 174 BPM and analyses grids, keys and per-bar features. It then renders beat-matched **crossfader** blends from a JSON plan and runs deterministic guardrails and tests. It produces an MP3, a twin-turntable video and a public YouTube upload.

Audio is **not** in this repo. You source your own tracks, legally.

## Read order
1. This file (end-to-end recipe)
2. `SETUP.md`: dependencies, paths, configuration
3. `docs/MIXING_RULES.md`: hard rules. Do not break them.
4. `docs/GUARDRAILS.md`: what each check catches and how to fix it
5. `docs/TASTE.md`: build a taste profile before picking tracks
6. `docs/PROCESS.md`: current defaults (visuals, GPU render, public YouTube, git backup, scheduled jobs)
7. `docs/LESSONS.md`: troubleshooting
8. `skills/`: assistant skills for this pipeline; keep in sync when the process changes

## Layout and paths
The scripts hardcode `/workspace/mixes` with the working dir at `/workspace/mixes/src2`. The simplest setup is to put this repo's contents at `/workspace/mixes` (`src/`, `src2/`, `eval/`, `visuals/code/`). Otherwise, search and replace `/workspace/mixes` (see SETUP.md).
Working data lives in `src2/` and is git-ignored: `*.m4a` (downloads), `wav/` (decoded), and `st/<id>.wav` / `st/<id>.json` (stretched audio plus grid and per-bar features, including cached vocal and drum activity).

## Recipe (all commands run in `src2/` unless noted)

### 1. Pick tracks
Aim for 18–22 tracks for a mix of at least 60 minutes. Each track runs about 4–5 minutes, and blends overlap by 16–32 bars.
- Use official uploads only (label or artist "- Topic" channels). Drop tracks with no official upload.
- Skip tracks whose drop is at bar 0 (no runway) unless they have a clean 16-bar phrase to loop.
- Use the taste profile (docs/TASTE.md). Order by key and energy: `order.py` is a simulated-annealing orderer over a Camelot cost and an energy cost. Edit the `T` dict inside it (id → (camelot, energy 1–5, title)); it writes `order2.json`.

### 2. Fetch (on a residential, non-datacenter machine)
YouTube blocks cloud and datacenter IPs. Run yt-dlp on a home machine with browser cookies, then copy the files to the render box:
```
yt-dlp --cookies-from-browser chrome -f 'ba[ext=m4a]' -o '%(id)s.m4a' https://www.youtube.com/watch?v=<ID>
scp <host>:'*.m4a' /workspace/mixes/src2/
```
`src/sync_set.sh` shows the same pattern, run over `ssh $HOST`.

### 3. Prep and analysis
```
bash add_track.sh <ID> [<ID>...]
```
This decodes the track, measures its BPM, stretches it to 174 and writes the grid. It also detects the key and writes per-bar features (all/low/hat dB, plus voc/drums from **temporary** demucs stems, which are deleted afterwards) and runs a local phase check. Add each new key to `src/tests/keys_extra.json`.
Optional tools: `regrid.py <ID>` (exact linear grid) and `retempo.py <ID>` (re-stretch using measured drift).

### 4. Plan JSON
A plan is a list of steps in play order, e.g. `src2/plan_60f.json`:
```json
[{"id": "N4mzOUMNsuI", "tech": "first", "kw": {"pre": 32}},
 {"id": "yogt46dJJ4g", "tech": "blend", "kw": {"pre": 16}, "anchor": true}]
```
- `id` must match `st/<id>.*`.
- `tech` is `first` or `blend`.
- `anchor` marks a showcase track that must play long enough.

`mix_simple.py` picks each blend's out and in windows itself. It scores every phrase-aligned 16-bar candidate by simulating V1 (vocal clash), L1 (double bass), O1 (overlap) and C2 (outgoing level) under the crossfader. If no clean window exists, it loops a clean instrumental phrase of the outgoing track.

### 5. Render and test
```
bash src/render_and_test.sh plan_X.json NAME /workspace/mixes/dj-mix-NN.mp3 GAIN_DB [nudge.json]
```
This runs, in order:
- `mix_simple.py`, which writes `NAME_raw.wav` and `NAME_meta.json` (including each blend's logged crossfader curve).
- `master.sh`, which writes `NAME_master.wav` and a 320k MP3. Pick a `GAIN_DB` that lands around -9 LUFS.
- `guardrails.py --png`, which writes `guard_NAME/`.
- `pytest src/tests src/build_qa` (fixture regressions plus the selected live-build acceptance gates, before cleanup).

The script prints `RESULT guardrails_exit= pytest_exit=`. For timing fails (F1/N1), run `autofix.py` to write warp nudges, then re-render. Never loosen a threshold.

### 6. Eval score
The scorer compares the mix against the pro-DJ profile `eval/pro_profile.json`.
```
python3 src/eval/analyze_pro_set.py <mix.wav> --anchors <tracklist secs,...> [--name NAME]   # -> eval/sets/NAME.json  (run from /workspace/mixes)
python3 src/eval/score_mix.py eval/sets/NAME.json                                           # -> eval/scores/NAME.json
```
The score is advisory: it is not yet calibrated to the listener (eval/README.md). Guardrails gate the release; the score doesn't.

### 7. Tracklist
`python3 src/gen_tracklist.py src2/NAME_meta.json dj-mix-NN-tracklist.md "DJ Mix NN – Liquid"` writes times from the meta and Camelot keys.

### 8. Visuals
The default visual is the twin-turntable renderer in `visuals/code/turntable_viz` (v2 layout, driven by the mix's real timing data, with occasional groove-dive camera moves at real drops or breakdowns, `GROOVE_DIVE=1`). Do not switch to other visual styles for a weekly mix. Render the full video **after** audio delivery, on a rented GPU, so a slow render never delays the MP3:

```
META=/workspace/mixes/src2/<mixNN_meta.json> MIX=/workspace/mixes/deliver/NN/dj-mix-NN-128k.mp3 \
  TRACKLIST=/workspace/mixes/deliver/NN/dj-mix-NN-tracklist.md \
  OUT=/workspace/mixes/visuals/dj-mix-NN-visuals-1080p30.mp4 GROOVE_DIVE=1 \
  /workspace/mixes/jobs/runjob.sh turntable-mixNN bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh
```

The script walks several GPU types (Community first, then Secure) and always terminates the pod. Put the API key in `RUNPOD_API_KEY` or `$HOME/.runpod_api_key`; never commit it. Expect about 0.56× realtime (roughly 1.8 hours per hour of mix, about $1–2). Afterward, confirm no pods are left running. See `docs/PROCESS.md`.

### 9. YouTube (public by default)
```
python3 src/yt_upload.py --check          # mints token, prints channel (read-only)
python3 src/yt_upload.py dj-mix-NN-visuals-1080p30.mp4 --title "DJ Grok Bot – Mix NN | Liquid Drum & Bass" --description "$(cat yt_desc_NN.txt)" --tags dnb,liquid --privacy public
```
Default privacy is public (since 2026-10-30). Confirm the uploaded video is public via oembed before sending the link.

### 10. Delivery
- `src/sync_icloud.sh <mp3> <tracklist.md> <track_no> "<Title>"`: tags the MP3 (ID3 plus a generated cover) and copies it atomically (tmp then `mv`) over ssh to `$HOST`'s iCloud Drive "DJ Mixes". It never deletes. To deliver some other way, replace the ssh/iCloud lines.
- Send the share MP3, the tracklist and the YouTube link to the listener. Ask for minute-stamped feedback and log it to `eval/example_ratings.jsonl` (your own ratings file).

### 11. Back up the code
After every mix, and whenever the process, skills, or code changes, snapshot the mixer (no audio, video, or secrets):

```
bash /workspace/backup_mixer_to_git.sh
```

That updates `grokbot-mixer/` on the private crate repo and, if the public audit passes, syncs https://github.com/davidgeorgehope/grokbot-mixer. Skills in `skills/` are part of that snapshot. Details are in `docs/PROCESS.md`.

- EQ default since Mix 05: SWAP_PHRASE=1 HIGH_SWAP=1 (phrase-snapped bass swap + separate >2 kHz swap). Set both to 0 to reproduce Mix 01-04 (meta 'eq_mode' records the mode).
- Delay-tail exit: ECHO_OUT (default on since Mix 05; 0 rebuilds older mixes) adds a filtered 1-beat delay tail after the outgoing crossfader end on <=10% of blends (shortest runway first); tests in src/tests/test_echo_out.py.
