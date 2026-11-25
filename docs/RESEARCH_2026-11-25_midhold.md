# Midnight Mixer Technique Research — 2026-11-25 (ET)

**Outcome: nothing kept. `protrans/rules.json` and all defaults/thresholds are unchanged.** `MID_HOLD=1` remains off by default. No blind A/B clip pair was cut because `MID_HOLD` failed `X1` on 33/33 pairs and lost on held-out `v1` and overall `official_v2-place8c`.

## 1. Current Situation & Why `MID_HOLD` Was Tested

- **Carry-over status:**
  - *Shorter outgoing fade-out tail (approved 2026-11-13):* already completed (`TAIL_EXIT: 6` in `protrans/rules.json`; `TAIL_EXIT` and `TAIL_SHALLOW`/`_CAP`/`_GATE` evaluated in `docs/TAILEXIT_2026-11-15.md` and `jobs/tailcap-*-1116.log`).
  - *Later bass handoff / incoming bass fill:* already tested and rejected (`BASS_COVER`, `FADE=graphcut`, `DROP_SWAP`, `BASS_FILL` in `docs/BASS_FILL_2026-11-20.md` — held-out `34.07 -> 30.68`).
  - *Psychoacoustic consonance:* already tested as a hand-weighted cost and rejected (`CONSONANCE` in `docs/RESEARCH_2026-11-19_consonance.md` — held-out `34.07 -> 32.87 / 33.86`; pros sit at median roughness percentile `0.48`).
- **Today's blockers:**
  - On `corpus_v2` (860 deck-gain curves noted in `src2/mix_simple.py`, and 365 transitions inspected in `protrans/corpus_v2/features`), pros bring incoming mids (`150 Hz–2 kHz`) to full level **with the bass** (median `0` bars, IQR `-1..+3`) while bringing highs in earlier (median `-1` bar vs bass, IQR `-7..+2`; early highs sit `+2.2 dB` median above mids, IQR `0.0..+7.4 dB`).
  - By contrast, our `HIGH_SWAP` (`src2/mix_simple.py:95-105`) is gated by `bob()` (drums-on-drums >= 8 bars), which fired on only **3/33** pairs, and `HIGH_OFS=8` puts `c+8=16` out of `range(4, 16, 4)` whenever `c >= 8`, leaving `high_bar` active on only **2/33** cohort pairs (`mhb1125_base`).
  - Meanwhile, the listener's 2026-11-23 rating (`joe_syntax_hospital__13`, B rated `2/5`: *"Felt super random when that piano started"*) and 2026-11-24 blind test (`hybrid_minds_ukf__10`, rated `4/5`) highlighted both unmotivated mid-entry / phrasing and placement gaps.

## 2. Live-Verified Literature & Practitioner Sources (2024–2026)

