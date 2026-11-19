# EXITPOS_GATE (2026-11-19)

EXITPOS v2 (job ep2-1119) lost on held-out: EP 29.28 train / 31.94 test, EPS 30.06 / 30.87, vs floor 32.40 / 34.07.
The three worst misses were cue-only moves that pulled the incoming drop out of (or off the end of) the blend.
The two biggest wins were Pola & Bryson Night Dawns → Wind Rises (also a cue-only move, +13.23) and, under EPS,
Ghetto Blaster → Seconds To Midnight (earlier exit that skips a slowdown outro, +16.49).

## Design

Outro-over-intro stays the safe default (`rules.json` unchanged). `EXITPOS_GATE=1` (research, requires `EXITPOS=1`,
off by default) will take an alternative window only when all of these hold:

1. It exits earlier than the default.
2. The outgoing's last drop has played to its end.
3. The incoming's first drop lands inside the blend.
4. A leave-one-DJ-out logistic (`protrans/replica/halftime/exitpos_gate.py`, fit by `fit_exitpos_gate_1119.py`)
   says the alternative is closer to a good blend than the default (threshold 0.6), **or** the default blend
   starts in / is mostly an outgoing outro or in-drop slowdown (listener: "when the outro is doing something odd").

On the engine's actual EP/EPS windows this would have blocked the three big cue-move losses (pola__00 −27.84,
hybrid_minds__28 −23.77, joe_syntax__11 −22.58) and Wilkinson EPS's later exit (−12.81), kept joe_syntax__01
(+5.76) and the Ghetto Blaster slowdown exit (+16.49), and still allowed netsky__02 (−9.60). It would also have
given back pola__02 (+13.23) and netsky__06 (+4.18), which were cue-only moves that no longer land drop 1.

The logistic alone is weak under leave-one-DJ-out (precision about 0.5 at 0.5). The three hard checks do the
important work; the per-DJ weights are a further veto, with the weird-outro override so Ghetto Blaster is not
lost when Joe Syntax is held out.

Eval job: `epg-1119` (arms EPG / EPGS).

## Why the first `epg-1119` eval matched EP/EPS exactly

`EXITPOS_GATE` *was* on the planner path and the env vars did reach `mix_simple.py`.
The hook only reordered `pair_cands` so the gated window was first. That does not matter:
`DUMP_CANDS` writes each window's engine cost, and `blend_bench.families()` then picks
`min(cost)` per family. Cue-only EXITPOS winners kept their cheaper costs, so detect
and `eval_cohort` both scored the ungated EP/EPS windows (pola__00 −27.84, Wilkinson
EPS −12.81, and the rest). Hook prints went to the child stderr, which `blend_bench.sh()`
discards on success — so the job log had no `EXITPOS_GATE` lines even though the hook ran.

Fix (still flag-only): after the decision, rewrite costs. A taken alt is boosted
(`−10*STRUCTW` on top of its EXITPOS cost); every other window is restored to the
default (outro-bonus) cost. nat_short (16-bar) and nat_long (≥32) are gated
separately so a 32-bar alt cannot be swallowed by `length_pref=16`. Rerun is
`epg2-1119` (new tags; ungated `cs_epg_1119` caches are not reused).

Live decisions for the 33 admitted pairs are in `protrans/replica/epg_decisions_1119.json`.
The "almost only nat_short" pattern is the default's own behaviour (`length_pref=16`
in `rules.json`): 32 of 33 floor windows are already nat_short, and only
`wilkinson_boomtown2026__33` is nat_long. The gate does not change that preference.

## epg2 result and the last-drop tightening (epg3)

`epg2-1119` (cost rewrite live): EPG and EPGS both 33.91 held-out vs the 34.07 floor;
train 31.79 (EPG) / 32.48 (EPGS). Every taken alternative exited *exactly* at last-drop
end, so the blend was the last 16 bars of a still-hot drop and the outro was left
unplayed (median bars left 4 to 13). That is what "ae >= last_drop_end" allowed, and
what EXITPOS then preferred.

Chosen fix, on train only (leave-one-DJ-out, held-out not used to pick the rule):
the last drop must have fully played *before the blend starts* (`exit - X >= last_drop_end`).
A higher model threshold cannot separate train loser hybrid_minds__28 (p=0.8356) from
winner joe_syntax__13 (p=0.8366). A 16-bar cap alone still allows the 16-bar last-drop
cuts. On train, the tighter hard check is predicted to score 33.19 (only
joe_syntax_hospital__12 still moves, 224 to 208, the earlier-outro +16.49 window).
Rerun is `epg3-1119`.

## Registered for the 2026-11-20 1 AM nightly (n1120)

EPG (EXITPOS_GATE strict) is the promotion candidate, so it can start earning two consecutive
wins. The nightly reads `protrans/replica/nightly_candidates.json` (and
`promotion_criteria_1120.json`). Defaults and `rules.json` stay unchanged; a night-1 win is
not an auto-adopt. Fresh mix queued in `fresh_mixes.json` for_night 2026-11-20:
Sirenity `ofcHup56lME` (new DJ, not in dev, not spent).

## epg_drop (shadow arm, 2026-11-19)

A second flagged arm, independent of EXITPOS_GATE. `EXITPOS_DROP=1` (requires `EXITPOS=1`,
off by default, not in `rules.json`) takes an exit right at the end of the last drop
(the epg2 behaviour the listener preferred on netsky_hospital_classics__02, [pt556u]) only when:

1. Incoming drop 1 lands inside the blend.
2. The first 16 bars of the outgoing outro are at least 3 dB quieter (all bands) or 3 dB
   thinner (lows) than the last 16 of the last drop.
3. When pro placement is known, the outro does not carry the blend (fraction of the pro
   outgoing overlap at or after last-drop end is below 0.5). This is the hybrid_minds_ukf__45
   veto (pro fraction 0.58). joe_syntax_hospital__12 (0.84) is also blocked; its +16.49
   earlier-outro window stays with epg_strict.
4. The window is not a known hard fail (cache; unknown is allowed and checked after render).
   hybrid_minds_ukf__08 is blocked this way.

If both EXITPOS_GATE and EXITPOS_DROP are set, the hook runs only the gate, so epg_strict
stays a pure arm. Thresholds were not fitted on held-out. Train check: JS01 allowed, HM45 blocked.

Live 33-pair decisions (`epgdrop_decisions_1119.json`): 8 takes (JS01, netsky__02,
netsky__17, JS13, HM00, HM10, HM28, pola__02) and the three epg2 takes above blocked.
Predicted pro-match from already-scored windows: held-out 33.91 vs the 34.07 floor,
train 32.18 vs 32.40. Both of the listener's ear picks are taken. A pro-match drop alone does
not kill the arm. Hard-fail on the 33, from epbasem vs the taken epg2 windows: 8 to 6
(fixes HM00 and HM28; leaves JS12's default fail for epg_strict). Leave-one-DJ-out of the
pro cache does not change any take that is not itself the motivating veto: without that
DJ's own pro row, energy alone would allow HM45 and JS12. Held-out DJs have no pro-outro
blocks.

epg_strict stays the n1120 promotion candidate. epg_drop is a shadow arm in
`nightly_candidates.json`. Official 105-dev hard-fail and confirmation scores: job
`epgdrop-1119` (webhook via runjob).
