# Mix 07 Weekly Visuals Experiment — Build Brief

**Idea:** Camelot Chladni Plate (cymatic sand)  
**Date:** 2026-11-07  
**Status:** design locked; await `deliver/07` audio  
**Fallback if break:** `src2/staff_viz.py --v1plus` (Mix 06 baseline)

---

## 1. What it looks like

Top-down view of a dark vibrating plate dusted with luminous sand. Grains slide toward nodal lines of a Chladni standing-wave field

```
F(x,y) = cos(nπx)·cos(mπy) − cos(mπx)·cos(nπy)
```

(optionally blended with a second finer mode). Figures redraw as the bass/mid/high balance shifts. Kicks toss sand outward; it resettles. Outgoing deck grains tinted with its Camelot hue; incoming with its own — during a blend the two colours/modes crossfade with the analysis `mixAB` / track overlap. Soft title cards (artist · title · key) fade in on track enter, same spirit as Mix 01–05 / staff_viz v1plus cards. No sheet-music lanes, no spectrogram scroll, no 3D flyover camera.

---

## 2. Why this week (not a repeat)

| Prior | Why different |
|---|---|
| Mix 01–05 `liquid2.frag` orbs + backdrop tex | No temporal dye memory; metaballs, not sand-on-nodes |
| Mix 06 `staff_viz --v1plus` | Notation lanes; this is abstract physics |
| 3D flyover | Rejected as less clear; this is flat top-down |
| 2026-11-04 spectrogram candidate | Frequency paint, not nodal sand |

 inspirations (pages actually opened — see IDEAS.md): Deus Cymatic Plate, Luxaudica Ink Bloom, BeamTracer Fluid+Particles, Figura sand/Lissajous (X), Hydra FFT docs, AUTOVJCLUB reactive guide, Nodal Chladni sand table.

---

## 3. Files to create / touch

```
visuals/code/chladni_plate.frag      # NEW — accumulate + tonemap; uniforms below
visuals/code/render_chladni.py       # NEW — fork of render_visuals2.py (moderngl EGL → ffmpeg)
visuals/code/analyze_mix.py          # REUSE as-is (bass/mid/high/kick/snare/rms)
visuals/code/d07_tracks.json         # NEW — from deliver/07 tracklist (starts, overlap)
visuals/code/d07_analysis.json       # NEW — analyze_mix.py output
src2/staff_viz.py key_hue/track_info # REUSE (import or copy 10 lines) for Camelot → HSV
viz07/                               # NEW work dir (segs OR single-pass out)
deliver/07/yt_desc.txt               # description for upload
```

Do **not** modify `liquid2.frag` / Mix 06 staff path except as fallback. Do **not** touch the audio build under `/workspace/mixes`.

---

## 4. Libraries (already in `visuals/venv`)

- `moderngl` 5.13 + `glcontext` (EGL headless)  
- `numpy`, `scipy`, `pillow`, `soundfile`  
- System: `ffmpeg`, `librosa` (system / src2 env for optional stem-lane preview)

Activate: `source /workspace/mixes/visuals/venv/bin/activate`

---

## 5. Audio → visual mapping

| Signal (from analysis JSON) | Visual |
|---|---|
| `bass` | low mode indices `(n0,m0)` — coarse figure |
| `mid` | shifts `m0`; blends second mode weight |
| `high` | high mode `(n1,m1)` + fine grain sparkle |
| `kick` | impulsive outward velocity (toss) |
| `snare` | brief plate flash / contrast punch |
| `rms` | slide speed + glow brightness |
| `beat` / BPM grid | optional subtle LFO breathing (AUTOVJCLUB advice) |
| track Camelot `[nA/B]` | sand cold/hot colour via `key_hue` |
| overlap / mixAB | crossfade mode A↔B + colour A↔B |

Optional upgrade (if timing.json exists for a blend): boost toss amplitude from stem drum onsets; bias low-mode strength from stem bass lane (`staff_viz.timing_lanes`). Nice-to-have, not required for v1.

---

## 6. Shader / sim approach (concrete)

**Preferred (GPU, matches Mix 01–05 perf):**

1. Ping-pong FBO pair at internal res (e.g. 960×540 or 1280×720).  
2. Each frame: advect a density field with curl/noise + force `−∇|F|` toward nodes; inject dye blobs on kick at random plate positions tinted by current Camelot RGB; decay dye slowly.  
3. Tonemap pass: density → glowing sand colour, vignette, grain noise, title-card overlay (same card tex path as `render_visuals2.py`).  
4. Uniforms: `time, flow, bass, mid, high, kick, snare, rms, beat, mixAB, n0,m0,n1,m1, colA.rgb, colB.rgb, cardA, cardT, res`.

