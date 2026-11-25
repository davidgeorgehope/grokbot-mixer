# Picker CV 11-25 Follow-Up: Exit-Miss Diagnosis, Hybrid Pickers & Pinned Official Scores

Checkpoint started 2026-11-25 01:44 AM ET.
Script: `protrans/replica/picker_1125_followup.py` | Tests: `protrans/tests/test_picker_1125_followup.py`.
No edits to `rules.json` or defaults.

## 1. Recovered `picker-cv-1125` Full Results (843 dev transitions, 101 mixes, 25 DJs)
Source: `jobs/picker-cv-1125.log`, `protrans/replica/picker_1125_cv.json`, `protrans/replica/picker_1125_analysis.json`.
The webhook tail (`tail -c 1500`) truncated lines 28–33 of `jobs/picker-cv-1125.log`. Recovered full summary:

| Arm | Exit+Cue Mean | Exit Mean (Med) | Exit @8 / @16 | Cue Mean (Med) | Cue @8 / @16 | Abstain | Δ Exit+Cue vs Default [95% Mix-Clustered CI] |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 37.13 | 46.82 (34.1) | 16.5% / 35.2% | 27.44 (18.7) | 18.6% / 42.9% | 100% | — |
| `cueonly_gated` | 35.03 | 46.82 (34.1) | 16.5% / 35.2% | 23.25 (16.3) | 22.4% / 48.9% | 21.1% | −2.09 [−3.07, −1.17] |
| `ridegate` | 33.74 | 44.23 (34.0) | 18.3% / 34.8% | 23.25 (16.3) | 22.4% / 48.9% | 12.8% | −3.39 [−5.32, −1.38] |
| `ridegate_cand2` | 34.35 | 45.46 (38.8) | 17.3% / 32.7% | 23.25 (16.3) | 22.4% / 48.9% | 13.5% | −2.77 [−4.71, −0.78] |
| `ref_full_gated` | 34.17 | 45.08 (39.0) | 18.6% / 34.2% | 23.25 (16.3) | 22.4% / 48.9% | 7.0% | −2.96 [−4.95, −0.96] |
| `ref_full_plain` | 33.56 | 44.05 (35.0) | 19.8% / 35.6% | 23.07 (16.3) | 23.6% / 49.1% | 5.3% | −3.57 [−5.48, −1.57] |
| `ref_cand2_full_gated` | 34.92 | 46.59 (43.1) | 17.1% / 31.4% | 23.25 (16.3) | 22.4% / 48.9% | 7.5% | −2.20 [−4.26, −0.25] |
| `majority` (`outro_intro` + `drop_cue`) | 36.22 | 47.37 (38.4) | 7.1% / 14.7% | 25.06 (22.4) | 22.4% / 35.7% | 0.0% | −0.91 [−2.57, +0.96] |
| `rule_drop_exit` (`drop1_end` + `drop_m16`) | 49.24 | 70.96 (64.6) | 4.4% / 9.3% | 27.51 (18.9) | 18.5% / 42.5% | 11.6% | +12.11 [n/a] |

Key `picker_1125` exit strata:
- On `pro_mid` (`pro_out < na − 40`, n=455): `default` 77.0 vs `ridegate` 54.4 vs `ref_full_plain` 49.9.
- On `pro_late` (`pro_out >= na − 40`, n=388): `default` 11.4 vs `ridegate` 32.3 vs `ref_full_gated` 36.2.
- `ride_auc` (out-of-fold ride-vs-leave classifier AUC) = **0.587**.

## 2. Diagnosis: Why Exits Miss (`picker_1125_diagnosis.json`)

### A. Why `default` misses (>16 bars on 546 / 843 = 64.8%)
`default` almost always places the exit in the outro or late drop 2/3 (`drop2`: 361, `outro`: 312, `drop3`: 104). Its misses break into 6 buckets:
1. **Pro exited during outgoing drop 1 or its build (`245`, `29.1%`)**: Quick-mix / double-drop transitions where the pro brings track B in during drop 1 (or right at the start of drop 1) while `default` plays all the way through drop 2 to the outro (80–225 bar errors).
2. **Pro exited at drop-1 end or into the breakdown (`124`, `14.7%`)**: Pro transitions at the drop-1 -> breakdown handoff (`near_drop1_end` ±12 bars accounts for 190 of the 455 mid-track exits), whereas `default` stays until the end.
3. **Pro exited in a later drop mid-track (`>40 bars left`, `85`, `10.1%`)**: Multi-drop or long tracks (>200 bars) where the pro leaves during drop 2 / drop 3 before the final 40 bars.
4. **Pro made a very-late tail exit (`<=12 bars left`, `55`, `6.5%` missed >16 bars; `213` total tail exits)**: Pro brings track B in during the last ~10 bars with a short ~8-bar overlap; `default` (16- or 32-bar blend) starts 16–32 bars early.
5. **Late outro / drop-end offset (`33`, `3.9%`)**: Both pro and `default` stay near the end (`>= na − 40`), but differ by >16 bars (e.g., pro exited at outro start `na − 40` vs `default` at `na − 16`, or 16 vs 32 bar blend).
6. **Pro ultra-early intro exit (`<16 bars`, `4`, `0.5%`)**: Immediate intro swap (e.g. `alpha_rhythm_AU0V19j8oKM__16` at bar 0).

