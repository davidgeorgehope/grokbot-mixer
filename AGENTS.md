# AGENTS.md: start here

This is **grokbot-mixer**, an automated liquid drum & bass mix builder. It takes YouTube track IDs, time-stretches every track to 174 BPM and analyses grids, keys and per-bar features. It then renders beat-matched **crossfader** blends from a JSON plan and runs deterministic guardrails and tests. It produces an MP3, an audio-reactive video and a private YouTube upload.

Audio is **not** in this repo. You source your own tracks, legally.

## Read order
1. This file (end-to-end recipe)
2. `SETUP.md`: dependencies, paths, configuration
3. `docs/MIXING_RULES.md`: hard rules. Do not break them.
4. `docs/GUARDRAILS.md`: what each check catches and how to fix it
5. `docs/TASTE.md`: build a taste profile before picking tracks
6. `docs/LESSONS.md`: troubleshooting

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
- `pytest src/tests`.

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

### 8. Visuals (run from `visuals/code`, in the venv)
```
python3 analyze_mix.py ../../dj-mix-NN.mp3 mixNN_tracks.json mixNN_analysis.json --lag 0.055
python3 procedural_backdrops2.py <n_tracks> ../tex_mixNN                      # backdrop textures
FRAG=liquid2.frag python3 render_visuals2.py mixNN_analysis.json ../../dj-mix-NN.mp3 ../dj-mix-NN-visuals-1080p30.mp4 --tex ../tex_mixNN
```
- The tracks JSON format is `{"overlap": sec, "tracks": [{"artist","title","feat","start","mix_in"}]}`; see `mix03_60_tracks.json`.
- Preview a slice first with `--start S --dur 60`.
- Rendering is headless (moderngl EGL) and runs at about 20 fps at 1080p30, so a 60-minute mix takes about 1.5 hours.

### 9. YouTube (private)
```
python3 src/yt_upload.py --check          # mints token, prints channel (read-only)
python3 src/yt_upload.py dj-mix-NN-visuals-1080p30.mp4 --title "..." --description "$(cat yt_desc_NN.txt)" --tags dnb,liquid --privacy private
```
Always upload as private. The owner makes the video public. The token scope may not allow changing privacy afterwards.

### 10. Delivery
- `src/sync_icloud.sh <mp3> <tracklist.md> <track_no> "<Title>"`: tags the MP3 (ID3 plus a generated cover) and copies it atomically (tmp then `mv`) over ssh to `$HOST`'s iCloud Drive "DJ Mixes". It never deletes. To deliver some other way, replace the ssh/iCloud lines.
- Send the share MP3, the tracklist and the YouTube link to the listener. Ask for minute-stamped feedback and log it to `eval/example_ratings.jsonl` (your own ratings file).

### 11. Back up the code
`bash /workspace/backup_mixer_to_git.sh` (private repo; see the script).

- EQ default since Mix 05: SWAP_PHRASE=1 HIGH_SWAP=1 (phrase-snapped bass swap + separate >2 kHz swap). Set both to 0 to reproduce Mix 01-04 (meta 'eq_mode' records the mode).
- Delay-tail exit: ECHO_OUT (default on since Mix 05; 0 rebuilds older mixes) adds a filtered 1-beat delay tail after the outgoing crossfader end on <=10% of blends (shortest runway first); tests in src/tests/test_echo_out.py.
