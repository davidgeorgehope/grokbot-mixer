# Midnight research 2026-11-19: consonance (psychoacoustic roughness) window ranking

**Outcome: nothing kept. `protrans/rules.json` is unchanged** (no `CONSONANCE` key; identical to the last backup). The `CONSONANCE=1` flag stays off by default.

## What was tried
- Source idea (adjacent field, music psychoacoustics, not DJ-mixing papers): Gebhardt, Davies & Seeber, "Psychoacoustic Approaches for Harmonic Music Mixing", *Applied Sciences* 6(5):123, 2016. It rates how two overlapping tracks sound together by the sensory roughness between their spectral peaks (Plomp-Levelt curve, Sethares parameterisation) instead of key labels.
- Implementation: `src2/consonance.py`. Per-bar median spectra (drums mostly removed), mid band 150 Hz to 4 kHz, cross-deck roughness only, weighted by the crossfader gains. Hook in `protrans/recreate.py`: adds `W * log(R(win)/R(default))` to each family's pick cost and offers one extra `cons_cue` family.
- Jobs: `cons-prep-1119` (peak caches), `cons-diag-1119` and `cons-diag400-1119` (diagnostic), `cons-cohort-1119d` (cohort, `protrans/eval_consonance.sh`). Earlier attempts `cons-cohort-1119`, `-1119b` and `-1119c` were stopped or restarted at about 12:10 AM ET and superseded by `-1119d`.

## Results
### Cohort (`cons-cohort-1119d`, finished rc=0 at 1:18 AM ET; 33 protrans pairs, 21 train / 12 held-out)
Weights 0.3 and 1.0 were declared in advance. The weight was to be chosen on the train mean only.

| variant | held-out score | train score | hard-fail pairs | must-pass blend checks | families used |
|---|---|---|---|---|---|
| cb1119_base (current rules) | **34.07** | **32.40** | 0 | 29/33 (L1 x1, N1 x3) | nat_short 32, nat_long 1 |
| cw03_1119 (W=0.3) | 32.87 | 30.72 | 0 | 29/33 (L1 x1, N1 x3) | nat_short 25, cons_cue 5, cue_early 2, nat_long 1 |
| cw10_1119 (W=1.0) | 33.86 | 28.75 | 0 | 28/33 (L1 x2, N1 x3) | nat_short 14, cons_cue 10, nat_long 5, cue_early 4 |

Both weights score below the baseline on train and on held-out. W=1.0 also adds one must-pass failure (an extra L1).

### Diagnostic (`cons-diag400-1119`, `protrans/results/consonance_diag_f400.json`)
For each pair, every same-length 4-bar-aligned window was ranked by roughness (percentile 0 = most consonant available, 1 = roughest).
- The pros' real overlaps have a **median percentile of 0.48**, which is right in the middle. Pros don't seek the most consonant window (Wilcoxon against 0.5: p = 0.94).
- Our default picks have a median percentile of **0.30**. They are already more consonant than what the pros chose (paired Wilcoxon pro vs default: p = 0.039; the pro window was smoother on only 12 of 33 pairs).
- The default pick's raw roughness has no relation to the similarity score (Spearman rho = -0.01, p = 0.96).

**In plain terms:** making blends "more consonant" moves us away from what pros do, not toward it. On its own, roughness doesn't explain pro choices.

## Caveat
The cohort was judged on the **old similarity score** (v3 held-out and train means). the listener doesn't trust that score as the definition of "better". The result means "consonance as a hand-weighted cost term doesn't help on the old score". It doesn't show that consonance is useless.

## Recommendation
Drop the hand-weighted cost term. Instead, test window roughness (and the roughness percentile within the pair) as a **candidate feature for the model picker** (`protrans/replica/picker_1119b.py` exit and cue rankers). Judge it the same way as the picker:
- decision-level match to the pros (exit and cue bar error, hit@8 and hit@16, with leave-one-DJ-out and mix-grouped bootstrap CIs), and
- hard checks (v2 hole, clash, half-beat, pump) as a veto only.

The ranker can learn when roughness matters, for example if it only separates candidates within a section, instead of being forced to always lower it. Feature caches already exist for the 33 protrans pairs (`cons-prep-1119`). Corpus-v2 pairs would need the peak cache before a dev-CV run.
