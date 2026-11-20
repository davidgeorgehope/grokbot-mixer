# SLOWPAIR_COND (2026-11-20)

**`protrans/rules.json` is unchanged.** `SLOWPAIR_COND` stays off by default. This is a prototype on top of the exit-only flag: Case A fires only on the drop-leave / hard-outro shape.

## What was tried
- Exit-only (`SLOWPAIR_EXIT=1`) lost on held-out (32.28 vs 34.07) because the two Netsky Case A moves dropped 33.35 → 20.39 and 40.9 → 32.43. The one gain was `joe_syntax_hospital__12` (Ghetto Blaster → Seconds To Midnight) 32.29 → 42.85, the pair with the hard outro slowdown flagged on listening, and it also cleared a parent hard fail.
- The condition, using the slow-pair feature flags: apply the exit-only pick only when the outgoing track ends with a hard outro *after* the last drop (`sp_out_hard_outro` and not `sp_out_hard_indrop`) **and** the incoming track has a drop that can land in the blend. In-drop slowdowns (the two Netsky losses) stay on the default.
- A naive "pro left in a drop" label is also reported: all three Case A pairs have the pro leaving in a drop, so that oracle would repeat the exit-only loss. It is not used at runtime.
- Numbers come from the already-scored default and exit-only checkpoints; no new renders. Official hard-fail is HC_A / HC_B v2 from the exit-only eval. Mix-grouped bootstrap CIs (4000, seed 20261119). Leave-one-DJ-out of the 33-pair scores is below.

## Results

| variant | held-out | train | n | n_fail | pairs changed | held-out CI (arm − default) |
|---|---:|---:|---:|---:|---:|---|
| bfb1120_base (current rules) | **34.07** | **32.4** | 33 | 0 | 0 | — |
| spex1120_def (exit-only, all Case A) | 32.28 | 32.91 | 33 | 0 | 3 | — |
| spex1120_cond (drop-leave shape) | 34.07 | 32.91 | 33 | 0 | 1 | 0.0 [0.0, 0.0] incl0=True |

Decision: **match_or_beat_floor**. Condition fired on 1 of 3 Case A pairs (1 picks moved).

Hard-fail (HC_A / HC_B v2): default 8 → cond 7 (HC_A 7→6, HC_B 6→6). New fails: none. Fixed: ['joe_syntax_hospital__12']. Leave-one-DJ-out fail-delta range: [-0.05, 0.0].

Moved pairs (default → cond, score default → arm):

- `joe_syntax_hospital__12` (train): `['n', 224, None, 48, 16]` → `['la', 176, 160, 16, 16]` , 32.29 → 42.85 (Cyantific - Ghetto Blaster -> S.P.Y - Seconds To Midnight) — hard outro after the last drop, not in-drop; incoming drop can land in the blend

Case A pairs the condition left on the default:

- `netsky_hospital_classics__17` (test): `['n', 256, None, 32, 16]` stayed, score 33.35 (Logistics - Together -> Apex - Just One Second (London Elektricity Remix)) — in-drop slowdown (not a pure hard outro after the last drop)
- `netsky_hospital_classics__15` (test): `['n', 240, None, 0, 16]` stayed, score 40.9 (Netsky - Memory Lane -> Netsky - The Whistle Song) — in-drop slowdown (not a pure hard outro after the last drop)

## Leave-one-DJ-out

| held-out DJ | rest train | rest held-out | rest mean Δ | held DJ mean Δ | moved on rest |
|---|---:|---:|---:|---:|---:|
| Hybrid Minds | 33.76 | 34.07 | 0.528 | 0.0 | 1 |
| Joe Syntax | 32.38 | 34.07 | 0.0 | 1.32 | 0 |
| Maduk | 32.91 | 35.35 | 0.352 | 0.0 | 1 |
| Netsky | 32.91 | 33.54 | 0.377 | 0.0 | 1 |
| Pola & Bryson | 32.91 | 32.77 | 0.352 | 0.0 | 1 |
| Wilkinson | 32.91 | 34.42 | 0.33 | 0.0 | 1 |

## Code

- `src2/slowpair.py` — `looks_like_drop_leave()`, `SLOWPAIR_COND=1` (off by default)
- `protrans/recreate.py` — exports `SLOWPAIR_COND` when a trial sets it
- `protrans/eval_slowpair_cond.py`
- `src/tests/test_slowpair.py`
- Flag off by default; do not put `SLOWPAIR_COND` in `rules.json`

