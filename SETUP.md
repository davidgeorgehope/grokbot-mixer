# SETUP

## Machine
- Linux x86_64. Developed on Debian with Python 3.13.5, 8 cores and 15 GB RAM, of which only about 3 GB was sometimes free.
- **No GPU needed for audio.** demucs runs on the CPU (it's slow, a few minutes per track; `-j 8`).
- Visuals use moderngl with the **EGL** headless backend. A GPU helps, but Mesa software EGL (llvmpipe) works and reaches about 20 fps at 1080p.
- A separate **residential machine** (e.g. a home Mac) runs yt-dlp with browser cookies, because YouTube blocks datacenter IPs.

## System packages
```
sudo apt-get install -y ffmpeg rubberband-cli libsndfile1 libegl1 libgl1-mesa-dri rsync python3-venv
```
- ffmpeg: decode, master, ebur128 loudness, MP3/MP4 encode.
- rubberband: time-stretch in `prep.py`, called as `rubberband -3 -F -T ratio -q`.

## Python (audio and tests), derived from the imports
```
pip install numpy scipy librosa soundfile pyloudnorm essentia demucs pytest matplotlib
```
- `essentia` does key detection in `keys.py` / `add*.sh`.
- `demucs` (htdemucs) pulls in torch on the CPU.
- `matplotlib` is only needed for `guardrails.py --png`.

## Visuals venv (`visuals/venv`)
```
python3 -m venv visuals/venv && visuals/venv/bin/pip install numpy scipy moderngl glcontext pillow soundfile
```
`analyze_mix.py` uses numpy and scipy plus ffmpeg on PATH. `render_visuals2.py` uses moderngl and Pillow and pipes frames into ffmpeg.

## Memory notes (60-minute mixes)
- `engine.py` loads stems lazily (`LazySt`) and `mix3.py` frees each track's stems after its last deck. Loading all ~20 tracks' stems up front ran out of memory.
- `src/tests/checks.py` and `guardrails.py` compute onsets in chunks and read audio blockwise. A full-length STFT of 64 minutes needed about 11 GB.
- `visuals/code/analyze_mix.py` uses a chunked STFT (`CH` env, default 40000 frames).
- Run one 1-hour `analyze_pro_set.py` at a time (three in parallel ran out of memory), with `OMP_NUM_THREADS=3`.

## Paths and configuration
Scripts hardcode `/workspace/mixes` (repo root) and `/workspace/mixes/src2` (working dir). Place the repo there, or
`grep -rl /workspace/mixes src src2 eval visuals/code | xargs sed -i "s#/workspace/mixes#$MIXER_ROOT#g"`.

Copy `config.example.env` to `config.env`, fill it in, and `source config.env` before running anything.

### Generic vs owner-specific parts
| Part | Owner-specific bit | Where to change |
|---|---|---|
| Delivery | iCloud Drive "DJ Mixes" on a Mac reached by `ssh $HOST` | `HOST`, `ICLOUD_DEST` and `TAG_ARTIST` env, `src/sync_set.sh` |
| Secrets | A password manager. `yt_upload.py` calls the 1Password CLI `op item get <item> --vault <vault>` | `src/yt_upload.py`: the vault and item titles in `op()`/`access_token()`. It reads `OP_VAULT`, `OP_YT_CLIENT_ITEM` and `OP_YT_REFRESH_ITEM` from the config |
| YouTube | The OAuth client and refresh token for your channel (scope `youtube.upload`) | as above |
| Fetch host | ssh alias of the residential machine; yt-dlp path `~/.ytdlp-nightly/bin` | `HOST` env, `src/sync_set.sh` |
| Taste | `eval/example_ratings.jsonl`, `src/tests/fixtures/*rated*.json`, `test_guardrails.py` time windows | replace with your listener's ratings (docs/TASTE.md) |
| Tags | `TAG_ARTIST` env | `src/sync_icloud.sh` |

Never commit secrets. Credentials are read at runtime from the password manager.
