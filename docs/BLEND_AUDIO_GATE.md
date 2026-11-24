# Blend audio gate (`BLEND_AUDIO_GATE`)

Fix 1 from `docs/RCA_mix10_failure_loop.md`, plus the two fix-2 pieces: the master-gain auto-step and breakdown-hole marking.
Status: built and validated on 2026-11-24 ET. It is behind a flag (default off) and not yet wired into `plan_search.py` or `repair.py`.

## What it does

`src2/blend_gate.py` proves a blend on its own rendered audio:

1. It takes the plan's meta (`mix_simple --dry`, or a render meta) and crops every deck to `[start - 16, end + 8)` bars. The clip is clamped so that no third deck sounds: it starts after the previous blend ends and stops before the next one starts.
2. It renders each crop with `engine.render_deck` (same `full_map`, automation, nudges, and locks), sums them, and masters the clip with `src/master.sh` at the planned gain.
3. It writes the clip as a small build under `src2/blend_gate_clips/` and runs the release checks on it, imported rather than copied:
   - `src/guardrails.py` (every fail-check, per-deck renders included), as a subprocess.
   - The blend-local `src/build_qa` tests, called in-process with the same functions and thresholds. The list is `TESTS` in the module.
4. It caches the verdict in `src2/blend_gate_cache/<key>.json`. The key hashes the check code (`CODE` list), the feature content of the clip's tracks (`st/<id>.json` bytes plus the audio file's size and mtime), the clip window (shifted deck crops, automation, and the transition), the gain, and the nudges for those tracks.

Checks that only make sense for a whole mix are still run, but they are reported as `mix_level` and do not fail the blend:

- `P1` and `test_true_peak` go to the master gain (`src2/gain_step.py`).
- `E4` compares against the whole-mix median.
- `test_global_grid_no_drift` allows 3% of the whole mix's grid points off. On a one-minute clip that means 0 of about 7 points.
- `test_every_deck_on_its_planned_bar` measures each deck at its middle, which is its solo body in a full mix but sits inside the blend on a clip.

No threshold was changed.

## Commands

```
cd src2 && . ../mix10/env10.sh && export NUDGE=nudge08_r9c.json
python3 blend_gate.py --meta mix10_r6_meta.json --gain 9.0 --jobs 2 --json out.json     # every blend of a rendered plan
python3 blend_gate.py --plan plan_mix10_r6c.json --gain 9.0 --jobs 3                     # dry first, then every blend
python3 breakdown_holes.py mix10_r5_meta.json                                            # solo deep-breakdown exposure
python3 gain_step.py mix10_r6_raw.wav --start 9.0                                        # first gain whose full master is <= -1.0 dBTP
python3 blend_gate_validate.py 2 [holdout]                                               # validation runs (eval/blend_gate_validation_*.json)
```

Tests: `src/tests/test_blend_gate.py`, `test_breakdown_holes.py`, and `test_gain_step.py`.

## Validation results

VALIDATION_PLACEHOLDER

## Wiring it in (next step)

Wire it in only after the current `render-mix10-r6e` job ends. Both edits are small, and both are gated by `blend_gate.enabled()`.

1. `plan_search.py`:
   - In `bad_windows()`, union `blend_gate.proven_bad_windows()` into `out` and add `BADC` entries with code `'BAG'`. Add `'BAG'` to `HARDCODES` so that a proven-bad window is a hard ban.
   - In the verify loop, after a dry is `ALL OK`, call `blend_gate.gate_dry_plan(P, gain)`. On a failure, record the failing windows (they land in the cache, so the next `bad_windows()` sees them) and continue to the next pool plan instead of accepting this one.
   - Gate the pool plans in batches. Each plan costs about 23 × 46 s on one core, and repeated windows hit the cache.
2. `repair.py`: wrap `ctx.dry` so that a try counts as passing only when the dry is `all_ok` and `gate_dry_plan` passes. Only the changed blends render, because the rest are cached. Union `proven_bad_windows()` into `ctx.badwin` at start. This turns repair's blind dry sign-off into a real audio check for bass gaps, swap dips, N1, alignment, and tails. The extra cost is about one minute per try.
3. Render wrappers: run `breakdown_holes.exposures(dry_meta)` before rendering, and refuse a plan with an `E1-deep` exposure. Use `gain_step.choose_gain_full(raw, 9.0)` between `mix_simple` and the QA run, and run guardrails and pytest once, on the chosen master.
4. Promotion: keep the flag off by default until one full mix built with the gate passes render QA on the first try.
