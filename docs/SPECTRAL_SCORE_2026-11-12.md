# Spectral collision / continuity scorer (2026-11-12)

Diagnostic only. Not a failing test, not a build gate, and `protrans/rules.json` was not changed. No existing test threshold was loosened or edited.

Implements Daito Manabe, *On the Measurability of DJ Mix Quality* (March 2026), https://projects.daito.ws/dj-mix-research-institute/paper/on_measurability_dj_mix_quality_daito_manabe_en.pdf §§5.2–5.3: contribution-weighted **spectral collision** (penalise both decks occupying the same low / low-mid band at once) and **spectral continuity** (reward a tone that glides from old to new rather than lurching). Companion rate: Banger Lab `clash()` over 6 bands (20–80, 80–250, 250–800, 800–2500, 2500–7000, 7000–20000 Hz), which counts a hit when both decks already fill a band on the same beat.

Our mixes are scored from the actual rendered deck signals (crossfader gain and bass/high lanes already applied, beat-grid aligned). Pro clips and daily A/B files are scored by fitting non-negative per-band contributions of the two aligned sources into the master (Manabe eq. 5). The overlap window is the contribution-activity run μ (Manabe §4.3).

Calibrated at 2026-11-12 12:18 America/New_York on **33 admitted** pro transitions (5 of 39 clips failed to align, all una-admitted). Score scales map a penalty equal to the pro median to 0.70:

- `s_col = 0.1528`
- `s_cty = 7.6955`

Higher Scol / Scty is better; higher pcol / pcty / banger clash rate is worse.

## Pro distributions (admitted, n=33)

- collision penalty pcol: median **0.0545**, p95 **0.1084**, p5 0.0182, min 0.0074, max 0.1324
- continuity penalty pcty: median **2.745**, p95 **6.143**, p5 1.927, min 1.459, max 9.001
- Scol: median 0.700, p5 0.493, p95 0.889
- Scty: median 0.700, p5 0.451, p95 0.779
- Banger clash rate: median **0.343**, p95 **0.601**, p5 0.117, min 0.066, max 0.645

## Mix 08 v2 (r11c) and long1h

Both full mixes sit *cleaner* than the pro median on collision and on Banger clash, which is consistent with a phrase-snapped bass swap. long1h is essentially tied with r11c on these metrics (mean pcol delta −0.0003).

- r11c pcol: n=25, median **0.0335**, p95 0.0416, max 0.0453; Scol median 0.803
- long1h pcol: n=25, median **0.0334**, p95 0.0461, max 0.0500; Scol median 0.804
- r11c Banger: median 0.117, max 0.209
- long1h Banger: median 0.122, max 0.219
- r11c pcty: median 2.127; long1h pcty: median 2.247
- blends above the pro p95 of pcol (0.108) or Banger (0.601): **0/25 and 0/25**

Highest r11c pcol: Alone → Trip (0.045), Always Be → Hypnotic (0.042), Ember → Bad To Me (0.038). Highest long1h pcol: Blur → Alone (0.050), Ember → Bad To Me (0.047). Ember → Bad To Me (the long-blend t12 bass-hole history) is in the upper tail of both builds, but still under the pro median.

## Known-bad cases

### Shine In → Dusk To Dawn (2026-11-11 equal-level clash, the listener 2/5 on the daily ours)

| version | the listener | pcol | Scol | pcty | Scty | Banger clash |
|---|---|---|---|---|---|---|
| daily ours | 2/5 | 0.0476 | 0.733 | 2.768 | 0.698 | **0.480** |
| daily pro (loudness-matched clip) | (the pro) | 0.0751 | 0.612 | 1.976 | 0.774 | 0.286 |
| official Joe Syntax clip | — | 0.0726–0.0784 | 0.599–0.622 | 1.979–1.989 | 0.772–0.773 | 0.318–0.372 |
| FADE=long, LONG_SOLO=16 | 3.5/5 | 0.0474 | 0.733 | 2.044 | 0.767 | 0.367 |
| long fix (LONG_SWAP=exit, LONG_SOLO_STRUCT=1) | better than 4/5 | 0.0551 | 0.697 | 2.758 | 0.699 | 0.451 |
| engine rebuild | “pretty good” | 0.0503 | 0.720 | 2.341 | 0.738 | 0.346 |

