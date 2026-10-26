# AGENTS.md: start here

This is **grokbot-mixer**, an automated liquid drum & bass mix builder. It takes YouTube track IDs, time-stretches every track to 174 BPM, analyses grids, keys and stems, and renders beat-matched blends from a JSON plan. It runs deterministic guardrails and tests until there are zero failures, then produces a share MP3, an audio-reactive video and a private YouTube upload.

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
Working data lives in `src2/` and is git-ignored:
- `*.m4a`: downloads
- `wav/`: decoded
- `st/<id>.wav` / `st/<id>.json`: stretched audio plus grid
- `sep/htdemucs/<id>/`: stems
- `fx/`: riser/impact/roll

## Recipe (all commands run in `src2/` unless noted)

### 1. Pick tracks
Aim for 18–22 tracks for a mix of at least 60 minutes. Each track runs about 4–5 minutes, and blends overlap by 16–32 bars.
- Use official uploads only (label or artist "- Topic" channels). Drop tracks with no official upload.
- Skip tracks whose drop is at bar 0 (no runway), unless you accept a drums-stem loop intro.
- Use the taste profile (docs/TASTE.md). Order by key and energy: `order.py` is a simulated-annealing orderer over a Camelot cost and an energy cost. Edit the `T` dict inside it (id → (camelot, energy 1–5, title)); it writes `order2.json`.

### 2. Fetch (on a residential, non-datacenter machine)
YouTube blocks cloud and datacenter IPs. Run yt-dlp on a home machine with browser cookies, then copy the files to the render box:
```
yt-dlp --cookies-from-browser chrome -f 'ba[ext=m4a]' -o '%(id)s.m4a' https://www.youtube.com/watch?v=<ID>
scp <host>:'*.m4a' /workspace/mixes/src2/
```
`src/sync_set.sh` shows the same pattern, run over `ssh $HOST`.

### 3. Prep and analysis (per track; `add8.sh` is the template)
```
ffmpeg -loglevel error -y -i <ID>.m4a -ar 44100 -ac 2 wav/<ID>.wav
B=$(python3 pbpm.py wav/<ID>.wav | awk '{print $2}')     # precise BPM (170–177 search)
python3 prep.py wav/<ID>.wav $B          # rubberband-stretch to 174 BPM -> st/<ID>.wav + grid st/<ID>.json (beats, downs, phrases)
python3 -m demucs -n htdemucs -j 8 -o sep st/<ID>.wav    # stems -> sep/htdemucs/<ID>/{vocals,drums,bass,other}.wav
python3 fixgrid.py                       # re-pick downbeat/phrase phase for all st/*.json (kick+snare pattern)
python3 barfeats.py  (or barfeats2.py)   # per-bar dB: all/low/hat (+voc/drums from stems) -> st/<ID>.json "bar"
python3 keys.py                          # essentia key (edma/bgate/krumhansl/temperley) -> keys_full.json, Camelot
python3 runs.py                          # bass runs (drops) per track in order2.json
python3 phasechk.py <ID>                 # local phase check; finds off-grid sections
```
Optional tools:
- `regrid.py <ID>... [--dry]`: replace the downbeats with an exact linear 174 grid. Use it when breakdowns slice the grid; it backs up to `.json.bak`.
- `retempo.py <ID>`: re-stretch using measured drift.
- Build the FX once: `mkdir -p fx && python3 makefx.py`. That writes `riser8`, `riser4` and `impact`. `mix3.py` also loads `fx/roll8.wav`, which no script in the repo generates, so supply your own 8-bar snare roll as `fx/roll8.wav`.
- The tests read keys from `src/tests/keys_extra.json` (id → Camelot). Add new tracks there too.

### 4. Plan JSON
A plan is a list of steps, one per track, in play order. Example from `src2/plan_60d.json`:
```json
[
 {"id": "N4mzOUMNsuI", "tech": "first", "kw": {"pre": 32}},
 {"id": "yogt46dJJ4g", "tech": "blend", "kw": {"pre": 16, "build": true}},
 {"id": "rJuyd8koFAU", "tech": "blend", "kw": {"pre": 24, "build": true}, "anchor": true},
 {"id": "K6dMmz0jLcI", "tech": "blend", "kw": {"pre": 32, "build": true, "tail_drums": "early"},
  "anchor": true, "breakdowns": [[99, 103]]}
]
```
Step fields:
- `id`: the YouTube ID, which must match `st/<id>.*`.
- `tech`: `first` | `blend` | `double` | `echo`. Default to `blend`. `echo` is banned by default (see MIXING_RULES.md).
- `anchor` (bool): a showcase track. `test_anchor_tracks_long_enough` requires it to play long enough.
- `breakdowns` (`[[src_from, src_to]]`): the record's own breakdown bars (at most 4 bars each). Guardrails E1 and G1 treat these as intentional.
- `allow_echo` (bool): the only way to get an `echo` step past guardrail X1.

