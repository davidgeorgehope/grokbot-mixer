# RCA addendum: BASS_COVER on the 2026-11-14 daily window (Prime Expansion -> Demons)

This is the swap-cover prototype for the same 2026-11-14 daily pair. The main write-up is `docs/RCA_2026-11-14.md` (hint_family, off by default): that RCA found the engine never nominated the near-hint mid-track window, so we mixed Prime Expansion's late second drop over Demons' bass-less intro. It was already on disk when this addendum was finished, so this note does not replace it or change `rules.json`.

the listener's widget answer on 15 November 2026 was B as the pro and 3/5 for ours (below 4, so an RCA). The log row also has a later 2/5 with a comment. Pick: `hybrid_minds_ukf__19`, Urbandawn – Prime Expansion -> Hybrid Minds – Demons (ft. Charlotte Haining), Hybrid Minds UKF mix [Ea4ngKLPNMQ](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) around 34:44. Delivered score 27.68; current default with LONG_XP=0.45 is 28.01 (train 32.26, held-out 34.05). No rule was kept on 14 November (LONG_RISE was reverted for the X1 3 dB/beat guard).

Clips he heard: `deliver/protrans/daily_2026-11-14_A.mp3` (ours) and `_B.mp3` (pro), 44.1 s, -14 LUFS, tick at 0:22. Diagnostic from that day: `deliver/protrans/diagnostics/daily_2026-11-14.png`. This prototype's figure and clip: `deliver/protrans/diagnostics/rca_2026-11-14_bass_cover.png`, `deliver/protrans/rca_2026-11-14_bass_cover.mp3` (same window as the daily clips, tick at 0:22). The SNAP_IN / shallow-tail prototype from the 11-15 pick was not touched.

## What we measured on the window he heard

Window: `nat_short` `["n", 176, null, 32, 16]`. Prime Expansion bars 160–176 (outro starts 168, music end 185, lows still full at about −17 dB). Demons bars 32–48 (intro; drop1 is 48). Demons' lows in that overlap sit at −28 to −36 dB, median −13.9 dB under the track's own body (−18.9 dB); every bar is under body−6, and the drop jumps to −19.7 dB at bar 48, the first bar after the cut.

Designed handoff under FADE=long, LONG_SWAP=exit: bass swap [164, 169] (4-bar width plus a 1-bar outgoing lead, centre near the exit start). That is Demons source bars 36–41, still in the intro. Rendered summed lows fall from about −19 dB at bar 164 to −39 dB at 168 and stay in a hole until the drop at 176. Dip vs just before the blend: **22.5 dB**. The official bass-gap test (9.84 dB vs the median of ±4 neighbours, pro p95) does not fire: the hole is 8–10 bars wide, so every bar's neighbours are also in the hole.

`cap_solo_incoming` and `swap_before_thin` only compare the second half of the window to the first-half median, so a window that is thin all the way through is almost invisible to them (`first_incoming_thin_bar` is 9, and the handoff already ends there). `SWAP_THIN` would have kept the bass on the outgoing when the incoming has no low end, but `swap_at` returns `POS*X` immediately for FADE=long and never runs that path.

Other checks on the heard clips, not the cause of the 3/5:

