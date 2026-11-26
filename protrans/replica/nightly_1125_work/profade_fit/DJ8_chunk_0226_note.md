# DJ-8 chunk 2026-11-26 ~02:11-02:45 ET

## r5 read (dev 27, no early exit in these renders)
| arm | mae_bass | mae_all | l1 | l1a | pump | hole | beat | van | hf |
|---|---|---|---|---|---|---|---|---|---|
| r4_base | 10.39 | 2.96 | 1 | 0 | 4 | 1 | 0 | 0 | 5 |
| r4_fit2 | 9.47 | 2.95 | 3 | 0 | 3 | 1 | 0 | 0 | 4 |
| r5_rel4 | 9.65 | 2.95 | 3 | 0 | 3 | 1 | 0 | 0 | 4 |
| r5_rel8_mid | 11.03 | 2.95 | 2 | 0 | 4 | 1 | 0 | 0 | 5 |
| r5_rel4_mid | 10.99 | 2.95 | 1 | 0 | 4 | 1 | 0 | 0 | 5 |
| r5_b30 | 10.16 | 2.95 | 1 | 0 | 4 | 1 | 0 | 0 | 5 |
| r5_ex35 | 9.31 | 2.70 | 4 | 0 | 3 | 1 | 0 | 0 | 4 |
Pick: r5_ex35 (best pro-match in every band, same hard fails/pumps as fit2; its extra L1 kushsessions__04 is inaudible, l1a 0).
The _mid arms and b30 bring back alpha_rhythm__11 pumping (7.6 / 4.8 dB > p95 4.54).

## pola02 (ee_r7 + pro fade) root cause found
- Pre-fix, both ex35 and fit2 failed incoming_vanish 6.9 dB (p95 5.24). No A/B written.
- Cause: mix_simple runs tail_exit (ee_r7 exit_bar 128) BEFORE pro_fade.apply, which rebuilt the fader over
  [start, end_bar=144]: A kept playing on the -10 dB shelf to bar 143 (undoing the early exit), and B's lower
  entry (-8.5) buried its quiet intro bars 117-119 under A (B-A -19 dB) -> appear/vanish/return.
- Fix: src2/pro_fade.py respects t['tail_exit']['exit_bar'] (PRO_FADE_RESPECT_EXIT, default 1; 0 = old).
  Test: src/tests/test_pro_fade.py::test_pro_fade_respects_upstream_tail_exit (11 pass).
- The dev27 grid did NOT run with early exit, so r4/r5 never exercised this path.

## Post-fix pola02 (ex35 + PRO_FADE_RESPECT_EXIT) - PASSES, blind A/B written
- profade: vanish 0.0, pump 4.1 (p95 4.54), lows_dip 22.9 (p95 45.34), beat ok (lag null, halfbeat ok), hole no, L1 1.0, l1a 0.0; v1 27.47 v2 31.31
- ee_r7 control (fresh render, not byte-identical to the r7 clip he heard): vanish 0, pump 3.9, lows_dip 25.1, L1 1.73, l1a 0; v1 27.27 v2 30.93
- Clips: nightly_1125_work/pola02_ab_profade/{A,B}.mp3 (2.65 MB each), A_diag.png, B_diag.png, fade_curves_vs_pro.png, placement_pro_vs_ours.png
- Key ONLY in /workspace/private/pola02_ab_profade_key.json (+ metas/diag json there).

## Next
1. Send the A/B to the listener (blind).
2. Re-run the dev27 grid with EARLY_EXIT + TAIL_EXIT on (so pro fade is tested on top of the early exit, the path we ship), via jobs/runjob.sh.
3. Pinned 33 for ee_r7+ex35(+respect-exit); n1127 shadow-arm spec; review L1 vs audible gating against pro p95 (still inaudible-only fires).
