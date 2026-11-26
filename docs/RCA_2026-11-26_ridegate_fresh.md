# RCA 2026-11-26: ridegate fresh-mix validation (ukf_drum_bass_wVp_VlkWqxI)

Job `ridegate-fresh-validate` finished `rc=0` at 11:21 America/New_York. 18/18 pairs rendered. Default new hard fails **0**. RIDEGATE and RIDEGATE+LINGER_GUARD each picked up **two new hard fails** (`__09` beat_clash, `__23` pumping). Official agreement: ridegate **17/18**, linger arm **16/18**. `rules.json` was not edited. The locked holdout was not opened.

Window format is `['n', exit_bar, None, incoming_start, X]`. Every window here is a **16-bar** blend (22.07 s at 174 BPM, `bar_sec=1.37931`). “48” in a default cue is the incoming start bar, not the blend length. Official hard-check thresholds: `pump_p95=4.54`, `lows_dip_p95=45.34`, clash if `|residual_lag_ms| > 15` or `halfbeat_fail`.

All official-check numbers below were re-measured from the rendered decks (`hardcheck.check`, `blend_diag.crop_decks` / `vdip`), not just the ckpt flag.

## 1. Pairs 09, 23, and 11

### `__09` Logistics – Waveforms (`9aN8jt9l8S0`) → Ownglow – Back To You (`DaFDQDy7en0`)

- **Fails `beat_clash`**. `residual_lag_ms = −158.19` (143.19 ms over the 15 ms lock floor). `halfbeat_fail=False`. Pump 3.18 dB (under 4.54 by 1.36). Lows dip 36.9 (under 45.34).
- Ridegate official / applied: `['n', 168, None, 32, 16]`, `p_leave=0.659`, linger_bars=0. Blend **A 152–168**, **B 32–48**. In this 2-track render (A starts at bar 0) that is **209.7–231.7 s**; the cropped clip (8-bar pre-roll) shows the blend at **11.03–33.10 s**.
- Pro cue in this same mix (corpus_v2): outgoing **99.38** (section “build”, between drop1 end 96 and drop2 112), incoming **43.68** (corpus label “breakdown”; `S.get` intro until 64), overlap **40.4 bars**. Pro mix time on the same A timeline: **137.1 s**. We exit **53.6 bars / 73.9 s later** and cue **10.7 bars earlier**.
- What’s in the tracks: A is entirely in the **outro** (`outro_start=144`, `music_end=165`, drops end at 144). The last three blend bars are past `music_end`; A full-band falls −20.9 → −73.1 dB. B is still in the **intro** (`intro_end=64`, drop1=64) — 32 bars before the drop.
- Why the ride causes it: `blend_lock` measured a consistent ~−155 to −165 ms offset on bars 154–159 (`lag_ms=−158.2`) and **refused to apply it** (`why: "near half a beat; left to halfbeat"`). A half-beat at 174 BPM is 172.4 ms; this is 0.46 beat, 14.2 ms shy of a flip. Halfbeat then abstained (`< 4 drum-on-drum bars`, `bars=0`, `lag_ms=0`), so the residual stayed. Default `['n', 160, None, 48, 16]` (A 144–160, still outro but ending before `music_end`; B 48–64, 16 bars from the drop) had **8 drum-on-drum bars**, lag 0, and passed.
- Linger arm applied the **same official window** and hard-failed the same way (linger_bars=0, so the guard correctly did not fire).

### `__23` Dexcell ft. LaMeduza – Freefall (`0oXTQGdoTk4`) → Matrix & Futurebound ft. Zelah – Got You There (`fhqyyDdLfTs`)