### B. Why learned exit models (`ref_full_gated` / `ridegate`) miss (>16 bars on 555 / 550 of 843)
1. **False-late holds (`268` / `31.8%` in `ref_full_gated`; `283` / `33.6%` in `ridegate`)**: When uncertain, the ranker/gate stays at `default` even when the pro exited early.
2. **False-early jumps (`147` / `17.4%` in `ref_full_gated`; `119` / `14.1%` in `ridegate`)**: When the pro rode to the outro/late drop 2, the learned model jumped mid-track — **87% of those false jumps (129/148 in `ref_full_gated`) went straight to the mid-track `breakdown` (88) or `build` (41)**! This costs +30 to +120 bars per miss (`pro_late` error jumps 11.4 -> 32.3–36.2).
3. **Wrong mid-track section (`85` / `10.1%` in `ref_full_gated`; `82` / `9.7%` in `ridegate`)**: Both exited mid-track, >16 bars apart (e.g., pro left during drop 1 body while model picked breakdown, or spurious intro-drops `[0, 16]` shifted `drop1_end`/`breakdown` tags).
4. **Late tail/outro offset (`55` / `6.5%` in `ref_full_gated`; `66` / `7.8%` in `ridegate`)**: Both `>= na − 40`, >16 bars apart.

### C. Track-content & DJ-pacing root causes
- **DJ pacing dominates mid-track vs outro choice (style-free ceiling):** Mid-track exit rate varies from **21% (`Alpha Rhythm`) / 25% (`Sound Territory`) / 42% (`KushSessions`, n=406)** up to **80–90% (`UKF`, `MrMoMMusic`, `Hikari Sakai`, `TheHeshBesh`, `Shogun Audio`)**. Without knowing the DJ's earlier pacing in the mix, pair-only AUC for `mid vs late` is **0.57–0.59**.
- **Track length `na` is the strongest structural signal (`r = +0.422, p = 1.2e-37` with `na - pro_out`):** Pros target a ~120–150 bar play length regardless of track length: when `na < 170` bars, `mid_rate = 43%` (default error 31.2, `ridegate` hurts at 32.6); when `na >= 220` bars, `mid_rate = 72%` (default error **72.2**, `ridegate` drops to **51.5**).
- **Spurious intro drops & breakdown contrast:** `structure.py` sometimes tags loud intros (`[0, 16]`) as `drop1`, corrupting `drop1_end` and `breakdown` anchors. Quiet breakdowns (`>= 10 dB` drum drop) appear in ~31% of misses, thin Track B intros (`>= 15 dB` bass contrast) in ~69% of misses, and drop-on-drop cues in ~21%, with weak marginal correlation (`|r| < 0.06`) to whether the DJ exits early vs late.

## 3. Hybrid Pickers Under Cross-Validation (running `picker-followup-cv-1125`)
1. **`hybrid_sec_cue`**: Section-aware cue ranker (adds Track B thinness/build/drop1 contrast + Track A default-exit coupling `(d1b - x) - (na - dex)` and `(d1b - x) - dX`) + default exit + default X.
2. **`hybrid_sec_mix`**: `hybrid_sec_cue` + section-aware **Bayes-mixture Expected-MAE exit gate** (`p_early * |c - mu_early| + (1 - p_early) * |c - mu_late|`, filtering spurious intro drops, selecting gate margin `M` via nested inner leave-one-DJ-out CV).

## 4. Follow-Up Hybrid Cross-Validation Results (`picker-followup-cv-1125`, n=843, 25 DJs, 101 mixes)
Checkpoint updated 2026-11-25 02:00 AM ET. Output: `protrans/replica/picker_1125_followup_cv.json`.

