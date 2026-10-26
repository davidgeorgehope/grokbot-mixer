# Guardrails (`src/guardrails.py`)

These are deterministic pass/fail checks on a rendered mix. You can't listen to the mix, so the checks measure it. Exit 0 means zero failures.
```
python3 src/guardrails.py --name NAME --mp3 OUT.mp3 --nudge nudge60d.json --png [--src /workspace/mixes/src2] [--out DIR] [--skip-decks]
```
- Inputs: `SRC/NAME_meta.json`, `SRC/NAME_raw.wav` and the mastered MP3.
- Outputs: `SRC/guard_NAME/guardrails.json` (failures with mm:ss), `transitions_rows.json` (per-bar A/B dB, flam and sub), and with `--png` a `trans_XX_MMSS.png` per transition. Each PNG shows the deck A, deck B and master waveforms on the beat grid, the M/S LUFS against the 30 s median minus 6, the sub below 120 Hz, and chroma, with failures shaded red.
- `src/tests/test_guardrails.py` requires `n_fail == 0`. It also re-checks that the guardrails still catch the three spots the listener rated bad in the v1 fixture (regression test).

| id | threshold (`TH`) | catches |
|---|---|---|
| E1 energy hole | 3 s loudness > 6 dB under the local 30 s median, unless intentional (own breakdown or declared `breakdowns`) | a fade almost to nothing between tracks |
| E2 near silence | 400 ms loudness < −35 LUFS (not in the first or last 5 s) | silence gaps |
| N1 entry shock | incoming first beats > 10 ms off the grid, or a master level step > 3 dB at entry or bass swap | weird entries, stem-switch jumps |
| F1 flam | per overlap bar, the decks' 16th-grid phases differ by > 15 ms | trainwrecked, flamming beats |
| G1 grid | master phase jump > 8 ms between 2-bar windows, or > 15 ms off the global grid | drift, off-grid source sections |
| K1 key clash | Camelot distance > 2 with more than 2 harmonic overlap bars | dissonant blends |
| L1 low end | summed sub > louder deck + 3 dB, or both decks carrying full bass | muddy double bass |
| V1 vocal clash | two decks singing in the same bar (demucs stems) | two lead vocals |
| P1 peak/DC | true peak > −1 dBTP, or DC > 0.005 | clipping |
| D1 dropped drop | a drop without a riser/roll/HPF build in the previous 8 bars or a +3 dB ramp | "it just dropped" |
| X1 echo-out | any echo transition without `allow_echo` | stop-start |
| O1 overlap | fewer than 8 bars with both decks within 12 dB of the outgoing body | fake blends |
| C1 groove | onset density < 30% of the local median for > 1 bar across a transition | the groove collapsing |
| C2 outgoing | outgoing deck > 10 dB under its body in the first half of the overlap | the outgoing track dying early |
| S1 dead tail | a deck playing its own near-silent tail (> 20 dB under its body), or a loop popping back in after it | fade out, then pop back in |

## Real incidents (mix 03-60 v1; fixture `src/tests/fixtures/guardrails_dj-mix-03-60_v1_rated.json`)
The v1 render had 62 failures (S1 14, F1 15, O1 11, E2 8, X1 5, E1 4, D1 2, N1 2, C2 1). The older 13-test QA suite had passed it.
- **~13:30, Deeper → Just Hold On ("horrible")**: S1 at 14:08. The outgoing track played its own fade-out tail, then a loop extension popped back in at 14:09.
- **32:40, Surrender → Come Together ("stop-start, not mixing")**: S1, E1 (−28 LUFS, 18.7 dB under the median), X1 echo-out and O1 (0 bars of overlap), all at 32:15–32:20.
- **~37, In The Shadows → Saviour ("almost ended to silence, then Saviour came in super weird")**: an echo-out with a faded tail. The fixed engine flags S1 around 39:11 in the reordered set.

Fixes that followed:
- Echo-outs are banned (X1).
- `extend_out` trims a record's tail before loop-extending (S1).
- The outgoing track holds its mids and highs for 8 bars (O1).
- Near-silent outgoing bars are phrase-looped (C2).
- The drum bridge no longer jumps stems (N1).

## The vocal-mute `np.interp` bug (fixed in mix3 v3)
Per-bar vocal muting used to set only the points *inside* the muted bars. `Deck.curve` uses `np.interp`, which clamps beyond the first and last points, so the outgoing deck's vocal gain stayed at 0, or ramped down, for its whole run before the window. Its vocals vanished for minutes (mixes 02 and 02b). The fix writes an explicit hold-at-1 point just before and after each muted run (`apply()` in `blend`). Lesson: every automation lane needs explicit endpoints.

## Auto-fix
`src/autofix.py NAME NUDGE_JSON` re-renders each deck in the flagged F1/N1 transitions on its own and measures each bar's 16th-grid phase. Bars more than 5 ms off get a nudge in ms (median over plays, applied once; looped bars used to be nudged cumulatively). `src/iterate.sh` loops render → guardrails → autofix.
