# turntable_viz — twin virtual turntables (prototype)

Two decks seen at an angle with a mixer between them, rendered offline in headless Chrome (SwiftShader WebGL2)
and muxed with ffmpeg. Deck/record/tonearm renderer is vendored from rauchg/vinyl (MIT, see `vendor/LICENSE`,
upstream commit in `vendor/UPSTREAM_COMMIT.txt`); patches are marked at the top of each vendored file.

- `prep.py` — reads engine `timing.json` + `st/<id>.json` / `.sections.json` (helpers reused from `../beatgrid_viz.py`),
  "cuts" each track into a spiral (1 revolution = 1 bar, so the platter turns at the real tempo), samples the
  track's own audio energy along the groove (RGBA map: energy, bass, section, beat/phrase ticks), and writes
  per-frame deck/mixer state (track bar under the needle, gain/low/high lanes, crossfader, levels).
- `scene.js` — draws both decks into two viewports, sets platter angle + tonearm from the track bar, and draws
  the mixer/HUD in a 2D canvas.
- `render.mjs` — puppeteer-core frame capture (`--still F --png out.png` or `--from/--to --out part.mp4`).
- `render_preview.sh` — full job: prep, N parallel workers, concat, mux mix audio, still, scratch cleanup.

Run: `/workspace/mixes/jobs/runjob.sh turntable-preview bash visuals/code/turntable_viz/render_preview.sh`
Needs `npm i` here (puppeteer-core) and /usr/bin/google-chrome.