| Arm | Exit+Cue Mean | Exit Mean (Med) | Exit @8 / @16 | Cue Mean (Med) | Cue @8 / @16 | `pro_mid` Exit | `pro_late` Exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 37.13 | 46.82 (34.1) | 16.5% / 35.2% | 27.44 (18.7) | 18.6% / 42.9% | 77.03 | 11.40 |
| `majority` | 36.22 | 47.37 (38.4) | 7.1% / 14.7% | 25.06 (22.4) | 22.4% / 35.7% | 57.64 | 35.33 |
| `cueonly_gated` (learned cue + default exit) | 35.03 | 46.82 (34.1) | 16.5% / 35.2% | **23.25** (16.3) | 22.4% / **48.9%** | 77.03 | 11.40 |
| `hybrid_sec_cue` (sec-aware cue + default exit) | 35.15 | 46.82 (34.1) | 16.5% / 35.2% | 23.48 (16.9) | **22.9%** / 47.0% | 77.03 | 11.40 |
| `hybrid_sec_mix` (sec-aware cue + Bayes-mix exit) | 34.14 | 44.81 (39.7) | 15.9% / 31.0% | 23.48 (16.9) | **22.9%** / 47.0% | **46.95** | 42.30 |
| `ridegate` | **33.74** | **44.23** (34.0) | **18.3%** / 34.8% | **23.25** (16.3) | 22.4% / **48.9%** | 54.37 | 32.34 |

### 95% Bootstrap CIs vs `default` (4000 draws; Mix-Clustered / Pair-Clustered)
- **`cueonly_gated`**:
  - Exit+Cue Δ: **−2.10** (mix `[−3.07, −1.17]`, pair `[−2.67, −1.52]`)
  - Cue Δ: **−4.19** (mix `[−6.14, −2.35]`, pair `[−5.33, −3.04]`)
  - Cue @8 / @16 gain: `+3.8 pts` (mix `[−1.4, +8.7]`, pair `[0.0, +7.5]`) / `+5.9 pts` (mix `[−2.5, +14.1]`, pair `[+1.7, +10.4]`)
  - Exit Δ: `0.00` (zero `pro_late` regression). vs `majority`: Exit+Cue Δ `−1.18` (mix `[−3.25, +0.65]`, crosses 0).
- **`hybrid_sec_cue`**:
  - Exit+Cue Δ: **−1.98** (mix `[−2.75, −1.20]`, pair `[−2.50, −1.45]`)
  - Cue Δ: **−3.96** (mix `[−5.50, −2.40]`, pair `[−4.99, −2.91]`)
  - Cue @8 / @16 gain: `+4.3 pts` (mix `[0.0, +8.4]`, pair `[+0.8, +7.7]`) / `+4.0 pts` (mix `[−2.6, +10.6]`, pair `[+0.1, +7.9]`)
  - vs `majority`: Exit+Cue Δ `−1.07` (mix `[−3.01, +0.57]`, crosses 0).
- **`hybrid_sec_mix`**:
  - Exit+Cue Δ: **−2.98** (mix `[−5.31, −0.50]`, pair `[−4.69, −1.28]`), vs `majority`: **−2.07** (mix `[−3.97, −0.04]`, pair `[−3.56, −0.64]`).
  - Exit Δ: `−2.01` (mix `[−6.63, +3.21]`, pair `[−5.28, +1.21]`, crosses 0). Slashes `pro_mid` error `77.03 -> 46.95`, but inner-CV `margin=5` on KushSessions pushes `pro_late` error `11.40 -> 42.30` and lowers `exit@16` (`35.2% -> 31.0%`).

## 5. Why `picker-fresh-1125` (n=14) Beat Default While 843-Pair CV Did Not
Fresh mix `kushsessions_z8SnJBUd-0U` (14 transitions, `picker_1125_fresh.json`):
- **Root cause of divergence:** In dev, KushSessions rides to the outro 58% of the time (`mid_rate = 42%`), and 46% of all 843 dev pairs ride late (`>= na − 40`). In `z8SnJBUd-0U`, KushSessions exited mid-track on **10 of 14 transitions (`mid_rate = 71%`)**, so `default` suffered a huge **63.18 bar** mean exit error (`exit@16 = 14.3%`).
- On `z8SnJBUd-0U` (4000-draw pair bootstrap CIs for n=14):
  - `default`: Exit+Cue `49.72`, Exit `63.18` (med `69.1`, `@16 = 14.3%`), Cue `36.25`.
  - `cueonly_gated`: Exit+Cue `45.66` (`Δ −4.06 [−8.86, +0.42]`), Cue `28.13` (`Δ −8.12 [−17.71, +0.85]`), Exit `63.18`.
  - `hybrid_sec_cue`: Exit+Cue `45.59` (`Δ −4.13 [−8.18, −0.41]`), Cue `27.99` (`Δ −8.26 [−16.36, −0.82]`), Exit `63.18`.
  - `ridegate`: Exit+Cue `33.64` (`Δ −16.08 [−27.93, −5.67]`), Exit `39.15` (`Δ −24.03 [−46.29, −5.22]`).
  - `ref_full_gated`: Exit+Cue `31.00` (`Δ −18.72 [−31.10, −7.38]`), Exit `33.87` (`Δ −29.31 [−52.34, −9.67]`).
  - **`hybrid_sec_mix`**: Exit+Cue **`25.52`** (`Δ −24.20 [−34.85, −13.92]`), Exit **`23.05`** (med `14.1`, `@16 = 50.0%`, `Δ −40.13 [−61.85, −18.86]`), Cue `27.99`.