- Beat: half-beat fail=false (fewer than 4 drum-on-drum bars). Pro lock 4.5 ms, scorer beat_off 8.7 ms. Kick-align lag 2.76 s with peak only 0.29 (weak; the daily clips were shifted by that lag).
- Loudness: both clips −14.2 LUFS, no clipping (ours peak 0.75).
- Keys: not stored in the library (`None->None` in the meta). A later KeyExtractor pass gives Prime Expansion 11A (F# minor) and Demons 12B (E major), a diagonal Camelot step, not a clash that would explain a 3/5.
- Vocals were not checked (no vocal maps); the vocal stem subscore stayed around 23.
- Tempo stretch is the usual 173 → 174 on Prime Expansion.

## Ranked causes of the 3/5

1. **Bass handoff in a bass-less intro (what this flag treats).** We swap lows eight bars before Demons' drop, while Prime Expansion still has full bass. That is the 22.5 dB hole in the clip, and it is the same "later bass handoff when the incoming has no bass" idea already on the research list. On this pair it is also a consequence of the window: STRUCT's 300-point bonus locks `nat_short` on outro-over-intro, so the overlap is Demons 32–48 by design. The deeper planner/shortlist cause, and the better pick-score move, is in the main RCA (`hint_family`).
2. **The fader still uncovers the last bars of the intro.** Even with the mid-window swap skipped, FADE=long's 8-bar exit starts at bar 168 and has Prime Expansion down 8–21 dB by 170–175, while Demons still has no bass. The leftover hole is the last four bars plus a hard cut at the drop. Filling that would mean delaying or extending the exit, which is SNAP_IN / shallow-tail work and was left alone. The gradual-tail rule (≤3 dB/bar above −24 dB) already needs about eight bars to leave, so a late short cut is not legal.
3. **Not a trainwreck, and not a threshold miss.** Phase, clipping, keys, and stretch are fine. The official bass-gap test is blind to a wide hole; nothing was loosened to make it pass.

## Fix (`BASS_COVER`, off by default)

`fade_long.incoming_no_bass`: true when every overlap bar of the incoming lows sits ≥ 6 dB under the track's own p75 body (the existing `thin()` / SWAP_THIN line, not a loosened guardrail). `mix_simple._ctx` then sets that blend's `swap_w=0` so lows stay on the outgoing and fade with the crossfader. No low-lane move means X1's 0.2–0.65 centre check does not run. A PIN `swap_bars` still wins. The crossfader is unchanged (not SNAP_IN / TAIL_SHALLOW). The lane builder follows each blend's own `swap_w` after `_ctx(None)` resets the global SW, so a zero-width ramp cannot be written. Tests: `src/tests/test_bass_cover.py`. `recreate.apply_rules` accepts `BASS_COVER` / `BASS_COVER_DB`; they are not in `rules.json`.

On this pair, body-6 holds for all 16 overlap bars. About 20 of the 33 admitted windows would also trip that test (typical STRUCT intro).

| | Default (28.01) | `BASS_COVER=1` (27.81) |
| --- | --- | --- |
| Window | PE 160–176 over Demons 32–48 | same |
| Bass swap | [164, 169] | none (lows stay on the outgoing) |
| Summed-lows dip | 22.5 dB, hole from ~166–175 | **18.3 dB**, mid-blend bass holds until the exit; leftover hole is 172–175, then the drop at 176 |
| bass_swap subscore | 0.85 / 1.79 | 0.83 (event detector still reads ours 18 vs pro 1; noisy, as documented) |
| blend_length subscore | 11.66 | 18.96 (near the pro's 18) |
| Half-beat / pro lock | fail=false, 4.5 ms | fail=false, 4.4 ms |

Clip: `deliver/protrans/rca_2026-11-14_bass_cover.mp3`, 44.1 s, −14 LUFS, short tick at **0:22**, same window he heard. The mid-window hole is gone. The last bars of the exit and the cut at the drop are not. The scorer on this pair moved 28.01 → 27.81 (a small loss). Dip improved 4.2 dB. This is a legal cover for a thin-intro overlap; it does not pick a better section.

## Cohort (like-for-like, flag on, defaults not changed)

Current default held-out is 34.05 (`d1115_xp_045`, train 32.26, n=33, 0 fails). Variant `rca14_bcover` = the same rules plus `BASS_COVER=1`. Job `rca14-bcover` finished 10:31 AM ET, n_fail=0.

| | train | held-out |
| --- | --- | --- |
| default (`d1115_xp_045`) | 32.26 | **34.05** |
| `BASS_COVER=1` | 33.18 (+0.92) | **32.51 (−1.54)** |

Like-for-like: 7 pairs up, 13 down, 13 flat. Train swings were large in both directions (joe_syntax_hospital__14 +11.35, hybrid_minds_ukf__40 +8.10, hybrid_minds_ukf__12 +6.74; hybrid_minds_ukf__25 −5.39). Held-out losses were led by maduk_liquicity_lunar2025__03 (−11.85), with smaller drops on Pola & Bryson and Netsky 06. Wilkinson was unchanged at 30.20. This pair: 28.01 → 27.81.

The flag stays off. The held-out drop is a reason to keep it opt-in and to treat it as cover for thin-intro windows, not a replacement for nominating the right section (`hint_family`). No threshold was loosened. X1 is unchanged.

## What was not done

- No default or `rules.json` change.
- No overwrite of `docs/RCA_2026-11-14.md` or `deliver/protrans/rca_2026-11-14_fix.mp3` (those are the hint_family RCA).
- No SNAP_IN, TAIL_EXIT, TAIL_SHALLOW, or LONG_RISE work.
- No per-track pin and no hand-calibrated threshold.
