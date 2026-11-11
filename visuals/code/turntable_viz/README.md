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
- `build_segs.py` — meta.json → per-transition timing segments (physical deck order, deck-rule gate)
- `deck_state.py` — two-deck state machine, FX windows, plan walker
- `preview_window.sh` — short CPU preview of a mix time window
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
| `DIVE_GAP_SEC` | `600` | min gap between dives across the whole mix (full-mix mode plans dives once, globally) |
| `DECK_CHECK` | `1` | per-segment visibility gate (`render.mjs --check`) before rendering |
| `FX_RECORD_SWAP` | `1` | record fly-off / spin-in at deck swaps |
| `FX_LIGHTS` | `1` | beat-synced light rig + ambient glow |
| `FORCE_DIVE` | `0` | plant a mid-clip dive if prep finds none |
| `KEEP_WORK` | `0` | keep checkpoints after success |
| `CLOUD` / `GPU_TYPE` | empty = walk candidates | pin one cloud or GPU to skip the walk |
| `MAX_RUNTIME_SEC` | `10800` | hard pod kill cap (~3 h) |

## Decks (state machine)

`deck_state.py`: track 0 on deck A; every incoming track loads on the idle deck, so track k is on deck k % 2 and the
playing record never moves. Segment timings list decks in physical order (`decks[0]` = A) plus `out_deck`;
`prep.py` flips the crossfader to match and the HUD/labels follow the physical deck. `build_segs.py` fails if
`walk_segments` finds a record on two decks (Mix 08 v2 bug: outgoing was always drawn on A, so the new track jumped
B -> A at each segment cut). Test: `src/tests/test_turntable_decks.py`.

## Optional FX (default off until the listener approves)

| env | effect |
|-----|--------|
| `FX_RECORD_SWAP=1` | stopped record lifts and flies off its deck over the 2 bars before the cut; the next record spins in and flips onto that deck over 3 bars after it (never while a record plays) |
| `FX_LIGHTS=1` | six truss beams that sweep per bar and flash on the beat (mix low-band level), plus deck-coloured ambient glow by channel level; colours swap every 16 bars |

CPU preview of a window: `META=... MIX=... TRACKLIST=... FROM=780 TO=822 OUT=x.mp4 FX_RECORD_SWAP=1 FX_LIGHTS=1 preview_window.sh`.

## Groove dives and the visibility check

- One camera for every pass. The table/mixer pass and both deck passes share one depth buffer, so they must
  use the same projection, near plane included (`camFor` sets `near`; vendored `camera()` honours `st.near`).
  Mix 08 drew the dived deck with a smaller near plane than the table, so its depth landed behind the table and
  the whole deck vanished for every dive.
- A dive flies the camera onto the focused deck's real stylus position (booth world), lands on the drop
  (2 bars in), rides the needle 4 bars, and pulls back over 2 bars. Full-mix renders plan dives once across the
  whole mix (`prep.py --plan-dives`), drops only, at least `DIVE_GAP_SEC` apart (about 6 per hour).
- `node render.mjs --data seg/data.json --check 12 --backend cpu` samples frames across each dive plus booth
  frames, renders each with and without each deck, and fails if a deck that is in frame is not drawn, if the
  booth shot does not show both full decks, or if the stylus is off-centre at the dive peak.

## Notes

- Bootstrap writes NVIDIA EGL/Vulkan ICD JSON under `/tmp` and exports
  `__EGL_VENDOR_LIBRARY_DIRS` / `VK_ICD_FILENAMES` (system ICD dirs are often read-only).
- Pod env sets `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display,video`.
- MID knobs stay at noon (no mid lane in the engine). Channel meters are estimates.