- **Fails `pumping`**. Re-measured V-dip **4.82 dB** at track bar **118** (clip 19.31 s, sides −25.4 / −24.6, trough −30.2). Official rounded pump **4.8 dB**, **+0.26 / +0.28** over `pump_p95=4.54`. No clash, lows dip 38.3 (under 45.34).
- Ridegate official / applied: `['n', 128, None, 8, 16]`, `p_leave=0.755`, linger_bars=0. Blend **A 112–128**, **B 8–24**. Mix time **154.5–176.6 s** (clip 11.03–33.10 s).
- Pro cue: outgoing **111.57** (end of drop1 48–112 — “drop”), incoming **23.70** (intro/build, `drop1=40`), overlap **19.75 bars**. Pro mix time **153.9 s**. Our **exit is only 1.4 bars / 0.6 s later**, but we cue **14.7 bars earlier** (bar 9 vs 23.7) and use a 16-bar blend instead of ~20.
- What’s in the tracks (`S.get`): the entire 16 bars of A are the **breakdown** (`breakdown=112`, drop2=144; drop1 ended at 112). B is entirely **early intro** (`intro_end=40`). A already starts quiet (−23.9 dB) and collapses to −37.5 at the dip bar; B starts at −43.6 and only reaches −23 by the end, still 16 bars short of its drop.
- Why the ride causes it: the pack exits **into the outgoing breakdown** with a thin, too-early incoming intro. The sum has a V at bar 118 because A’s drop has already ended and B has not yet arrived. Default `['n', 208, None, 24, 16]` sits in A drop2 / outro_start 192 and B 24–40 (still intro, but 16 bars later, closer to the drop) and pumps only **2.93 dB**.
- Linger arm used the same official window and also hard-failed (structural linger_bars=0).

### `__11` Dawn Wall – I Should Have Been There (`8cXagpI3yv0`) → K Motionz – Dusk (`30_nSrjTPRQ`)

- **No official hard fail.** Pump 3.25 dB (under 4.54). The fault is **linger**: ridegate official `['n', 192, None, 32, 16]`, `p_leave=0.539`, **linger_bars=8 > pro p95 5.4**.
- Blend **A 176–192**, **B 32–48**. Mix time **242.8–264.8 s** (clip 11.03–33.10 s).
- Pro cue: outgoing **95.93** (in A drop 32–96, “drop”), incoming **31.81** (“build”), overlap **28.3 bars**. Pro mix time **132.3 s**. We exit **81.1 bars / 111.9 s later** (end of drop2 / `outro_start=176`) and cue only **1.2 bars later**.
- What’s in the tracks: A 176–192 is still **in drop2** (drops `128–192`). B 32–48 is a **breakdown** (`S.get` breakdown=32, drop2=48, so all 16 bars; built-row snapshot has breakdown=40, so only the last **8** bars — that is the count the guard used). Outgoing full-band starts at drop level (−15.9 dB) and fades to silence by 190; incoming sits in a breakdown around −24 to −32 dB for the second half. See the diagnostic plot: [RCA_2026-11-26_ridegate_fresh_pair11.png](RCA_2026-11-26_ridegate_fresh_pair11.png).
- Why the ride causes it: the pack keeps A in a drop and cues B at bar 32, which walks into (and, on snapshot sections, spends 8 bars in) the incoming breakdown. That is the same shape as the listener’s `outgoing_drums_linger_under_incoming_breakdown` note.

**LINGER_GUARD did block pair 11.** The linger arm abstained and rendered the default `['n', 192, None, 0, 16]` (`fam=nat_short`, linger_bars=0, pump 1.2, hard_fail false). Cue 0–16 is B’s intro (`intro_end=16`), so there is no breakdown landing.

## 2. Why agreement is 16/18, and the ukf__40 linger sensor

Agreement dropped to 16/18 on the linger arm for **two** reasons, only one of which is linger:

| pair | what happened |
|---|---|
| `__11` | Guard **correctly disagreed** with the official lingering window (8 > 5.4) and rendered default. |
| `__16` | Official **abstained** (`official_abstain=True`, `p_leave=0.711`). `official_win` is listed as the unused candidate `['n', 176, None, 32, 16]`, but all three arms rendered default `['n', 176, None, 16, 16]`, which itself hard-fails (pump 5.6 + clash). The compare script treats rendered default ≠ `official_win` as a disagreement even when the pack abstained. This is not a second linger miss. |

### `hybrid_minds_ukf__40` (today’s daily, 10:24 America/New_York)

the listener’s note (`protrans/log.jsonl`, fault `outgoing_drums_linger_under_incoming_breakdown`): “Ours lets the old track beats run at low volume over the incoming breakdown for a long time; the pro does not.”

Our render (`n26l15`): `['n', 176, None, 32, 16]`, blend A **160–176**, B **32–48**.

**Structural `linger_bars=0`**, so the current guard would not have blocked it.

