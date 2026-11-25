# Half-Beat Grid Correction Investigation (`HALFBEAT_LOCK`, 2026-11-25)

## Problem Statement

After `BLEND_LOCK` resolves in-range lags (`15 <= |lag| <= 150 ms`), two transitions in the `n1125` pinned-33 evaluation showed residual lags just outside `LOCK_MAX_MS = 150 ms` near half a beat (`~172.4 ms` at 174 BPM):

1. `hybrid_minds_ukf__28` (`n1125` baseline): `measure_blend_lag = +163.99 ms`
2. `joe_syntax_hospital__13` (`n1125` `thin_dropcue` arm): `measure_blend_lag = +166.89 ms`
3. Plus `maduk_liquicity_lunar2025__05` (`n1125` baseline): `halfbeat_fail = True` (`lag_ms = None`, `HB.blend_check` flagged `4` late bars at `dphase_ms = -172.4 ms`, `lag_ms = -174.15 ms`).

## Root-Cause Measurements (`kick+snare` vs `kick+mid`)

Evaluating 64-bin bar-folded drum envelopes (`halfbeat.drum_envs`: `30-150 Hz` kick + `1500-5000 Hz` snare) over the loud overlap bars measured by `measure_blend_lag` revealed two completely different physical causes:

- **`hybrid_minds_ukf__28` (`bnRTUL2jnk0 -> Op886B0sd4Q`, loud bars `226..232`) — FALSE half-beat lag from mid-band synths:**
  - `kick+snare` fold correlation at `0 ms` is **`r0 = 0.766`**, vs **`r_half = 0.237`** at `+172.4 ms`!
  - Both decks already have strong `kick+snare` lock at `beat_phase = 0.000` (`str_a = 7.12`, `str_b = 9.61`).
  - Why did `measure_blend_lag` return `+164.0 ms`? Because `blend_diag.bar_offsets` correlates `30-150 Hz + 150-1500 Hz` (without the `1500-5000 Hz` snare band), where mid-band synths weakly peaked at `+172 ms`.
  - Shifting `ukf__28` by `+172.4 ms` lowers `measure_blend_lag` to `-13.06 ms` (fooling `bar_offsets`), **but destroys the true `0.766` kick+snare alignment**.

- **`joe_syntax_hospital__13` (`u6cggHmZEAs -> SqzxwPEa-DI`, `THIN_DROPCUE=1`, loud bars `242..248`) — GENUINE half-beat offset:**
  - `u6cggHmZEAs` outro (`str_a = 0.87`, `phase_a = -0.062`) has weak/off-beat percussion against `SqzxwPEa-DI` (`phase_b = 0.000`, `str_b = 5.02`).
  - On loud overlap bars, `kick+snare` fold correlation improves at `+172.4 ms` (`r0 = 0.197 -> r_half = 0.213`; across `240..248`, `0.067 -> 0.267`), and `kick+mid` jumps `-0.102 -> +0.392`.
  - Re-phasing incoming `SqzxwPEa-DI` by `+172.4 ms` drops `measure_blend_lag` from **`+166.89 ms` to `0.0 ms`**, and `hardcheck.check` moves from `beat_clash=True` (`hard_fail=True`) to `beat_clash=False` (`hard_fail=False`, `lows_dip_db=5.9`, `pump_db=0.8`).

- **`maduk_liquicity_lunar2025__05` (`cG7cRDcPY3k -> EpHrodtTiK0`)**:
  - Across the full overlap (`224..240`), `kick+snare` fold correlation at `0 ms` is `r0 = 0.399` vs `-0.167` / `0.085` at `-172.4 ms` (`str_a = 8.54`, `str_b = 0.88`). Only the final 4 bars triggered `HB.blend_check`, so a full-blend half-beat shift is not confirmed (`r_half < r0`).

## Principled Implementation (`HALFBEAT_LOCK`, Off by Default)

Implemented in `src2/finephase.py` (`hb_lock_flag_on()`, `HALFBEAT_LOCK=0` by default; wired in `protrans/recreate.py`):

1. Triggers only when `BLEND_LOCK=1` and `HALFBEAT_LOCK=1` and `150 < |lag| <= BEAT_MS/2 + 25` (or `halfbeat.fail` with `lag` in that range).
2. Calls `_halfbeat_ks_confirm(decks, trans, i, half_ms, bars=report.get('bars'))`:
   - Rejects any shift when `0 ms` already has strong `kick+snare` alignment (`r0 >= 0.50`) or when `r_half < r0`.
   - Confirms only when `(r0 < 0.50 and r_half >= max(0.20, r0 + 0.05))` OR `(r0 < 0.30 and min(str_a, str_b) < 1.5 and r_half >= r0)`.
3. Applies `half_ms = round(copysign(BEAT_MS / 2, lag), 1)`, re-measures `measure_blend_lag`, reverts if `lag` does not resolve below `LOCK_MAX_MS`, and applies residual fine lock if `15 <= |lag2| <= 150 ms`.

Unit tests added in `src/tests/test_halfbeat_lock.py` (verifying off-by-default, genuine half-beat fix `< 15 ms`, and rejection of `ukf__28`-style `kick+snare`-locked mid-band spoofs).

## Pinned 33 Evaluation (`src2_pin_n1121`, `HARD_FALLBACK=0`)

Using the fixed `hardcheck.py` threshold rule:

| Variant | `v1` train / test | `v2` train / test | `hard_fail` (33) | `beat_clash` | Notes |
| --- | :---: | :---: | :---: | :---: | --- |
| `n1125_base` (`HALFBEAT_LOCK=0`) | 32.40 / 34.07 | 34.09 / 33.53 | 6 | 2 | `ukf__28` (`+163.99 ms`), `maduk__05` (`halfbeat_fail`) |
| `hbl1125_base` (`HALFBEAT_LOCK=1`) | **32.40 / 34.07** | **34.09 / 33.53** | **6** | **2** | `ukf__28` cleanly skipped (`r0=0.766` vs `rh=0.237`) |
| `n1125_thin` (`HALFBEAT_LOCK=0`) | 30.39 / 35.39 | 31.91 / 35.11 | 6 | 2 | `joe_syntax_hospital__13` (`+166.89 ms`), `maduk__05` |
| `hbl1125_thin` (`HALFBEAT_LOCK=1`) | **30.46 / 35.39** | **31.98 / 35.11** | **5** | **1** | `js13`: lag **`+166.89 -> 0.0 ms`**, `v1` `22.08 -> 23.67`, `v2` `19.29 -> 20.58`, hard pass |
