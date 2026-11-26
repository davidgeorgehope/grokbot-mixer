# n1127 shadow arm: ee_r7 + pro fade (ex35)

Frozen spec, off by default. Do not put this on tonight's n1126 card, and do not swap any n1126 arm for it.

## What it is

ee_r7 already leaves the old track earlier (the listener preferred it over the long "safe" outro on pola02). This arm keeps that, and also uses the learned pro fade so the *amount* of fade over time follows what the pro DJs do, instead of our older equal-power shape.

A bug found on 2026-11-26: the pro fade used to ignore the early exit and stretch the old track back out to the end of the window (pola02 incoming_vanish 6.9 dB, over the 5.24 limit). The fade now stops where the early exit already decided (`PRO_FADE_RESPECT_EXIT=1`, the default). After that fix, pola02 passed every hard check. A blind A/B of ee_r7+pro fade vs ee_r7 alone was sent to the listener; hold the answer key until he answers.

## Flags (all off unless this shadow arm is on)

```
EARLY_EXIT=1
PICKER_STYLE_GATED=1
PICKER_STYLE_GATED_MAP=replica/picker_early_exit_r7_windows.json
PICKER_INJECT_CS=1
TAIL_EXIT=6
PRO_FADE=1
PRO_FADE_ENTRY_DB=-8.5
PRO_FADE_SHELF_DB=-10.0
PRO_FADE_EXIT_SLOPE=3.5
PRO_FADE_HIGH_OFS=7.0
PRO_FADE_BASS_CUT_DB=-24.0
PRO_FADE_RESPECT_EXIT=1
```

`TAIL_EXIT=6` is already the default in rules.json; it is listed so the arm stays frozen if that default ever changes. Do not write rules.json. Do not change defaults. Promotion still needs two consecutive night wins plus a fresh-mix pass.

## Why ex35, not fit2

On the 27 dev blends *without* early exit (r5 grid, 2026-11-26 12:37 AM ET):

- ex35 (exit slope 3.5) was the closest fade to the pros in every band (bass MAE 9.31 vs fit2 9.47 vs base 10.39; all-band 2.70 vs 2.95).
- Same hard fails (4) and pumps (3) as fit2; better than base (5 hard fails, 4 pumps).
- Its one extra L1 flag is two quiet basses overlapping far below normal level; the audible version (l1a) is 0. The 3.0 dB L1 threshold was not loosened.

## What must be true before this takes a nightly slot

1. the listener's ear on the pola02 blind A/B (already sent; A is the pro fade, B is ee_r7 only — do not tell him until he answers).
2. The r6 grid (`fit-pro-fade-6`, arms `r6_ee_base`, `r6_ee_fit2`, `r6_ee_ex35`) must finish: same 27 pairs, but this time with early exit + ee_r7 flags + tail exit + respect-exit, so we see the path we would actually ship. Prefer ex35 if it is still the closest fade and is not worse on hard checks (beat, hole, pump, vanish) than r6_ee_base. Do not loosen tests. If fit2 is honestly better on that grid, freeze fit2 instead and update this spec.
3. A full official pinned-33 score of the frozen flags vs the n1121 base and vs ee_r7 alone (not part of the r6 job).

If any of those fail, keep the arm off and do not add it to a card.

## Slot rule for n1127

Six-arm cap stays. This would be a *shadow* arm (promotion=false, adopt_to_defaults=false, flags_off_by_default=true). Only add it to a future card if a shadow slot is free. Do not bump a promotion arm (epg_strict / epg_drop / epg_stack) or a still-needed n1126 shadow to make room. Do not touch the n1126 candidates list.

## Judge, if it is ever run

Same as other shadow arms: held-out mean must improve, hard-fail count must not get worse (pairs the default already fails are not counted against it), and the listener's ear still counts if we send a blend. Not an auto-adopt keep.