- Outgoing (`S.get`): drops `64–160` and `176–272`, **breakdown=160**, drop2=176. The whole blend is the **inter-drop breakdown**, not a drop. Built-row snapshot even **omits `breakdown`** (`None`, drops `63–157` / `175–268`, drop2=175) — `in_breakdown` used to return false whenever the field was missing.
- Incoming: **intro** (`intro_end=drop1=48`). Bars 32–48 are not a tagged breakdown. The mix *sounds* like a breakdown because A has left the drop and B has not yet dropped (bass stays around −45 to −72 dB until B’s drop at mix bar 176).

Source-track drum/perc (high-pass 200 Hz), drop1 median **−17.1 dB**:

| A bars | vs drop | notes |
|---|---|---|
| 160–172 (14 of 16 blend bars) | **−0.7 to −6.6 dB** | “breakdown” still has drop-level beats |
| 173–174 | −13 / −35 dB | brief hole |
| 175–176 | back to ~−1 dB | drop2 |

The **pro** enters at outgoing **144.6** (still in the drop), incoming **17.3**, overlap **23**. By the time A hits the breakdown (~bar 160), a 23-bar equal-power fade is already ~**−6 dB**, then falls off. Our fade *starts* at the breakdown boundary, so those near-normal source drums stay audible (then “low volume”) under B’s pre-drop intro for the whole 16 bars.

## 3. Sensor redefinition, calibration, and what was implemented

A **section-only** rule “block if the fade sits in the outgoing breakdown under a non-drop incoming” is not safe: 13/33 pro windows do this (p95=21 bars, max=27), and several **passing** official fresh rides do it for all 16 bars (`__01` pump 1.1, `__03` 2.6, `__26` 0.5, `__30` 3.7).

A **predicted pump** from source energy × equal-power fade does not reliably match the rendered V-dip (`__23` pred 3.66 vs actual 4.8 — would miss; `__12` pred 4.35 vs actual 2.9 — near a false fail). A **predicted lag** from naive source-bar crops was not confident on any pair (the real −158 ms lock is measured on beat-aligned rendered decks).

The sensor that does match the listener’s fault, and that can be calibrated to the pro p95:

> `drum_linger_bars`: count of blend bars where the **outgoing is in a breakdown**, the **incoming is not in a drop**, and the **predicted-faded** outgoing drum/perc band (high-pass 200 Hz, equal-power `cos(π/2 · (j+0.5)/X)`) stays **within X dB of the outgoing drop median**.

`in_breakdown` now **infers** `[end of first drop, drop2)` when the snapshot omits `breakdown`. Structural `linger_bars` p95 on the 33 protrans pro windows is **unchanged** (5.4; hist 0×30, 3, 9, 16; 3/33 = 9.1% of pros have any structural linger). Official default and ridegate on protrans remain 0/33 structural.

Drum calibration, 33/33 protrans sources, **X = 8 dB**, threshold = pro p95 of the bar count:

| window | n>0 | p95 | max | ukf__40 |
|---|---|---|---|---|
| Pro official pro windows | 12/33 (36%) | **8.80** | 17 | **4** (under) |
| Our official ridegate on protrans | 10/33 | 10.0 | 11 | **10** (over) |
| Our daily `['n', 176, None, 32, 16]` | — | — | — | **10 > 8.80 — would block** |
| Fresh `__23` official, `S.get` sections | — | — | — | drum=**9 > 8.80** |
| Fresh `__23` official, built-row sections (live path) | — | — | — | drum=**8**, just **under** 8.80 |
| Fresh `__09` | — | — | — | drum=**0** (outro, not a breakdown) |
| Fresh `__11` official | — | — | — | structural **8 > 5.4** (already blocked); drum=0 (outgoing still in a drop) |

Implemented behind **`LINGER_GUARD` (still off by default, still not written to `rules.json`)**: block if `linger_bars > 5.4` **or** `drum_linger_bars > 8.80`. No pair pins. 95 tests green.

Dry-run of `maybe_apply` with the guard on (same path a re-render would take):

- `__11`: still blocked (structural 8, built-row sections).
- `__23`: **not** blocked on the live path (built-row drum=8 ≤ 8.80). The pumping official window would still be applied; I did not lower the threshold to catch it, because that would be an uncalibrated cut. A full re-render of 09/23 would still hard-fail on both arms.
- `__09`: not blocked (drum=0). The clash needs a lock preview on **beat-aligned rendered decks**, which a naive source crop does not reproduce.
- `hybrid_minds_ukf__40` our window: **would now be blocked** (10 > 8.80); the pro window (4) would not.