- **Takeaway:** A single high-mid-rate mix (n=14) gives huge apparent exit gains for any aggressive mid-track exit picker (`ref_full_gated`, `ridegate`, `hybrid_sec_mix`), whereas across 101 mixes / 25 DJs (n=843), none of those style-free exit pickers beat `default` on exit with a CI excluding zero because DJ pacing (21%–100% mid-track rate) is unobservable without earlier-mix context. By contrast, **cue placement (`cueonly_gated` / `hybrid_sec_cue`) wins consistently across both 843-pair CV and the 14-pair fresh mix with zero late-exit damage.**

Diagnostic PNG: `docs/picker_cv_1125_followup.png`.

## 6. Pinned 33-Pair Render Evaluation (`PROTRANS_SRC2=/workspace/mixes/src2_pin_n1121`, `HARD_FALLBACK=0`)
Completed 2026-11-25 02:59 AM ET (`picker-followup-pinned-1125`, `rc=0`). Output: `protrans/replica/picker_1125_followup_pinned.json`.
Note: Both `official_v1` and `official_v2-place8c` are **0–100 similarity scores (higher is better)**.

| Arm | Applied (`picker_style_gated`) | `v1` Train / Test (All) | `Δv1` vs `base` [95% CI] | `v2` Train / Test (All) | `Δv2` vs `base` [95% CI] | `v2` place `(entry/gone/swap)` | Audio MAE `b_entry` / `a_exit` |
|---|---:|---:|---:|---:|---:|---:|---:|
| `base` (`default`) | 0/33 | **32.40 / 34.07** (33.01) | 0.00 | **34.09 / 33.53** (33.89) | 0.00 | 26.4 / 26.3 / 27.2 | **20.3** (n=32) / 54.0 (n=20) |
| `cueonly_gated` | 23/33 (7 abst, 3 `!in_cs`) | 28.85 / 29.41 (29.05) | **−3.96 [−7.20, −0.90]** | 29.31 / 29.84 (29.51) | **−4.38 [−8.00, −0.63]** | 21.3 / 25.2 / 22.4 | 31.6 (n=32) / 55.1 (n=19) |
| `hybrid_sec_cue` | 22/33 (9 abst, 2 `!in_cs`) | 29.88 / 32.51 (30.84) | −2.17 [−5.39, +0.89] | 29.87 / 32.60 (30.86) | −3.02 [−7.06, +1.24] | 21.2 / 25.6 / 21.0 | 31.9 (n=32) / 62.7 (n=20) |
| `hybrid_sec_mix` | 20/33 (2 abst, 11 `!in_cs`) | 30.81 / 33.35 (31.73) | −1.28 [−3.91, +1.47] | 31.12 / 32.83 (31.74) | −2.14 [−5.34, +0.95] | 21.4 / **27.6** / 24.0 | 33.0 (n=32) / **32.6** (n=23) |

`base` reproduces the pinned v1 baseline (`32.40 / 34.07`) and v2 baseline (`34.09 / 33.53`) identically.

### Reconciling CV Bar-Error Gains vs Pinned Render Similarity Losses
Why did every picker variant **lose** on `v1`/`v2` similarity on the 33 pinned pairs despite improving mean bar MAE on the 843-pair CV?
1. **Dev-set KushSessions cue skew + ungated cue overwrite (`tau = -1e9`):**
   - On `KushSessions` (`n=406`, 48% of dev, median `pro_in = 47.5` bars), `default` cue error is `29.72` (`@16 = 27.3%`) and `cueonly_gated` improves it to `21.73` (`@16 = 56.4%`).
   - On **non-KushSessions DJs (`n=437`, median `pro_in = 31.9`)**, `default` cue `@16` is already **`57.4%`** (mean `25.32`), and `cueonly_gated` *drops* `cue@16` to **`41.9%`** (`−15.5 pts`!) because inner CV selected `tau = -1e9` (0 cue abstention), shifting fast intros (`0/8/16`) out to `32–48` bars.
   - The 33 pinned pairs (`Hybrid Minds UKF`, `Joe Syntax Hospital`, `Netsky Hospital`, `Maduk Liquicity`, `Pola & Bryson`, `Wilkinson`) are all fast-cue non-KushSessions pairs where `base` already gets `audio_b_entry_MAE = 20.3` bars; `cueonly_gated` / `hybrid_sec_cue` degrade `b_entry_MAE` to `31.6–33.0` bars, hurting `place_entry` (`26.4 -> 21.3`), `place_swap` (`27.2 -> 21.0–24.0`), `v1 stem_curves` (`40.1 -> 32.7–36.3`), and `v1 deck_curves` (`30.6 -> 25.1–28.4`).