1. **DJustify (Hsu et al., 2026)** — *"DJustify: Reason-and-Verify DJ Planning for Pop Transitions and Story-Driven Sets"*, arXiv:2610.33434 ([link](https://arxiv.org/html/2610.33434)). *Fit:* Exact audio-render verification gates paired with structural cue rules (phrase-end anchors, harmonic restarts, low-frequency onsets; re-cue if entry stalls in a flat intro).
2. **MixWeaver (Zhou et al., ISMIR 2026)** — *"MixWeaver: Stem-Aware Automatic DJ Transition Generation via Structured Discrete Optimization"* ([link](https://ismir2026program.ismir.net/poster_428.html)). *Fit:* Jointly constrains beat-aligned phrase placement and discrete stem-level transitions instead of unconstrained mid-band cuts.
3. **Mosaikbox (Sowula & Knees, ISMIR 2024)** — *"Mosaikbox: Improving Fully Automatic DJ Mixing Through Rule-based Stem Modification and Precise Beat-grid Estimation"* ([link](https://repositum.tuwien.at/bitstream/20.500.12708/212628/1/Sowula-2024-Mosaikbox%20Improving%20Fully%20Automatic%20DJ%20Mixing%20Through%20Rule-ba...-vor.pdf)). *Fit:* Conditions EQ timing on timbral/rhythmic activity (`high_at` without a full-drum `bob()` gate) and avoids prolonged vocal overlap (>2 s).
4. **Raveform (Kim et al., TISMIR 2026, Apr 20 2026)** — *"Raveform: A Dataset of Metrical and Functional Structure Annotations for EDM Tracks in DJ Mixes"* ([link](https://transactions.ismir.net/articles/10.5334/tismir.288)). *Fit:* Separates percussive `intro/outro` from drumless `ambient-intro/ambient-outro` and sub-band profiles to avoid flat cue entries.
5. **Switch-Point Interpretability (Zehren, Alunno & Bientinesi, *Signals* 2024, 5(4), 642–658)** — ([link](https://www.mdpi.com/2624-6120/5/4/36); earlier *CMJ* 2022 [link](https://direct.mit.edu/comj/article/46/3/67/117159/Automatic-Detection-of-Cue-Points-for-the)). *Fit:* SHAP analysis on EDM-150 shows pro switch points align with 4-bar boundaries of high novelty in total energy, bass RMS, drum-onset count, and timbre.
6. **Cue Point Object Detection (Arguello, Lanzendörfer & Wattenhofer, ISMIR 2024)** — ([link](https://ismir2024program.ismir.net/poster_19.html)). *Fit:* Frames cue selection as localized boundary detection on spectrogram context rather than fixed offset rules like `drop1 - 16`.
7. **Sub-band Convex EQ Optimization (Kim, Yang & Nam, NIME 2021)** — ([link](https://nime.org/proc/nime2021_87/); see also DJtransGAN [arXiv:2110.06525](https://arxiv.org/abs/2110.06525)). *Fit:* Motivates band-separated fader trajectories (`MID_HOLD` prototype), though subject to `X1` guardrails here.
8. **Practitioner DnB & X** — CyberDJ on liquid bass/drum balance ([link](https://cyberdj.net/blog/liquid-bass-and-drum-mix/)), 35hz ([link](https://35hz.co.uk/how-to-mix-drum-and-bass)), BeatmatchGuru ([link](https://beatmatchguru.com/how-to-dj-drum-and-bass/)), and an X double-drop example ([post](https://x.com/ANHEL_DNB_MIX/status/2122639718693445680)). *Fit:* Phrase-aligned top-end swaps (hats/percussion) before bass handoff, keeping mid presence smooth rather than gating mids abruptly.

## 3. Prototype Tested: `MID_HOLD` (Off by Default)

- **Code changes (off by default, `MID_HOLD=0`):**
  - `src2/mix_simple.py` (lines 711–718): when `MID_HOLD=1` (default `0`) and a blend has a bass swap, writes `d['auto']['mid']` holding the incoming `150 Hz–2 kHz` band `MID_HOLD_DB` dB (default `6`) below the crossfader until the bass swap, then opening it on the same raised cosine as `'low'`.
  - `src2/engine.py` (lines 146–153): renders `d['auto']['mid']` via zero-phase `XO..HXO` band subtraction (`low + mid + high == original`).
  - `protrans/recreate.py` (line 16): passes `MID_HOLD`, `MID_HOLD_DB` from rules/env; `protrans/research_1125/` holds `smoke.py`, `eval_midhold.sh`, `eval_v2.py`, `bandlag.py`.
- **Jobs run via `jobs/runjob.sh`:**
  - `midhold-smoke-1125` (`done rc=0`): `joe_syntax_hospital__13` `v1` `29.77 -> 29.76`.
  - `midhold-cohort-1125` (`done rc=0`): full 33-pair `eval_cohort.py` + `eval_tailexit.py` for `mhb1125_base`, `mh6_1125` (`MID_HOLD_DB=6`), and `mh10_1125` (`MID_HOLD_DB=10`), using temp `/tmp/rules_midhold_1125_{6,10}.json`.
  - `midhold-v2-1125` & `midhold-v2-mh10-1125` (`done rc=0`): scored all 33 pairs with `protrans/score_v2.py` (`official_v2-place8c`).

## 4. Cohort Results (33 Protrans Pairs: 21 Train, 12 Held-Out Test)

*Higher is better for both `v1` (`protrans/score.py`, `gain-events-v3-beatid`, remains official) and `v2` (`protrans/score_v2.py`, `official_v2-place8c`). CIs are 4000-draw mix-grouped bootstrap deltas vs `mhb1125_base`.*

| Variant | `v1` Train | `v1` Held-Out | `v1` All | `official_v2` Train | `official_v2` Held-Out | `official_v2` All | Must-Pass (`eval_tailexit`) |
|---|---:|---:|---:|---:|---:|---:|---|
| `mhb1125_base` (default) | 33.30 | **33.92** | 33.53 | **34.84** | 32.15 | **33.86** | **29/33** (test **12/12**, train 17/21: `L1:1, N1:3, X1:0`) |
| `mh6_1125` (`MID_HOLD_DB=6`) | 33.79 (+0.48 [-0.01, +0.78]) | 33.36 (-0.56 [-1.50, +0.22]) | 33.63 (+0.10 [-0.83, +0.58]) | 34.50 (-0.34 [-0.56, +0.02]) | 32.19 (+0.03 [-0.15, +0.28]) | 33.66 (-0.21 [-0.46, +0.11]) | **0/33** (`X1:33`, `L1:2`, `N1:3`) |
| `mh10_1125` (`MID_HOLD_DB=10`) | 33.59 (+0.29 [-0.02, +0.48]) | 33.48 (-0.44 [-0.95, +0.02]) | 33.55 (+0.02 [-0.57, +0.34]) | 34.26 (-0.58 [-1.01, +0.12]) | 32.21 (+0.06 [-0.07, +0.27]) | 33.52 (-0.35 [-0.80, +0.15]) | **0/33** (`X1:33`, `L1:2`, `N1:3`) |

### Blend Diagnostics (`eval_tailexit`, 33 pairs)
- **Summed-lows dip median (dB):** `23.6` (`base`) -> `24.3` (`mh6`, worse) -> `24.6` (`mh10`, worse).
- **Manabe spectral collision (`pcol_med`):** `0.0369` (`base`) -> `0.0328` (`mh6`) -> `0.0294` (`mh10`).
- **Manabe continuity (`pcty_med`):** `2.7599` (`base`) -> `2.7596` (`mh6`) -> `2.7655` (`mh10`).
- **Banger clash rate (`banger_med`):** `0.1004` (`base`) -> `0.0758` (`mh6`) -> `0.0581` (`mh10`).
- **Designed tail24 median:** `6.0` bars across all three.
- **Zero-fail checks on `mh6`/`mh10`:** `bass_gap`, `V1`, `outgoing_fader_tail`, `bass_never_doubles` all passed `33/33`.

### X1 Failure Proof (Real `MID_HOLD` Fault, Not a Harness Bug)
- In the exact same `eval_tailexit.py` harness, `mhb1125_base` had **`X1: 0`** (`33/33` passed `X1`; `12/12` test passed all checks).
- Both `mh6_1125` and `mh10_1125` failed **`X1: 33/33`** because `src/guardrails.py:64` enforces `"crossfader + one bass swap + optional high swap only"` (`k not in ('gain','low','high')` fails `X1`), and `MID_HOLD` writes `d['auto']['mid']`. `mh6`/`mh10` also added one extra `L1` failure (`1 -> 2` on train).

## 5. Diagnosis of Losers & Why `MID_HOLD` Lost

Across `mh6_1125` vs `mhb1125_base` (`0` window changes; identical `[a_out, b_in, X]` on all 33 pairs):
- **Mechanism:** Holding incoming `150 Hz–2 kHz` mids down until the bass swap delays when the incoming track becomes audibly present in the mix (`entry` event shifts 1–4 bars later), collapsing detected `blend_length` and hurting `stem_curves`/`deck_curves` when pros actually open incoming mids with the crossfader:
  - `maduk_liquicity_lunar2025__02` (test): `v1` `27.78 -> 26.21` (`-1.57`, `mh10` `28.64`), `v2` `33.39 -> 34.86` (`mh10` `35.38`). Audible `entry` shifted from clip bar `10` to `14`, shrinking detected `blend_length` `6 -> 2` bars (`len` subscore `46.55 -> 28.39`). (`v2` ticked up only because the delayed entry happened to sit closer to pro's `b=39.3`.)
  - `netsky_hospital_classics__15` (test): `v1` `40.90 -> 41.06` (`mh10` `41.07`), **`v2` `50.22 -> 48.99` (`-1.23`, `mh10` `48.76`)**. Incoming audible `entry` pushed from `b=2.0` to `b=6.0` vs pro `b=0.2`, cutting `entry` placement subscore `58.90 -> 45.56`.
  - `joe_syntax_hospital__12` (train): **`v1` `32.29 -> 31.09` (`-1.20`, `mh10` `32.21`)**, **`v2` `36.43 -> 35.50` (`-0.93`, `mh10` `36.97`)**. Audible `entry` shifted `9 -> 10`, `blend_length` shrank `9 -> 6` bars (`14.14 -> 9.55`), `stem_curves` fell `43.68 -> 41.99` (vocals `48.82 -> 44.03`, melody `44.04 -> 42.22`).
  - `maduk_liquicity_lunar2025__05` (test): **`v1` & `v2` `26.56 -> 24.40` (`-2.16`)**. Audible `entry` delayed `10 -> 13`, `blend_length` collapsed `4 -> 1` bar (`54.91 -> 37.35`).
  - `joe_syntax_hospital__11` (train): **`v1` `60.51 -> 57.00` (`-3.51`)**, **`v2` `60.52 -> 56.79` (`-3.73`)**. `swap` and `beat` subscores dropped (`66.69 -> 50.98`, `47.59 -> 34.51`).
  - (`hybrid_minds_ukf__00` train `v1` `29.45 -> 38.82` vs `v2` `39.22 -> 34.67` is a RANSAC match flip between repeated sections `bar 88` drop 1 vs `bar 200` outro on identical windows.)

## 6. Next X1-Compliant Directions (Diagnostics Run Read-Only)

Because `render-n1125` (`ridegate` + `cueonly_gated`) owns the single render slot tonight, two X1-compliant candidates were diagnosed without rendering:
1. **Un-gate `HIGH_SWAP` (`>2 kHz` high lane, already legal under `X1`):** Currently `high_at` (`src2/mix_simple.py:95-105`) requires `bob()` (drums-on-drums >= 8 bars), which passes on only **3/33** pairs, and `HIGH_OFS=8` pushes `c+8=16` out of bounds unless `c=4`, so `high_bar` fires on only **2/33** pairs. Across `33` cohort blends, **25/33** pairs have active above-bass energy (`>= -6 dB` of body) on both decks for >= 8 bars (`7/33` in `hat`). Next test: gate `high_at` on `>2 kHz` / above-bass activity instead of `bob()`, with `HIGH_OFS=4`, keeping `X1` intact.
2. **4-bar Cue Novelty / Percussive Anchor (Zehren et al. 2024 / DJustify 2026 / Raveform 2026):** On 32 cohort pairs, default cues (`d1 - 16`) have negative 4-bar all-band novelty on multiple tracks (`-4.70` on `hybrid_minds_ukf__00`, `-0.53` on `__10`, `-6.29` on `__09`, `-0.98` on `__12`, `-1.76` on `__13`), whereas pros often enter on drum/percussion onset rises inside the intro (`+5.54` / `+10.98` low on `__00` at bar 13.9; `+6.84` / `+11.19` low on `__10` at bar 21.2). Adding 4-bar novelty / percussive-intro features to `cueonly_gated` (which already cut cue MAE by `-4.19` bars in `picker-cv-1125`) keeps `X1` and `rules.json` untouched.