Collateral on the linger arm only: some official pack windows that do not official-hard-fail have drum_linger > 8.80 (fresh `__03`/`__30` measure 12 on `S.get`; several protrans official ridegate windows measure 10–11). The ridegate arm (flag off) is unchanged.

## 4. Artifacts

- Diagnostic PNG (pair 11, both decks’ equal-power gain, drum/perc, and full-band): `/workspace/mixes/docs/RCA_2026-11-26_ridegate_fresh_pair11.png`
- This note: `/workspace/mixes/docs/RCA_2026-11-26_ridegate_fresh.md`
- Cal: `/workspace/mixes/protrans/replica/linger_guard_cal.json` (structural + drum fields). Per-pair drum details: `replica/nightly_1126_work/drum_linger_cal.json`.
- Ride-preview cal: `protrans/replica/ride_preview_cal.json`. Dry-run and exit lag: `replica/nightly_1126_work/ride_preview_dryrun.json`, `exit_lag_1126.json`. Safe re-render ckpt: `replica/gate_ckpt/n1126f_ride_safe.jsonl`.


## 5. Ride safety preview (11:44–12:05 America/New_York)

General fixes only. No pair pins. `rules.json` and defaults were not written. New behaviour is behind `RIDEGATE_LOCK`, `RIDEGATE_PUMP`, and `RIDEGATE_EE`, all off by default. Cal: `protrans/replica/ride_preview_cal.json`. Locked holdout was not opened.

### 5.1 Lock preview (`RIDEGATE_LOCK`) — catches `__09`

A ride is rejected (fall back to the default window) when a **confident** mid-blend lag is un-lockable by finephase (`|lag| > LOCK_MAX_MS=150`) **and** drum-on-drum bars `< 4` (halfbeat’s own floor; among 19/33 protrans pro windows with `dd>=4`, p05=9.8, but using 10 as a hard floor would veto passing rides with 5–9 overlap bars). Missing audio/st never blocks.

The preview slices each source on its `st` grid, applies the actual `fade_long.xlong` gains, and runs `finephase.loud_lag_ms` / `confident_lag` on the mid-shelf (both faded decks `> -35` dB and both faders `>= 0.45`). That mid-shelf is required: official `measure_blend_lag` on `__09` used bars 154–159; a `|d|<6` source-grid mask drops those bars (A is 6–10 dB louder on the sources, `n_loud` too small), and using every audible bar dilutes the cluster so `confident_lag` is None. `robust_lag` of a messy set invented half-beat residuals on passing official rides `__06` / `__11` / `__14` (official residual `None`) and was not used.

Dry-run of all 18 official ride windows with the mid-shelf rule: **only `__09` is blocked by lock** (`lag=−158.2` ms, `dd=0`). Official `blend_lock` on that render was `lag_ms=−158.2`, `applied=False`, `why: "near half a beat; left to halfbeat"`, halfbeat abstained (`dd=0`). No passing official ride is blocked. `__07` has a mid-shelf lag of 149.5 ms (still `<= 150`, so finephase would apply it) and `dd=14`. `__00` / `__12` are near half-beat on some bars but not a confident cluster, or have `dd>=4`.

### 5.2 Pump prediction (`RIDEGATE_PUMP`) — catches `__23`

Source × equal-power fade predicted **3.66 dB** on `__23` vs official rendered **4.82 dB** (`+0.28` over `pump_p95=4.54`). The renderer uses `FADE=long` (`fade_long.xlong`: fast rise, mid shelf ~0.45–0.50, then exit) plus bass/high swap, not a linear equal-power ramp. Re-predicting with the actual/xlong xfader rises to **~4.18**, still under 4.54, and would **false-fail** passing `__12` (pred 4.62 vs actual 2.9). Predicted V-dip is therefore **not** a hard gate.

The flag instead rejects a measurable **both-thin** condition: outgoing in a breakdown, incoming not in a drop, and both source `st` `bar['all']` at least `T=6` dB below their drop medians, for more than the pro p95 count **10.80** (33 protrans official pro windows; 19 at 0, then 1–7, 10×2, 12, 17). Fresh official at T=6: `__23=14` (catch), `__30=9`, `__03=8`, no other official over 10.80 — no fresh official false positives.