2. **Exit placement vs cue placement (`hybrid_sec_mix`):**
   - `hybrid_sec_mix` is the **only** arm that improved `place_exit` (`26.3 -> 27.6`) and `v1 outgoing_cut` (`20.6 -> 22.0`), slashing pinned `audio_a_exit_MAE` from `54.0 -> 32.6` bars (`ukf__19` jumped `v1 +22.55 / v2 +18.82`, `netsky__06` `v2 +13.76`, `ukf__12` `v2 +6.35`).
   - It still trailed `base` overall (`v1 −1.28`, `v2 −2.14`) because (a) its ungated KushSessions-skewed cue model dragged `entry`/`swap`/`stem_curves` down, and (b) **11/31** mapped early-exit windows fell back to `nat_short` because those windows were not in `recreate.py`'s candidate set `cs`.

## 7. Recommendation on Nightly Picker Arm
- **Do NOT promote `cueonly_gated`, `hybrid_sec_cue`, or `hybrid_sec_mix` over `default` as a replacement yet.** Keep `default` (`rules.json`) untouched as the production baseline; on the 33 pinned pairs `cueonly_gated` significantly regresses both `v1` (`−3.96 [−7.20, −0.90]`) and `v2` (`−4.38 [−8.00, −0.63]`).
- **Keep `cueonly_gated` / `hybrid_sec_cue` / `hybrid_sec_mix` strictly as diagnostic/experimental shadow arms** (with `hybrid_sec_cue` preferred over `cueonly_gated` for cue-only research because section features halved the non-KushSessions `cue@16` drop and improved pinned `v1`/`v2` by `+1.79/+1.35` over `cueonly_gated`).
- **Next fix required before promoting any picker arm:**
  1. **Reweight/stratify training across DJs** (cap KushSessions weight or balance by DJ/style) and **enforce a real cue gate (`tau > 0`, or only override when default `ic` clashes with Track B density/intro length)** so fast `0/8/16` cues are preserved.
  2. **Inject mapped `picker_window` `[ib, ic]` into `recreate.py`'s candidate pool `cs`** (when rhythmically valid) instead of dropping 35% of early-exit predictions (`11/31` in `hybrid_sec_mix`) via `win_not_in_cs`.
  3. **Select picker hyperparameters against `v2`/audio-placement proxy or stratified DJ-balanced loss**, not raw KushSessions-dominated bar MAE.

## 8. DJ-Balanced Cue + Positive Gate (`tau > 0`) + Candidate Injection (`PICKER_INJECT_CS=1`)
Added 2026-11-25 03:25 AM ET (`picker-djbal-cv-1125` `rc=0`, `picker-djbal-pinned-1125` `rc=0`).
Three fixes implemented in `protrans/replica/picker_1125_followup.py`, `protrans/recreate.py`, and `src2/mix_simple.py` (opt-in via `PICKER_INJECT_CS=1`; `rules.json` and default paths untouched):
1. **DJ-balanced cue training (`dj_pair_weights`, `cap=20`):** KushSessions (`n=406`) capped to weight `20` (~7.5% of total weight instead of 48.2%), matching 20-pair DJs.
2. **Strictly positive cue gate (`TAUS_POS`, `tau > 0`) tuned on DJ-balanced inner CV:** Selected `tau = 0.25` (abstain rate `78.8%` on the 33 pinned pairs; `cue_moved = 0.300` on CV vs `0.679–0.789` previously), keeping fast `0/8/16` cues unless confident.
3. **`PICKER_INJECT_CS=1` in both `recreate.py` AND `src2/mix_simple.py` (`pair_cands`):** Eliminated silent drops/rejections of off-grid (`8`-bar exit / `8`-bar cue) early-exit windows (`0` failed renders out of 33).

