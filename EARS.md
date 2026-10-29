# Ears: first tool probe (2026-10-28)

Setup: home GPU box (Apple MPS), venv `~/ears/.venv` (py3.11, torch 2.15, beat_this final0, basic-pitch CoreML, laion/larger_clap_music, MERT-v1-95M). Script: `ears/ears_probe.py`, raw scores: `ears/probe_results_2026-10-28.json`.
Calibration windows cut from dj-mix-03-60-refill mixdown: BAD 33:50-34:40 (1/5), BAD-ish 14:42-15:20 (far-back loop), GOOD 30:31-31:30 (5/5), 7 neutral blends, 2 solo (non-blend) windows, 40 Raveform pro transition segments as the reference set.

| metric (mixdown) | BAD | BAD-ish | GOOD | neutral range | pro median / p90 | verdict |
|---|---|---|---|---|---|---|
| Beat This beat-interval CV | **0.337** | 0.028 | 0.029 | 0.026-0.179 | 0.069 / 0.331 | separates BAD; false hits on beatless/breakdown windows |
| Beat This off-grid beats | **0.21** | 0.00 | 0.006 | 0-0.228 | 0.017 / 0.187 | same |
| Beat This bad bars (downbeats not 4 apart) | **0.25** | 0 | 0 | 0-0.318 | 0.015 / 0.29 | same |
| Basic Pitch dissonance (mean) | 0.013 | 0.010 | 0.013 | 0.004-0.023 | 0.002 / 0.009 | no separation on the mixdown |
| CLAP kNN distance to pro | 0.020 | 0.018 | 0.017 | 0.006-0.028 | 0.008 / 0.021 | no separation |
| MERT kNN distance to pro | 0.084 | 0.094 | 0.089 | 0.075-0.125 | 0.077 / 0.093 | no separation |

Takeaways
- Beat This works: it gets confused when two drum grids disagree. Use it gated on "both decks drumming" (else breakdowns trip it). Best as a per-deck check: run it on each deck's rendered signal and compare the grids (phase offset in ms + downbeat agreement).
- Basic Pitch on the mixdown can't tell whose notes are whose. Next: run it per deck (render A and B separately for the blend window, ideally the melodic stems) and score cross-deck intervals only.
- Off-the-shelf embedding distance doesn't hear "bad". They're only useful as features for a trained classifier (positives = pro + 4-5 ratings, negatives = synthetic bad blends).
- The far-back loop (BAD-ish) isn't an acoustic problem. Catch it with the structural rule (only loop the phrase right before the out point), not with ears.

Runtime for 52 files (~60 min audio), GPU box: MPS Beat This 18 s, Basic Pitch 56 s (CoreML), CLAP 51 s, MERT 86 s, about 3.5 min total. Same box CPU-only: see CPU line below.
CPU-only on the same box: Beat This 68 s, Basic Pitch 51 s, CLAP 46 s, MERT 209 s, about 6.2 min total. MPS is about 3.8x faster for Beat This and 2.4x for MERT. The box CPU wasn't benchmarked because two render workers were using its RAM.
