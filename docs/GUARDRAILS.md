# Guardrails (`src/guardrails.py`)

These are deterministic pass/fail checks on a rendered mix. You can't listen to the mix, so the checks measure it. Exit 0 means zero failures.
```
python3 src/guardrails.py --name NAME --mp3 OUT.mp3 --nudge nudge60f.json --png [--src /workspace/mixes/src2] [--out DIR] [--skip-decks]
```
- Inputs: `SRC/NAME_meta.json`, `SRC/NAME_raw.wav` and the mastered MP3.
- Outputs: `SRC/guard_NAME/guardrails.json` (failures with mm:ss), `transitions_rows.json` (per-bar A/B dB, flam and sub), and with `--png` a `trans_XX_MMSS.png` per transition. Each PNG shows the deck A, deck B and master waveforms on the beat grid, the M/S LUFS against the 30 s median minus 6, the sub below 120 Hz, and chroma, with failures shaded red.
- `src/tests/test_guardrails.py` requires `n_fail == 0`. It also re-checks that the guardrails still catch the three spots the listener rated bad in the v1 fixture.

| id | threshold (`TH`) | catches |
|---|---|---|
| E1 energy hole | 3 s loudness > 6 dB under the local 30 s median, unless intentional (own breakdown or declared `breakdowns`) | a fade almost to nothing between tracks |
| E2 near silence | 400 ms loudness < −35 LUFS (not in the first or last 5 s) | silence gaps |
| N1 entry shock | incoming first beats > 10 ms off the grid, or a master level step > 3 dB at entry | weird entries, stem-switch jumps |
| F1 flam | per overlap bar, the decks' 16th-grid phases differ by > 15 ms | trainwrecked, flamming beats |
| G1 grid | master phase jump > 8 ms between 2-bar windows, or > 15 ms off the global grid | drift, off-grid source sections |
| K1 key clash | Camelot distance > 2 with more than 2 harmonic overlap bars | dissonant blends |
| L1 low end | summed sub > louder deck + 3 dB, or both decks carrying full bass | muddy double bass |
| V1 vocal clash | two decks singing in the same bar (cached per-bar vocal features) | two lead vocals |
| P1 peak/DC | true peak > −1 dBTP, or DC > 0.005 | clipping |
| X1 crossfader | each blend has one logged monotonic x(t) 0→1; deck gains come only from it (≤3 dB/beat); no other automation | ducking, mutes, echo-outs, fader stabs |
| E3 blend sag | > 25% of the blend's first half has both decks' mids > 8 dB under the outgoing body | melody lost mid-blend |
| O1 overlap | fewer than 8 bars with both decks within 12 dB of the outgoing body | fake blends |
| C1 groove | onset density < 30% of the local median for > 1 bar across a transition | the groove collapsing |
| C2 outgoing | outgoing deck > 10 dB under its body in the first half of the overlap | the outgoing track dying early |
| S1 dead tail | a deck playing its own near-silent tail (> 20 dB under its body), or a loop popping back in after it | fade out, then pop back in |
| R1 rhythm clash | median bar onset-envelope xcorr between decks over the overlap < 0.20 (max lag ±1/8 beat) | drums fighting / wrong-tempo "car crash" |
| T1 source tempo | raw wav UK-breaks pulse (120–130 BPM autocorr ≥ 0.50) stronger than DnB (165–180) with DnB height < 0.45 | non-DnB track forced onto a 174 grid (pbpm.py only searched 170–177) |
| J1 level jump | adjacent-bar RMS jump > 6.5 dB at phrase-loop seams | loop-seam level chops |

## History
The v1–v3 incidents (echo-outs, dead tails, vocal-mute stabs, drum-only bridges, map cuts) all came from automation that the crossfader engine no longer has. See docs/LESSONS.md and the git history for those checks (D1/Q1/H1/M1), which were removed with the old engine.

## Auto-fix
`src/autofix.py NAME NUDGE_JSON` re-renders each deck in the flagged F1/N1 transitions on its own and measures each bar's 16th-grid phase. Bars more than 5 ms off get a nudge in ms, written to the nudge JSON. Then re-run `src/render_and_test.sh`.