### 8a. Leave-One-DJ-Out CV (`picker_1125_djbal_cv.json`, n=843; Non-KushSessions n=437)
| Slice & Arm | Exit+Cue Mean | Exit Mean (Med) | Exit @8 / @16 | Cue Mean (Med) | Cue @8 / @16 | `cue_moved` / `exit_moved` |
|---|---:|---:|---:|---:|---:|---:|
| **All (n=843) `default`** | 37.13 | 46.82 (34.1) | 16.5% / 35.2% | 27.44 (18.7) | 18.6% / 42.9% | 0% / 0% |
| **All (n=843) `djbal_cue_defexit`** | 35.94 | 46.82 (34.1) | 16.5% / 35.2% | **25.07** (17.0) | **20.9%** / **46.9%** | 30.0% / 0% |
| **All (n=843) `djbal_cue_sec_mix`** | **34.94** | **44.81** (39.7) | 15.9% / 31.0% | **25.07** (17.0) | **20.9%** / **46.9%** | 30.0% / 49.3% |
| **Non-Kush (n=437) `default`** | 39.86 | 54.41 (55.6) | 10.1% / 24.7% | 25.32 (15.0) | 23.6% / **57.4%** | 0% / 0% |
| **Non-Kush (n=437) `hybrid_sec_cue`** | 38.93 | 54.41 (55.6) | 10.1% / 24.7% | 23.45 (17.0) | 25.9% / 45.5% (−11.9%) | 78.5% / 0% |
| **Non-Kush (n=437) `djbal_cue_defexit`** | 39.18 | 54.41 (55.6) | 10.1% / 24.7% | **23.96** (15.0) | **24.3%** / 55.8% (−1.6%) | 35.2% / 0% |
| **Non-Kush (n=437) `djbal_cue_sec_mix`** | **35.57** | **47.19** (47.4) | **14.2%** / **28.1%** | **23.96** (15.0) | **24.3%** / 55.8% (−1.6%) | 35.2% / 37.8% |

- On **All 843** (mix-clustered 95% CI vs `default`):
  - `djbal_cue_defexit`: ΔEC **−1.19 [−1.73, −0.65]**, ΔCue **−2.37 [−3.46, −1.29]**, `cue@16` **+3.9% [+0.7%, +7.2%]**.
  - `djbal_cue_sec_mix`: ΔEC −2.19 [−4.47, +0.34] (pair CI **−2.19 [−3.91, −0.51]**), ΔExit −2.01 [−6.63, +3.21].
- On **Non-KushSessions (`n=437`)**:
  - `djbal_cue_defexit` eliminated `hybrid_sec_cue`'s `cue@16` collapse (−11.9% → −1.6%, mix-CI `[−6.1%, +2.7%]`).
  - `djbal_cue_sec_mix` beat `default` on Exit+Cue: mix-CI **−4.29 [−7.59, −0.60]** (vs `majority`: −0.75 [−3.72, +2.41]).

### 8b. Pinned 33-Pair Similarity (`picker_1125_djbal_pinned.json`, Higher Is Better)
| Arm | Applied | `v1` Train / Test (All) | `Δv1` vs `base` [Pair CI] / [Mix CI] | `v2` Train / Test (All) | `Δv2` vs `base` [Pair CI] / [Mix CI] | `v2` `(entry/gone/swap)` | Audio `b_entry`/`a_exit` MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| `base` (`default`) | 0/33 | 32.40 / **34.07** (33.01) | 0.00 | 34.09 / **33.53** (33.89) | 0.00 | 26.4 / 26.3 / 27.2 | **20.3** / 54.0 |
| `djbal_cue_defexit` | 7/33 | 33.47 / 32.51 (33.12) | +0.11 [−1.32, +1.66] / [−2.05, +2.32] | 34.10 / 32.43 (33.49) | −0.39 [−2.34, +1.52] / [−2.17, +2.52] | 23.1 / 27.1 / 24.2 | 26.0 / 59.8 |
| `djbal_cue_sec_mix` | 25/33 | **36.81** / 31.56 (**34.90**) | **+1.90** [−1.41, +5.22] / [−3.27, +5.11] | **38.84** / 31.10 (**36.03**) | **+2.14** [−1.86, +6.09] / [−3.26, +5.54] | **28.9 / 29.7 / 31.6** | 28.8 / **23.0** |

### 8c. Verdict
- **Did it beat `base` on pinned similarity?**
  - `djbal_cue_defexit` fixed the old cue-only `−4` pt similarity regression (`−3.96 / −4.38` → `+0.11 / −0.39`), ending essentially tied with `base`.
  - `djbal_cue_sec_mix` **beat `base` on overall point estimates (`+1.90 v1`, `+2.14 v2`, and all three `v2` placement sub-scores)** and cut `audio_a_exit_MAE` by 31 bars (`54.0 → 23.0`), driven by large gains on the 21 train pairs (`+4.41 v1 / +4.75 v2`) — **but regressed on the 12 test pairs (`−2.51 v1 / −2.43 v2`)** due to `margin = 5` over-exiting (`wilkinson_boomtown2026__33`, `pola_bryson_puzzlewood__04`), and both 95% CIs still cross zero (`[−1.41, +5.22]` / `[−1.86, +6.09]`).
- **Worth adding as a nightly arm?**
  - **Yes, as a diagnostic/shadow nightly arm (`djbal_cue_sec_mix` with `PICKER_INJECT_CS=1`), NOT as a `rules.json` replacement yet.** It is strictly better than `cueonly_gated` / `hybrid_sec_cue` / `hybrid_sec_mix` on pinned `v1`/`v2` (`+5.86 v1 / +6.52 v2` over `cueonly_gated`) and shows real upside when paired with early exits, while its `train` vs `test` split (`+4.75` vs `−2.43` on `v2`) confirms the exit gate margin (`margin=5`) still needs tightening (`margin >= 10–15` or `pro_late` guardrail) before promotion.