### 5.3 Exit lag vs the pro, and `RIDEGATE_EE`

Exit is first outgoing blend bar `e−X+1`, vs the pro’s `outgoing_bar` (fresh corpus cue) / `out_bar_at_entry` (protrans).

| cohort | arm | n | mean | median | p25 | p75 | n late (>8) |
|---|---|---:|---:|---:|---:|---:|---:|
| fresh | default | 18 | +66.9 | +81.2 | +49.3 | +97.9 | 15 |
| fresh | ridegate | 18 | +26.9 | +4.1 | +1.1 | +61.3 | 8 |
| fresh | ridegate+LOCK+PUMP | 18 | +30.9 | +19.3 | +1.1 | +76.8 | 9 |
| protrans | default | 33 | +66.0 | +58.7 | +32.7 | +107.7 | 30 |
| protrans | ridegate | 33 | +31.8 | +32.0 | −4.3 | +71.7 | 21 |

The “53–81 bars later” figure is a **subset of late rides**, not the average. Ridegate is already earlier than default on both cohorts (fresh median +4.1 vs +81.2; only 6/33 protrans rides later than their default). Late fresh rides include `__09 +53.6`, `__11 +81.1`, also `__00 +63.9`, `__06 +49.4`, `__12 +106.2`, `__16 +129.5` (official abstain / default), `__19 +81.5`.

`ride_pick` did **not** revert any of the 18 fresh official exits (`jr==je`); those late exits are already the exit ranker’s top pick, so un-reverting `je` cannot fix them. `ee_r7` is a pinned 5-id list and is not uniformly earlier (e.g. `ukf__40` ee_r7 exit 256 vs pro 144.6, and it hard-fails pump). It is not a drop-in earlier-exit for fresh.

`RIDEGATE_EE` (off by default) therefore only keeps `je` when `ride_pick` would revert a mid/earlier exit to the default, the `je` start is earlier, and `drum_linger` does not exceed its threshold. On this pack that path fires on 2/33 protrans built rows and would cut lag `hybrid_minds_ukf__19` +66.2→+18.2 and `maduk_liquicity_lunar2025__05` +114.7→+18.7. It does not change any fresh pair. Not enabled for the re-render below.

### 5.4 Re-render of affected fresh pairs

Dry-run `maybe_apply` with `RIDEGATE=1,RIDEGATE_LOCK=1,RIDEGATE_PUMP=1` on all 18: **only `__09` (lock) and `__23` (pump)** fall back to default. Those two were re-rendered as `n1126f_ride_safe` (unique `eval_gate` tags; `ONLY` those ids). `corpus-v2` was left running.

| pair | official ride | safe window | fam | hard | residual / pump |
|---|---|---|---|---|---|
| `__09` | `['n', 168, None, 32, 16]` beat_clash −158.19 | `['n', 160, None, 48, 16]` (default) | nat_short | **ok** | residual `None`, pump 1.3 |
| `__23` | `['n', 128, None, 8, 16]` pumping 4.82 | `['n', 208, None, 24, 16]` (default) | nat_short | **ok** | pump **2.9** (under 4.54) |

**New hard fails** on the safe arm vs default: **0** (the two previous new fails are gone). `__16` still hard-fails under both default and ride (official abstain; same default window; not affected).

**Window agreement** with the official built-row ride: was **17/18** (miss = `__16` abstain labelling). After LOCK+PUMP: **15/18** (also `__09` and `__23`, intentionally rejected). The other 15 official rides are unchanged.

**Exit lag** on the safe arm: fresh mean **+30.9** / median **+19.3** (ridegate was +26.9 / +4.1). `__09` lag improves slightly (53.6→45.6, still late). `__23` lag **regresses** from +1.4 (the pumping ride, almost on the pro exit) to the default **+81.4** — the cost of refusing the thin breakdown blend.

pytest: `protrans/tests/` **98 passed**. Dry-run: `replica/nightly_1126_work/ride_preview_dryrun.json`. Exit-lag table: `replica/nightly_1126_work/exit_lag_1126.json`. Safe ckpt: `replica/gate_ckpt/n1126f_ride_safe.jsonl`.