`kw` arguments are passed straight to the functions in `mix3.py`:
- `first(pre)`: start `pre` bars before the first drop.
- `blend(pre=32, fade=16, hpf=False, acap=None, min_overlap=16, tail_drums=False, loop_intro=False, build=False, which=-1)`:
  - `pre`: bars of the incoming track before the bass swap.
  - `fade`: bars after the swap while the outgoing track's mids and highs fade (held 8 bars first).
  - `build`: `true` gives an 8-bar HPF sweep, a riser and an impact landing on the swap. `"roll"` adds a snare roll.
  - `tail_drums`: `true` switches the outgoing track to its drums stem after the swap. `"early"` gives a drum bridge: the outgoing mids and vocals ramp out over 2 bars, which you need across key changes.
  - `loop_intro`: replace the incoming intro with a clean drums-stem loop.
  - `hpf`: HP sweep on the outgoing track.
  - `acap`: offset in bars for an 8-bar acapella of the outgoing track's strongest vocal phrase.
  - `which`: which of the outgoing track's bass runs to swap at (`-1` = last, `-2` = the one before).
- `double(pre=16, hold=16, out=8, which=-1, at=0, slam=False)`: a double drop. Drops are layered and the incoming track takes the bass. `slam` keeps the incoming silent until the drop.
- `echo(pre=32, which=-1, roll=True, lead=0, ride=False, outro=0)`: an echo-out. It is forbidden unless `allow_echo` is set.

Vocal clashes are muted automatically per bar using the demucs vocal stems. Runway that's too short is loop-extended from a clean drums-stem section, so use loops only when the track has no runway.

Preview without rendering: `python3 mix3.py --plan plan_X.json --dry` prints the length in minutes and every transition. Make sure the length is at least 60 minutes.

### 5. Render, test and guardrail loop (until zero fails)
```
NUDGE=nudge60d.json bash ../src/render_and_test4.sh plan_X.json NAME /workspace/mixes/dj-mix-NN.mp3 GAIN_DB
```
This does the following:
- `mix3.py --plan ... --out NAME` writes `NAME_raw.wav` and `NAME_meta.json`.
- `master.sh` (compressor, gain, limiter, 320k MP3) prints LUFS and true peak. Pick `GAIN_DB` (e.g. 9.2) to land around −9 LUFS integrated.
- `guardrails.py --name NAME --mp3 ... --nudge ... --png` writes `guard_NAME/guardrails.json` plus a PNG per transition.
- `pytest src/tests` runs the tests.

It exits non-zero on any failure (`GUARDRAILS_EXIT`, `TESTS_EXIT`).

Automatic loop for timing failures (F1/N1): `bash ../src/iterate.sh plan_X.json NAME OUT.mp3 GAIN nudge60d.json [MAX=4]`. It runs `autofix.py`, which writes warp nudges into the nudge JSON. It stops when non-timing failures remain; fix those by editing the plan (`pre`, `which`, `tail_drums`, `breakdowns`, order) and re-run. **Do not ship until guardrails report `n_fail: 0` and pytest is all green.** Look at the PNG strips for every transition: you can't listen, but the waveforms, grid, LUFS, sub and chroma show what's wrong.

Log progress to a checkpoint file (e.g. `mixNN_progress.md`) after each render so an interrupted run can resume.

### 6. Eval score
The scorer compares the mix against the pro-DJ profile `eval/pro_profile.json`.
```
python3 src/eval/analyze_pro_set.py <mix.wav> --anchors <tracklist secs,...> [--name NAME]   # -> eval/sets/NAME.json  (run from /workspace/mixes)
python3 src/eval/score_mix.py eval/sets/NAME.json                                           # -> eval/scores/NAME.json
```
The score is advisory: it is not yet calibrated to the listener (eval/README.md). Guardrails gate the release; the score doesn't.

### 7. Share copy and tracklist
- Write `dj-mix-NN-tracklist.md` with mm:ss artist/title from `NAME_meta.json` deck `start_bar` × `bar_sec`.
- Make a smaller share MP3, e.g. `ffmpeg -i dj-mix-NN.mp3 -b:a 192k dj-mix-NN-share.mp3`.
- Optional: an analysis JSON for downstream use (`analyze_360.py` is the template; it reads `master.wav` and `mix360_meta.json`).

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

