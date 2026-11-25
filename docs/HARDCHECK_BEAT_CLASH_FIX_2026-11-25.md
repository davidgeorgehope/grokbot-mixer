# Hard-Check `beat_clash` Bug Fix (2026-11-25)

## Root Cause

In `protrans/replica/hardcheck.py`, `check()` evaluates post-render alignment on the final rendered decks by calling `finephase.measure_blend_lag(M['decks'], M['trans'], 0)`.

When `BLEND_LOCK` is enabled (the baseline default in `protrans/rules.json`), incoming `decks[i + 1]` carries a non-zero `blend_lock_ms` on every blend that was locked. Inside `src2/finephase.py:measure_blend_lag`:

- Because `decks[i + 1].get('blend_lock_ms')` is truthy, `prefer_zero` is set to `True`.
- `loud_lag_ms(..., prefer_zero=True)` calls `robust_lag(..., prefer_zero=True)` instead of `confident_lag()`.
- Unlike `confident_lag()` (which returns `None` when any bar in the cluster has `|lag| < LOCK_MIN_MS` = `15 ms`), `robust_lag(..., prefer_zero=True)` returns the median of the nearest-to-zero cluster — typically sub-15 ms residual lags such as `-0.73 ms`, `+1.45 ms`, `-2.90 ms`, or `-8.71 ms`.

However, `protrans/replica/hardcheck.py` line 53 checked:

```python
clash = bool(hb.get('fail')) or (lag is not None)
```

That flagged **any** non-`None` residual lag as `beat_clash=True`, ignoring `finephase.LOCK_MIN_MS` (`15.0 ms`) — its own documented threshold for an already-locked blend. Every blend where `BLEND_LOCK` had successfully reduced residual lag below `15 ms` and `robust_lag` happened to report a numeric sub-15 ms residual was falsely failed as a `beat_clash`.

## Fix

In `protrans/replica/hardcheck.py`:

```python
clash = bool(hb.get('fail')) or (lag is not None and abs(lag) > FP.LOCK_MIN_MS)
```

- `FP.LOCK_MIN_MS` (`15.0 ms`) and `hardcheck_calib.json` are kept completely untouched.
- `residual_lag_ms` continues to be recorded verbatim in the `check()` output dictionary.
- Genuine clashes (`|lag| > 15.0 ms` such as `+163.99 ms` on `hybrid_minds_ukf__28` or `+166.89 ms` on `joe_syntax_hospital__13`, or `halfbeat_fail=True` such as `maduk_liquicity_lunar2025__05`) continue to be flagged.

## Unit Tests

Added `protrans/tests/test_hardcheck_beat_clash.py` (17 cases):
- Verifies `FP.LOCK_MIN_MS == 15.0` untouched.
- Verifies sub-15 ms residual lags (`-0.73`, `+1.45`, `-2.90`, `-8.71`, `0.0`, `±15.0` ms) with `halfbeat_fail=False` return `beat_clash=False` and `hard_fail=False`, preserving `residual_lag_ms`.
- Verifies `|lag| > 15.0` ms (`±15.1`, `45.0`, `-120.0`, `163.99`, `166.89` ms) and `halfbeat_fail=True` still set `beat_clash=True` and `hard_fail=True`.

## Before / After Hard-Fail Counts on `n1125` (Pinned 33 Pairs)

Exact counts across `n1125` (`HARD_FALLBACK=0`, `src2_pin_n1121`) and `render-n1125`:

| Arm | `n` | Before (`hard_fail` / `beat_clash`) | After (`hard_fail` / `beat_clash`) | False `beat_clash` rows cleared (`residual_lag_ms`) | Remaining `beat_clash` rows |
| --- | ---: | :---: | :---: | --- | --- |
| `base` (`n1125`) | 33 | 8 / 4 | **6 / 2** | `joe_syntax_hospital__11` (`-0.73 ms`), `__12` (`+1.45 ms`) | `hybrid_minds_ukf__28` (`+163.99 ms`), `maduk_liquicity_lunar2025__05` (`halfbeat_fail`) |
| `epg_strict` (`n1125`) | 33 | 7 / 3 | **6 / 2** | `joe_syntax_hospital__11` (`-0.73 ms`) | `ukf__28`, `maduk__05` |
| `epg_drop` (`n1125`) | 33 | 6 / 3 | **4 / 1** | `joe_syntax_hospital__11` (`-0.73 ms`), `__12` (`+1.45 ms`) | `maduk__05` |
| `epg_stack` (`n1125`) | 33 | 5 / 2 | **4 / 1** | `joe_syntax_hospital__11` (`-0.73 ms`) | `maduk__05` |
| `picker_style_gated` (`n1125`) | 33 | 10 / 2 | **9 / 1** | `joe_syntax_hospital__11` (`-0.73 ms`) | `maduk__05` |
| `struct_mid_tight` (`n1125`) | 33 | 8 / 3 | **6 / 1** | `joe_syntax_hospital__11` (`-0.73 ms`), `__12` (`+1.45 ms`) | `maduk__05` |
| `thin_dropcue` (`n1125`) | 33 | 8 / 4 | **6 / 2** | `joe_syntax_hospital__11` (`-0.73 ms`), `__12` (`-2.90 ms`) | `joe_syntax_hospital__13` (`+166.89 ms`), `maduk__05` |
| `cueonly_gated` (`render-n1125`) | 26 | 5 / 1 | **4 / 0** | `joe_syntax_hospital__12` (`-8.71 ms`) | *(none)* |

Non-clash hard fails (`bass_hole` and `pumping`) are completely unchanged.