Manabe pcol **does not** flag the 2/5 ours: it is *less* collided than the matching pro and sits below the pro median. A p95 pcol gate would have missed it.

Banger clash() **does** line up with the equal-level complaint: the 2/5 ours is 0.480 vs the pro’s 0.286. The 3.5/5 long cut drops it to 0.367; the engine rebuild to 0.346. The approved long_fix is still 0.451, but its activity window started at 1.2 s and ran the whole clip, so that one number is less trustworthy than the 3.5/5 cut (window 20–66 s).

Continuity also agrees on the original 2/5 vs the pro (2.77 vs 1.98) and on the 3.5/5 long cut (2.04). long_fix continuity did not improve (2.76), same window caveat.

### Deeper → Just Hold On (mix 03-60 v1, listener: “horrible”)

Skipped. The mix audio (`dj-mix-03-60.mp3`, `pro_sets/wav/dj-mix-03-60.wav`) and the stem wav for the 124 BPM original Just Hold On (`_K2sC9nrf_A`) are no longer on disk, so the actual car-crash blend cannot be rescored. The historical failure was a fake 174 grid on a UK-breaks track (guardrail R1). This spectral scorer is not designed to catch a tempo/rhythm wreck, and it should not be asked to stand in for R1.

## Agreement with the listener (protrans/log.jsonl)

| date | pair | the listener | ours pcol (Banger, pcty) | pro pcol (Banger, pcty) |
|---|---|---|---|---|
| 2026-11-08 | She Just Wanna Dance → Cosmic Flowchart | (unrated) | skipped, sources missing from disk | skipped |
| 2026-11-09 | Secret Place → These Simple Things | couldn’t tell, “quite good” | 0.019 (0.045, 4.28) | 0.046 (0.363, 3.98) |
| 2026-11-10 | The Feeling → Fearful Symmetry | 4/5, correctly IDed the pro | 0.037 (0.111, 1.70) | 0.078 (0.558, 2.34) |
| 2026-11-11 | Shine In → Dusk To Dawn | 2/5, correctly IDed the pro | 0.048 (**0.480**, 2.77) | 0.075 (0.286, 1.98) |
| 2026-11-12 | Final Hours → Listen | 4/5, thought ours was the pro | 0.037 (0.076, 3.09) | 0.128 (0.514, 4.46) |

The only rated daily where ours has a *higher* Banger clash rate than the pro is the 2/5 Shine In day. On the two 4/5 days ours is much less clashy than the pro. Manabe pcol is lower for ours than for the pro on every scored daily, including the 2/5, so it does not track that complaint.

Spearman (ours pcol vs rating, n=3): rho = −0.87, p = 0.33 (right direction, not significant). Spearman (ours Scty vs rating): rho = 0.0.

## Verdict

**Keep as a diagnostic only; too early to gate.** (`promote_to_gate_later`: false)

The Banger clash rate is the more useful of the two clash signals for the equal-level problem the listener actually heard. Manabe pcol should not be the thing we promote: it did not separate the known-bad Shine In ours from the pro, and a pro-p95 pcol gate would have flagged none of Mix 08 and would have missed that 2/5 as well (the 2/5 Banger rate 0.480 is also still under the pro p95 of 0.601, so a naive p95 Banger gate would have missed it too). Continuity is worth keeping on the diagnostic figure, but it is not consistent enough to gate on this sample.

Next step: leave both scores and the new blend-diagnostic lane in place, collect more the listener-rated blends, and only then consider a data-calibrated gate (never a hand-set threshold). The Deeper → Just Hold On car crash stays a rhythm problem for R1.

## Files

- `src2/spectral_score.py` — scorer
- `src/tests/test_spectral_score.py` — unit tests (synthetic signals only; 9 passed)
- `src/calib/spectral_vs_pro.py` — this calibration
- `src/calib/spectral_scales.json` — calibrated scales
- `src/calib/spectral_vs_pro_results.json` — full numbers
- `src2/blend_diag.py` — extra diagnostic lane (generate-only, never fails a build)
- figures under `deliver/spectral/2026-11-12/` (per-bar collision / continuity lanes; not a build gate)