## 9. Learned Late-Safe Exit Gate (`djbal_cue_asym_mix`), Pinned Eval, Held-Out Diagnosis & Shadow Config
Added 2026-11-25 04:05 AM ET (`picker-asym-cv-1125` `rc=0`, `picker-asym-pinned-1125` `rc=0`).

### 9a. Diagnosis on 843 Dev Pairs & Learned Gate Design (`inner_asym_mix_gate`)
- Under unweighted expected MAE, `djbal_cue_sec_mix`'s inner CV picked `margin = 5.0`, which moved 49.3% of exits (61.8% on KushSessions) and inflated `pro_late` exit error from `11.40` (`default`) to `42.30` bars (`39.37` on Non-KushSessions).
- Fix in `protrans/replica/picker_1125_followup.py` (`inner_asym_mix_gate`): tune `(min_na, margin)` over `min_na in [0, 190, 200]` and `margin in [5..50, 1e9]` by inner leave-one-DJ-out CV on the **843 dev pairs only** (never touching the 33 pinned pairs), optimizing asymmetric regret `|ex - pro_out| + 1.0 * max(0, |ex - pro_out| - |dex - pro_out|)`.
- Full-843-dev fit selected `cue_djbal = {cfg: 0, tau: 0.25}` and `asym_exit = {min_na: 200, margin: 50.0}` (`13/33` windows active on pinned; `20/33` abstain to `base`), emitted to `protrans/replica/picker_djbal_sec_mix_windows.json` (`picker_1125_asym_protrans_maps.json`).

### 9b. 25-Fold Leave-One-DJ-Out CV (`picker_1125_asym_cv.json`, n=843)
| Slice & Arm | Exit+Cue Mean | Exit Mean (Med) | Exit @8 / @16 | `pro_mid` / `pro_late` Exit | Cue Mean (@16) | `exit_moved` |
|---|---:|---:|---:|---:|---:|---:|
| **All (n=843) `default`** | 37.13 | 46.82 (34.1) | 16.5% / 35.2% | 77.03 / 11.40 | 27.44 (42.9%) | 0.0% |
| **All (n=843) `majority`** | 36.22 | 47.37 (38.4) | 7.1% / 14.7% | 57.64 / 35.33 | 25.06 (35.7%) | 96.8% |
| **All (n=843) `djbal_cue_sec_mix`** | 34.94 | 44.81 (39.7) | 15.9% / 31.0% | 46.95 / 42.30 | 25.07 (46.9%) | 49.3% |
| **All (n=843) `djbal_cue_asym_mix`** | **34.65** | **44.24** (32.5) | **16.7%** / 34.9% | 61.88 / **23.55** | **25.07** (**46.9%**) | 18.9% |
| **Non-Kush (n=437) `default`** | 39.86 | 54.41 (55.6) | 10.1% / 24.7% | 76.47 / 12.61 | 25.32 (**57.4%**) | 0.0% |
| **Non-Kush (n=437) `djbal_cue_asym_mix`** | **36.08** | **48.20** (47.8) | **12.8%** / **28.6%** | 64.18 / **17.95** | **23.96** (55.8%) | 12.6% |

- **All 843 (mix-clustered 95% CI):** `djbal_cue_asym_mix` beats `default` on `exit_cue` (**−2.47 [−3.79, −1.10]**) and `cue` (**−2.37 [−3.46, −1.29]**), and beats `majority` on `exit_cue` (**−1.56 [−3.20, −0.006]**), `exit` (**−3.13 [−6.24, −0.25]**), `exit@16` (**+20.2%**), and `cue@16` (**+11.2%**).
- **Non-KushSessions (`n=437`, mix-clustered 95% CI vs `default`):** `exit_cue` **−3.78 [−5.76, −1.91]**, `exit` **−6.20 [−9.77, −2.96]**, `exit@16` **+3.9% [+1.5%, +6.4%]**; `pro_late` error cut from `39.37` down to `17.95`.

