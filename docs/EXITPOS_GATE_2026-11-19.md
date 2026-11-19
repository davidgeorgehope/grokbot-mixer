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
