# grokbot-mixer

DJ Grok Bot's liquid DnB mix pipeline (a snapshot of `/workspace/mixes`). It holds code, plans and test data only: no audio, video, stems or credentials.

One engine: `src2/mix_simple.py`, a two-deck **crossfader** mixer.
- Each blend is one monotonic equal-power crossfade x(t) 0→1 over a 16-bar phrase.
- Each track has a constant gain (normalised to -16 LUFS). There are no stems, EQ, ducking or FX in playback.
- Mix points are chosen from full-track analysis to be vocal-free and single-bassline. If a track has no clean window, a clean 16-bar phrase is looped, with 1-beat overlap-add seams.

## Layout
- `src2/`: engine (`engine.py`, `mix_simple.py`), track prep (`add_track.sh`, `pbpm.py`, `prep.py`, `fixgrid.py`, `barfeats.py`, `keys.py`, `phasechk.py`, `regrid.py`, `retempo.py`, `drift.py`), ordering (`order.py`), the plan `plan_60f.json` and warp nudges `nudge60f.json`
- `src/`: `render_and_test.sh` (the one entry point), `master.sh`, `guardrails.py`, `autofix.py`, `tests/`, `gen_tracklist.py`, `eval/` scorer, delivery (`sync_icloud.sh`, `sync_set.sh`, `yt_upload.py`)
- `eval/`: pro profile, ratings and scores
- `visuals/code/`: audio-reactive video
- `docs/`: GUARDRAILS, LESSONS, MIXING_RULES, TASTE

## Run (from the repo root)
    bash src/render_and_test.sh plan_60f.json mixS /workspace/mixes/dj-mix-03-60.mp3 9.0 nudge60f.json

Start with AGENTS.md. Credentials come from 1Password at runtime and are never stored here.