### 9c. Pinned 33-Pair Evaluation (`picker_1125_asym_pinned.json`, Higher Is Better)
| Arm | Applied | `v1` Train / Test (All) | `Δv1` All / Train / Test [Pair CI] | `v2` Train / Test (All) | `Δv2` All / Train / Test [Pair CI] | Audio `b_entry`/`a_exit` MAE |
|---|---:|---:|---:|---:|---:|---:|
| `base` (`default`) | 0/33 | 32.40 / **34.07** (33.01) | 0.00 | 34.09 / **33.53** (33.89) | 0.00 | **25.5** / 43.2 |
| `djbal_cue_defexit` | 7/33 | 33.47 / 32.51 (33.12) | +0.11 [−1.32, +1.66] | 34.10 / 32.43 (33.49) | −0.39 [−2.34, +1.52] | 26.0 / 59.8 |
| `djbal_cue_sec_mix` | 25/33 | **36.81** / 31.56 (**34.90**) | +1.90 [−1.41, +5.22] | **38.84** / 31.10 (**36.03**) | +2.14 [−1.86, +6.09] | 28.8 / **23.0** |
| `djbal_cue_asym_mix` | 13/33 | 34.44 / 31.66 (33.43) | +0.42 [−1.79, +2.46] / +2.03 / **−2.41 [−6.85, +0.53]** | 35.73 / 30.98 (34.00) | +0.12 [−3.20, +3.04] / +1.64 / **−2.54 [−9.05, +1.63]** | 25.9 / 37.4 |

- Mix-clustered 95% CIs for `djbal_cue_asym_mix` vs `base`: `v1` all **+0.42 [−2.89, +2.50]**, train **+2.03 [+0.98, +3.74]**, test **−2.41 [−4.82, 0.00]**; `v2` all **+0.12 [−3.08, +2.75]**, train **+1.64 [+0.11, +4.12]**, test **−2.54 [−5.09, 0.00]**.

### 9d. Per-Pair Diagnosis of Held-Out (`test`, n=12) Losses
The late-ride guard (`min_na=200, margin=50`) did **not** fix held-out test similarity (`−2.41 v1`, `−2.54 v2` vs `base`):
1. **8/12 held-out pairs abstained to `base` (`Δ = 0.00`):** `maduk__02, 03, 05`, `netsky__23`, `pola_bryson__00, 02, 04`, `wilkinson__33`. That skipped `wilkinson__33` (`−8.09 v2` in `sec_mix`) and `pola__04` (`−14.72 v1 / −14.62 v2` in `sec_mix`), but also skipped `pola__00` (`+9.68 / +6.99`) and `pola__02` (`+4.14 / +11.02`).
2. **2/4 active held-out regressions were cue moves, not exit moves:**
   - `netsky_hospital_classics__02` (`na=185 < 200`, exit stayed `176`, **only cue moved `0 → 48`**): `v1 43.75 → 32.29 (−11.46)`, `v2 36.91 → 31.06 (−5.85)` (`audio_ent_b 4.9 → 148.0` vs `pro 20.4`; `bass_swap 41.38 → 9.75`).
   - `netsky_hospital_classics__15` (`cue 0 → 16` alone in `djbal_cue_defexit`): `v1 40.90 → 33.66 (−7.24)`, `v2 50.22 → 42.91 (−7.31)`.
3. **Static `min_na=200` still over-exited `netsky_hospital_classics__15` (`na=246`):**
   - `netsky__15` has two drops (`[[48,127],[159,235]]`) and the pro DJ rode **both drops** to `203.4` (`42.6` bars left), so `base` (`240/0/16`, `v1=40.90, v2=50.22`) was already optimal. Because `na=246 >= 200`, `asym` moved exit `240 → 144` (plus cue `0 → 16`), crashing to `v1=19.56 (−21.34)`, `v2=16.09 (−34.13)` (`deck_curves 47.34 → 10.92`, `bass_swap 62.07 → 9.52`). Meanwhile `netsky__06` (`320 → 160`, `+2.46 v1 / +9.80 v2`) and `netsky__17` (`256 → 160`, `+1.45 v1 / −0.36 v2`) gained or held even.
4. **Exit picker ignores blend compatibility at the candidate exit bar:** On `pola_bryson_puzzlewood__04` (`sec_mix`), moving `224 → 152` actually moved `audio_gone_a` closer to pro (`146.0` vs `134.6`, `gone 20.0 → 37.3`), yet `v1` dropped `34.12 → 19.40 (−14.72)` because `beat_align` collapsed (`46.67 → 15.35`) at bar `152`.

### 9e. Tomorrow Night Shadow Config Update
- Updated `protrans/replica/nightly_candidates.json` for tomorrow night (after `n1125_run.py` had already loaded `CANDS_FILE` at `03:29 AM ET`, leaving `nightly-n1125` undisturbed): replaced obsolete `picker_style_gated` in slot 4 with shadow arm `djbal_cue_sec_mix` (`shadow: true, promotion: false, flags_off_by_default: true`, `delta: {"PICKER_STYLE_GATED": 1, "PICKER_STYLE_GATED_MAP": "replica/picker_djbal_sec_mix_windows.json", "PICKER_INJECT_CS": 1}`). `adopt_to_defaults` remains `false` and `protrans/rules.json` was not modified.
