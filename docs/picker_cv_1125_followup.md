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
