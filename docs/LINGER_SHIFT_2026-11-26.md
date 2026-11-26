# LINGER_SHIFT (2026-11-26)

Flag, off by default. Enable with `LINGER_SHIFT=1`. If a run has turned it on, `LINGER_SHIFT_OFF=1` forces it off. Ridegate stays the engine default; this flag does not change that.

When predicted drum linger or structural linger exceeds the pro p95 (8.80 / 5.4), the live path searches earlier legal natural windows on the 8-bar grid so the fade starts while the outgoing is still in its drop, and/or the incoming cue sits before the incoming breakdown. Incoming cues that start mid-drop are skipped (they pumped on __11). Lock and pump previews still apply. No pair pins.

## Fresh check (4 linger pairs + controls __00 / __06)

Predicted drum_linger: __03 12→3, __22 11→3, __30 12→0. Structural linger __11 16→0. Controls unchanged. Official hard fails: 0→0 (cue 24 on __11 pumped 4.9 and was rejected; cue 16 passed). fade_err (fader MAE vs the corpus curve) unchanged on __03/__22/__30; __11 10.06→8.91. No official v1/v2 (these pairs have no pro clip). Exit lag vs the corpus cue moved the wrong way on the shifted exits (__03 1.8→6.2, __22 1.0→7.0, __30 102.5→110.5). __11 cue lag 1.2→14.8. Pump on __30 3.7→4.2 (still under 4.54).

Rendered-deck drum linger (outgoing high >200 Hz within 8 dB of the drop baseline, actual xfader, not equal-power): already 0 on the old default for __03/__11/__30, and 1→0 on __22. The equal-power predictor overstated how long the xlong shelf kept drums up. First-half outgoing lows are louder under the fix (the blend now starts in the drop); last-half lows still hand off, no new hole.

The official 32-bar __30 clips do differ across the blend (100 ms hops, blend region mean 2.58 dB, max 9.66 dB, 81/220 hops over 3 dB). That is a real change, but not a clear win on official placement or on the rendered 8 dB linger, so the flag stays off.

A/B (old default vs flag, worst pair __30): `/workspace/mixes/docs/AB_linger_shift_2026-11-26_A.mp3`, `/workspace/mixes/docs/AB_linger_shift_2026-11-26_B.mp3`, diag `/workspace/mixes/docs/AB_linger_shift_2026-11-26_diag.png`. Answer key: `/workspace/private/AB_LINGER_SHIFT_2026-11-26.json`.
