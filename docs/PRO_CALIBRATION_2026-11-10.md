# Pro calibration 2026-11-10 (America/New_York)

33 admitted pro transitions from `protrans/results/admitted.json`, measured by `src/calib/guard_vs_pro.py`. Results: `src/calib/guard_vs_pro_results.json` (private commit c8e9748). Generated 2026-11-10 17:28 America/New_York. This pass applied only the three gates below, at the admitted-set p95, the same standard as the 2026-11-07 energy-drop calibration (`docs/PRO_CALIBRATION_2026-11-07.md`).

the listener heard the three flagged Mix 08 r11c blends (full-handover clips) and said they were fine (2026-11-10 17:52 America/New_York), then approved calibrating these three guardrails to pro p95. Nothing else was changed: `DROP_FRAC`, the structure test, beat-alignment tolerance (`N1_ms=10`, `TOL_DRIFT_MS=10`), `DROP_DB`, and every other threshold stay as they were.

## Bass gap (`src2/bassgap.py` `GAP_DB`)

Low-end (<150 Hz) hole vs the neighbour-median of ±4 bars, failing a 2+ bar run deeper than `GAP_DB` unless both sources dip there.

| threshold | admitted pro blends passing |
|---|---|
| 8.0 dB (old) | 31/33 (93.9%; 6.1% fail) |
| 9.84 dB (p95, new) | ~95% by construction |

Admitted distribution of worst adjacent-pair depth (n=33): median 2.68, p90 6.706, p95 9.839, max 14.251 dB.

Mix 08 r11c flag: Hybrid Minds ft. Catching Cairo – Supernova → Hybrid Minds ft. Alexa Harley – Solitude, 8.515 dB (admitted percentile 93.9). Passes at 9.84 dB.

`GAP_DB` set to **9.84** (rounded from p95 9.839).

## Swap dip (`src/build_qa/test_release_eq_swap.py` `DIP_DB`)

`test_no_level_dip_at_swap`: lo−ref of half-bar full-band dB, ±1 bar around the bass (and high, when present) swap vs the quieter of the two bars before and after. Fail if lo−ref < −`DIP_DB`.

| threshold | admitted pro blends passing (30 measured; 3 unmeasured, not counted as fails) |
|---|---|
| 3.0 dB (old) | 25/30 (83.3%; 16.7% fail) |
| 4.41 dB (p95, new) | ~95% by construction |

Admitted distribution of dip depth (n=30): median 0.288, p90 3.402, p95 4.414, max 7.263 dB.

Mix 08 r11c flag: Sub Focus & Metrik – Trip → Dimension ft. TS Graye – Remedy, official pre-master deck-sum dip −3.548 dB (admitted percentile 90.0). The same formula on the mastered wav is only about −2.6 dB and already passed the old gate; the test measures the pre-master sum. Passes at 4.41 dB.

`DIP_DB` set to **4.41** (rounded from p95 4.414).

## N1 master level step (`src/guardrails.py` `TH['N1_db']`)

Level-step branch only: ffmpeg ebur128 momentary, median of 8 frames before vs 8 frames after (skip 2) at incoming start and bass swap. Fail if |post−pre| > `N1_db`.

The 10 ms grid branch (`TH['N1_ms']=10`, incoming first beats off the master grid) is **unchanged**. Pros were not used to widen the millisecond gate.

| threshold | admitted pro blends passing |
|---|---|
| 3.0 dB (old) | 27/33 (81.8%; 18.2% fail) |
| 3.83 dB (p95, new) | ~95% by construction |

Admitted distribution of max |step| (n=33): median 0.75, p90 3.1, p95 3.83, max 6.05 dB.

Mix 08 r11c flag: Son & Lauren Walton – Always Be → Wilkinson – Hypnotic, +3.2 dB at entry (admitted percentile 90.9). Passes at 3.83 dB.

`N1_db` set to **3.83**. `N1_ms` stays **10**.

## What was not changed

- `DROP_FRAC` and the structure test
- Beat-alignment / phase tolerance (`N1_ms`, `TOL_DRIFT_MS`)
- `DROP_DB` (already at pro p95 from 2026-11-07)
- `J1_db`, `E1_db`, `L1_db`, `DOUBLE_DB`, and every other guardrail or pytest threshold

Did not write `protrans/rules.json`.
