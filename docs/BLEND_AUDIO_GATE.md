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

Validation, 2026-11-24 (code as committed 10:05 AM ET; files eval/blend_gate_validation_mix10.json,
eval/blend_gate_validation_holdout.json, eval/blend_gate_crosscheck.json).

| Mix | Blends | Known faults | Caught | Flagged but labelled clean |
|---|---|---|---|---|
| Mix 10 r6 (r6c faults) | 23 | 6 | 6 | 0 |
| Mix 10 r5 | 23 | 1 (18:45 N1 step) | 1 | 1 (blend 13 tail) |
| Mix 09 r3 | 22 | 2 | 2 | 2 |
| Mix 09 r4 | 23 | 1 | 1 | 2 |
| Mix 09 r5 | 22 | 2 | 2 | 2 |
| Mix 09 r5b | 22 | 0 | 0 | 2 |
| Mix 08 r11c (delivered) | 25 | 0 | 0 | 1 |
| Total | 160 | 12 | 12 | 10 |

The Mix 10 r5 14:24 dip is a solo breakdown hole, not a blend fault: breakdown_holes.py marks it (E1-deep at 14:23).

All 10 "labelled clean" flags come from two track-level faults:

- SqzxwPEa-DI > l4XZ-wqc4vQ, 1 bar of both vocals (V1, test_no_vocal_clash): 4 mixes.
- n1dOiesZS1g as the outgoing deck, a 6.01 dB one-bar tail step against the 6 dB limit
  (test_outgoing_audio_tail_never_drops_abruptly): 6 mixes.

blend_gate_crosscheck.py runs the same shared check on each FULL mix meta with today's code and features. It fails on all 10
(10/10), so the gate agrees with the release test and the labels are stale. Mix 08 r11c blend 19 was checked further:

- the clip and the full mix give identical per-bar values (bar 13 step -6.01 dB), so no window-edge effect;
- the 11/10 engine gives the same value as today's, and the tail test only gained an unrelated fader constant since then;
- the delivered MP3 matches today's clip bar by bar (constant offset, shape within 0.05 dB).

The most likely cause is that the stem file st/n1dOiesZS1g.wav, re-decoded 11/20, moved a borderline -5.99 to -6.01. This is not
proven, because the old stem is not kept. No threshold was changed.

Timing: median 44.6 s per blend (p90 96 s) on Mix 10, n=46; holdout median 48 s (p90 169 s) at box load 15-31; render median 6.5 s.

Wiring status: gated.py check/search/repair and render_gated.sh are done and tested (25 unit tests). plan_search.py and repair.py
are unedited, and gated.py drives them through SEESAW_BANFILE and ctx.dry/ctx.badwin. A first search smoke (10:35 AM ET) tried no
plans: every plan in the old r6 pool held a gate-proven bad window and that run allowed no re-search. pool_skips now reports the
blocking windows, and the next run re-searches once with the bans.


## Wiring it in (next step)

Wire it in only after the current `render-mix10-r6e` job ends. Both edits are small, and both are gated by `blend_gate.enabled()`.

1. `plan_search.py`:
   - In `bad_windows()`, union `blend_gate.proven_bad_windows()` into `out` and add `BADC` entries with code `'BAG'`. Add `'BAG'` to `HARDCODES` so that a proven-bad window is a hard ban.
   - In the verify loop, after a dry is `ALL OK`, call `blend_gate.gate_dry_plan(P, gain)`. On a failure, record the failing windows (they land in the cache, so the next `bad_windows()` sees them) and continue to the next pool plan instead of accepting this one.
   - Gate the pool plans in batches. Each plan costs about 23 × 46 s on one core, and repeated windows hit the cache.
2. `repair.py`: wrap `ctx.dry` so that a try counts as passing only when the dry is `all_ok` and `gate_dry_plan` passes. Only the changed blends render, because the rest are cached. Union `proven_bad_windows()` into `ctx.badwin` at start. This turns repair's blind dry sign-off into a real audio check for bass gaps, swap dips, N1, alignment, and tails. The extra cost is about one minute per try.
3. Render wrappers: run `breakdown_holes.exposures(dry_meta)` before rendering, and refuse a plan with an `E1-deep` exposure. Use `gain_step.choose_gain_full(raw, 9.0)` between `mix_simple` and the QA run, and run guardrails and pytest once, on the chosen master.
4. Promotion: keep the flag off by default until one full mix built with the gate passes render QA on the first try.