**CPU fallback (if EGL particle compute is finicky):**  
`N≈80k` grains as `float32` xy/vx/vy updated in numpy each frame (Nodal-style `−F·∇F`), splat into a PIL/numpy framebuffer, upload as texture. Slower (~3–6 fps) but correct; use only for 30s preview if GPU path stalls.

Mode index mapping (start point, tune on preview):

```python
n0 = 1 + int(np.clip(bass * 5, 0, 5))       # 1..6
m0 = 2 + int(np.clip(mid  * 4, 0, 4))       # 2..6, ensure n0 != m0
n1 = 4 + int(np.clip(high * 4, 0, 4))
m1 = n1 + 1 + int(np.clip(mid * 2, 0, 2))
w_hi = float(np.clip(0.15 + 0.7 * high, 0, 0.85))
```

---

## 7. Preview (do this first once Mix 07 audio exists)

1. Build `d07_tracks.json` from `deliver/07/*tracklist.md` (starts + overlap ≈ 32 bars @ 174 BPM ≈ 44 s, match meta).  
2. `analyze_mix.py deliver/07/dj-mix-07-128k.mp3 d07_tracks.json d07_analysis.json --fps 30 --bpm 174`  
3. Pick a strong blend (big bass handoff / rated daily-style pair if known) → `--start S --dur 30`.  
4. Render 1080p30 preview → `visuals/mix07_proto/preview30.mp4`.  
5. Sync check: play preview; kicks should toss in time (±40 ms). If late, re-run analyze with `--lag 0.03` (or measure like `staff_viz.measure_sync` against kick peaks).  
6. Eye check: Camelot colour shift visible across the blend; figure coarsens on bass, fines on highs.

---

## 8. Full-mix render strategy

**Path A (recommended, mirrors Mix 01–05):** single-pass `render_chladni.py d07_analysis.json AUDIO OUT.mp4 --w 1920 --h 1080` overnight / background. Resume-safe: write frame index checkpoint every 5 min.

**Path B (if single-pass OOMs or needs parallel):** viz06v3-style — cut mix into ~N track-centred segments with `full_viz.py`-like cuts, render 4-wide with `xargs -P4`, concat video + full 128k audio (see `viz06v3/run.sh`).

Target: `viz07/dj-mix-07-chladni-1080p30.mp4` (or 720p if box CPU is hot — the listener accepted 720p for Mix 06 staff).

---

## 9. Sync check (gate before upload)

- Kick tosses align with audible kicks on 3 sampled minutes (intro, mid blend, late drop).  
- `ffprobe` duration of video == audio (±0.1 s); A/V both present.  
- Title cards appear near track starts (half-overlap rule from `render_visuals2.py`).  
- If sync fails or render crashes → **fall back immediately** to `staff_viz.py --v1plus` segment pipeline (`full_viz.py` + viz06v3 pattern). Do not ship broken experiment.

---

## 10. YouTube upload

```bash
cd /workspace/mixes
source ... # if needed
python3 src/yt_upload.py viz07/dj-mix-07-chladni-1080p30.mp4 \
  --title 'DJ Grok Bot – Mix 07 | Liquid Drum & Bass' \
  --description "$(cat deliver/07/yt_desc.txt)" \
  --privacy public \
  --tags 'drum and bass,liquid dnb,dj mix,grok bot'
```

Write `visuals/up07.link` with the youtu.be URL. Then Drive/iCloud backup per existing deliver flow; delete local mp4/tex scratch (the listener cleanup rule).

---

## 11. Acceptance / ship criteria

- Experiment actually runs end-to-end (not just a still).  
- Visually distinct from Mix 06 staff and Mix 01–05 liquid on a 10-second glance.  
- Public YouTube live before / around the usual morning window if audio is ready.  
- IDEAS.md already logged (2026-11-07 entry).  
- On any hard failure → staff_viz v1plus, still titled the same, note fallback in DOCKET/PROGRESS.

---

## 12. Proto already on disk

`visuals/mix07_proto/` contains a still-frame Chladni field with dual Camelot tints (8A + 9A) generated without Mix 07 audio — look proof only. Full motion preview waits for deliver/07.
