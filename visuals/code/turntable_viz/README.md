# turntable_viz — twin virtual turntables (default mix visual)

Two square decks with a 3D mixer between them (v2 booth layout, front camera ~40°),
rendered offline in headless Chrome (WebGL2) and muxed with ffmpeg. Deck/record/tonearm
renderer is vendored from rauchg/vinyl (MIT, see `vendor/LICENSE`); patches are marked
at the top of each vendored file.

This is the **default** YouTube visual for every mix. Occasional groove-dive camera
swoops (needle close-ups on drops/breakdowns) are on by default (`GROOVE_DIVE=1`).

## Measured speed (2026-11-09)

| where | clip | wall | speed | est 60 min |
|-------|------|------|-------|------------|
| box CPU (SwiftShader, 3 workers) | 55.2 s | ~1187 s | 0.046× | ~21.5 h |
| Runpod Secure RTX 4090 (`egl_angle`) | 55.2 s | 99 s render / 269 s incl. boot | 0.557× | ~1.8 h |

GPU WebGL probe picks the first hardware backend. On Runpod pytorch images that is
usually `egl_angle` (ANGLE → NVIDIA OpenGL ES); plain `--use-gl=egl` often fails.

## Pieces

- `prep.py` — engine timing + stems → per-frame state, groove maps, dive windows
- `scene.js` — booth layout, mixer, HUD, groove-dive camera
- `render.mjs` — puppeteer-core capture (`--backend auto|gpu|cpu`; gpu fails closed on SwiftShader)
- `probe_webgl.mjs` — try egl / egl_angle / vulkan / … and print the winner
- `render_preview.sh` — short single-clip helper (legacy)
- `render_full.sh` — **full-mix entry point**, restartable chunked parts
- `build_segs.py` — meta.json → per-transition timing segments
- `runpod_render.sh` / `remote_run.sh` / `bootstrap_runpod.sh` — rent GPU, render, pull, terminate
- `Dockerfile` — optional warm image (stock pytorch + bootstrap is the default path)

## Box (CPU) — short clip

```bash
TIMING=/workspace/mixes/deliver/visuals/beatgrid_preview.timing.json \
MIX=/workspace/mixes/deliver/07/dj-mix-07-128k.mp3 \
OUT=/workspace/mixes/deliver/visuals/turntable_preview.mp4 \
BACKEND=cpu GROOVE_DIVE=1 \
  /workspace/mixes/jobs/runjob.sh turntable-preview \
  bash /workspace/mixes/visuals/code/turntable_viz/render_full.sh
```

## Full mix on Runpod GPU (Saturday Mix NN)

Needs `RUNPOD_API_KEY` in the env, or `$HOME/.runpod_api_key` (mode 600). Walks
Community then Secure across 4090 / L4 / A5000 / 3090 / A4000 / L40S until one
deploys. Pod is always terminated (EXIT trap + 3 h cap).

```bash
META=/workspace/mixes/src2/mixNN_meta.json \
MIX=/workspace/mixes/deliver/NN/dj-mix-NN-128k.mp3 \
TRACKLIST=/workspace/mixes/deliver/NN/dj-mix-NN-tracklist.md \
OUT=/workspace/mixes/visuals/dj-mix-NN-visuals-1080p30.mp4 \
GROOVE_DIVE=1 \
  /workspace/mixes/jobs/runjob.sh turntable-mixNN \
  bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh
```

Single-clip GPU smoke (55 s preview):

```bash
TIMING=/workspace/mixes/deliver/visuals/beatgrid_preview.timing.json \
MIX=/workspace/mixes/deliver/07/dj-mix-07-128k.mp3 \
OUT=/workspace/mixes/deliver/visuals/turntable_preview_gpu.mp4 \
FORCE_DIVE=1 GROOVE_DIVE=1 \
  /workspace/mixes/jobs/runjob.sh turntable-gpu-smoke \
  bash /workspace/mixes/visuals/code/turntable_viz/runpod_render.sh
```

## Restart / flags

| env | default | meaning |
|-----|---------|---------|
| `WORK` | auto under `visuals/tt_work_*` | checkpoint dir (resume with same `WORK`) |
| `CHUNK_FRAMES` | 900 | frames per part (~30 s @30 fps) |
| `BACKEND` | `auto` | `gpu` on Runpod; `cpu` forces SwiftShader |
| `GROOVE_DIVE` | `1` | needle swoops on drops/breakdowns |
| `FORCE_DIVE` | `0` | plant a mid-clip dive if prep finds none |
| `KEEP_WORK` | `0` | keep checkpoints after success |
| `CLOUD` / `GPU_TYPE` | empty = walk candidates | pin one cloud or GPU to skip the walk |
| `MAX_RUNTIME_SEC` | `10800` | hard pod kill cap (~3 h) |

## Notes

- Bootstrap writes NVIDIA EGL/Vulkan ICD JSON under `/tmp` and exports
  `__EGL_VENDOR_LIBRARY_DIRS` / `VK_ICD_FILENAMES` (system ICD dirs are often read-only).
- Pod env sets `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display,video`.
- MID knobs stay at noon (no mid lane in the engine). Channel meters are estimates.
