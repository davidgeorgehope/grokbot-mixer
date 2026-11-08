> Historical eight-bar audit; superseded by real_blend_recalibration_report.md.

# Real-blend admission audit — 2026-11-08 ET

## Rule and calibration

Each source-fitted full-band amplitude gain must be within 12 dB of its own 95th percentile for a total of at least eight simultaneous bars. Only actual simultaneous frames count. Longest continuous overlap is diagnostic, not the admission criterion: an initial continuous-run criterion overrejected blends with musical rests. No score weights or engine rules changed.

Calibration sweep (-9 / -12 / -15 dB): Hospital radio-DJ excerpt 2.356 / 2.356 / 3.081 overlap bars (all reject); genuine Hybrid Minds __08 23.923 / 33.528 / 40.778 bars (all pass). Synthetic source-fitted audio tests also distinguish a real overlap from fade-gap-drop.

**Limitation:** the full hospital_podcast393__04 pro.wav had already been cleaned. We measured only the retained 46.7 s blind-A pro excerpt using the original source-location anchors. Its fitted 2.356 bars are not a measurement of the entire original 64 s clip, and may include fitting leakage into speech. The full row remains excluded by talkover and fails closed on missing input. No missing-audio measurement is presented as zero.

## Admission

Current input was **31**, not 33: four talkover rejects and two permanent version skips had already reduced the original 37. This gate rejects **11 more**, leaving **20** (16 train / 4 held-out).

Reject means **less than eight adequately audible overlap bars**, not necessarily no mixing. In particular, previously favoured Netsky __15 has 3.262 such bars and is excluded by this policy. A genuine shorter blend can fail this minimum-length requirement; all data remain available for review.

| Clip | Total overlap bars | Longest run bars | Admission |
|---|---:|---:|---|
| hybrid_minds_ukf__00 | 21.386 | 6.887 | keep |
| hybrid_minds_ukf__08 | 33.528 | 17.580 | keep |
| hybrid_minds_ukf__09 | 13.411 | 11.780 | keep |
| hybrid_minds_ukf__10 | 11.961 | 6.343 | keep |
| hybrid_minds_ukf__11 | 9.424 | 3.443 | keep |
| hybrid_minds_ukf__12 | 41.865 | 24.648 | keep |
| hybrid_minds_ukf__13 | 4.893 | 2.900 | reject: insufficient overlap |
| hybrid_minds_ukf__19 | 25.554 | 7.068 | keep |
| hybrid_minds_ukf__20 | 2.356 | 1.087 | reject: insufficient overlap |
| hybrid_minds_ukf__23 | 5.075 | 2.537 | reject: insufficient overlap |
| hybrid_minds_ukf__25 | 9.605 | 3.443 | keep |
| hybrid_minds_ukf__28 | 19.030 | 2.356 | keep |
| hybrid_minds_ukf__33 | 1.812 | 1.812 | reject: insufficient overlap |
| hybrid_minds_ukf__40 | 18.305 | 13.230 | keep |
| hybrid_minds_ukf__45 | 34.253 | 17.761 | keep |
| joe_syntax_hospital__00 | 3.625 | 2.719 | reject: insufficient overlap |
| joe_syntax_hospital__01 | 17.580 | 2.537 | keep |
| joe_syntax_hospital__08 | 16.130 | 12.505 | keep |
| joe_syntax_hospital__09 | 3.262 | 3.262 | reject: insufficient overlap |
| joe_syntax_hospital__11 | 13.230 | 3.987 | keep |
| joe_syntax_hospital__12 | 19.754 | 17.942 | keep |
| joe_syntax_hospital__13 | 19.754 | 3.262 | keep |
| joe_syntax_hospital__14 | 7.068 | 2.356 | reject: insufficient overlap |
| joe_syntax_hospital__17 | 0.000 | 0.000 | reject: insufficient overlap |
| joe_syntax_hospital__18 | 1.994 | 1.812 | reject: insufficient overlap |
| netsky_hospital_classics__02 | 16.311 | 3.987 | keep |
| netsky_hospital_classics__06 | 13.593 | 5.256 | keep |
| netsky_hospital_classics__15 | 3.262 | 2.537 | reject: insufficient overlap |
| netsky_hospital_classics__17 | 16.855 | 9.968 | keep |
| netsky_hospital_classics__23 | 4.168 | 1.631 | reject: insufficient overlap |
| wilkinson_boomtown2026__33 | 30.991 | 14.136 | keep |

## Fresh baseline

Freshly recreated and rescored every one of the 20 admitted pairs with unchanged rules and gain-events-v2 scorer. No old survivor averages used.

- Train: **24.90** (n=16); held-out: **21.52** (n=4); failures: 0.
- Previous clean cohort: train 23.86 (n=25), held-out 24.54 (n=6). These means describe different datasets; changes are not engine gains.
- Full per-clip scores and exact rules: `results/baseline_real_blend.json`.

## Verification and cleanup

- `jobs/real-blend-verified-final.log`: **69 passed, 0 skipped, 0 failed** (52 engine tests + 17 protrans tests).
- Admission and daily pick both use `admit.load_admitted()`; smoke checked exactly the same 20 ids.
- Missing/failed measurements fail closed. Cache keys cover file fingerprints, thresholds and algorithm version; writes are locked and atomic.
- Tune decisions carry exact cohort ids so an older dataset cannot set the keep/reject floor for this one.
- Jobs ran through `jobs/runjob.sh` with running/done/failed markers and logs. Initial wrong-venv test attempt failed collection (soundfile absent); rerun in the existing system audio environment passed. A regression lookup initially failed after its row moved to the rejection archive; fixed to look in both admission and rejection records, with no new skip.
- Baseline renders were removed per worker; no `/tmp/protrans_bench/realblend_*` scratch remains. Rejected corpus clips are retained as audit data, not throwaway render output.
- Job webhook delivery is still conditional on its pre-existing environment configuration; this task did not provision credentials or claim that alerts were connected.
