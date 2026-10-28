# Lessons and troubleshooting

- **OOM on 60-minute mixes**:
  - Track audio loads lazily (`engine.LazySt`) and is freed after a track's last deck.
  - Tests and guardrails compute onsets in chunks and read audio blockwise.
  - Visuals use a chunked STFT.
  - Run one heavy analysis at a time.
  - If it still runs out of memory, check `free -g`; another job may be holding memory.
- **G1 grid fails in beatless breakdowns**: these are false positives. The phase estimator returns None with no drums there, and the stretched source grid is exactly uniform. Options:
  - Declare the record's own breakdown in the plan with `"breakdowns": [[from, to]]` (at most 4 bars).
  - Skip it with `which` (exit after an earlier drop).
  - Replace the downbeats with an exact grid using `regrid.py`.
- **Off-grid source sections** (live-played or swung parts): use warp nudges in `nudge*.json` (`{id: {src_bar: ms}}`), written by `autofix.py`. Add nudges only where needed. Nudges near transitions or drops have broken deck alignment, and `test_every_deck_on_its_planned_bar` catches that. Always pass the same `NUDGE=` to render, guardrails and tests; one run silently used the default file.
- **Fix estimators, not thresholds**: when a test disagrees with the deck-alone measurement (for example a drum-loop xcorr bias), fix the measurement and note why. Never loosen a threshold to get green.
- **Interruptions**: renders take minutes and can be killed. Append each step to `mixNN_progress.md` (plan, render log name, result) and resume from the last line.
- **Big file copies to the home machine**: scp of a 1.2 GB video failed twice on a flaky link. Copy to a temp name and `mv` into place (atomic, so iCloud never syncs a partial file), use rsync with `--partial` or a different route, and verify the byte size at the destination.
- **YouTube blocks datacenter IPs**: fetch on a residential machine with `--cookies-from-browser`. Use a nightly yt-dlp when extraction breaks.
- **No official upload**: drop the track rather than using a rip.
- **Drop at bar 0** (no runway): drop the track, or let the engine loop one of its clean phrases.
- **Visual sync**: run `analyze_mix.py --lag 0.055` to correct the STFT envelope lead.

## Just Hold On was 124 BPM UK-breaks, not DnB (mix 03-60 "car crash")
`pbpm.py` only searched 170–177, so Sub Focus & Wilkinson – Just Hold On (Beatport: Breaks, 124 BPM) got `orig_bpm=170.5` and a fake 174 grid. F1/G1 still passed (16th-fold phase finds energy on a 16th even when the pulse is wrong). Fix: R1 onset-xcorr across the overlap + T1 raw-wav tempo band check; drop/replace non-DnB tracks; widen pbpm's search and reject out-of-band pulses.

## 2026-10-28: Why there is only a crossfader now
Mixes 03 v1–v3 used stems, EQ swaps, vocal ducking, drum bridges and FX. the listener heard every one of those as chopping ("random cutting in/out", the whole track fading at 48:36). Each automation was a new source of artefacts and needed its own guardrail (Q1/M1/H1/D1). The fix that worked was subtraction:
- One equal-power crossfader per 16-bar phrase blend, and constant per-track gain.
- Avoid clashes by **choosing** mix points (vocal-free, one bassline) instead of repairing them with automation.
- Loop a clean phrase when a track has no clean outro. Seams use 1-beat linear overlap-add on bar boundaries.
- Demucs stays an offline analysis tool only (cached `bar.voc` / `bar.drums`), and the stems are deleted after prep.
