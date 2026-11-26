# Should L1 only count bass overlap you can actually hear?

Short review, 26 Nov 2026. **The check was not changed.** This is a recommendation and the numbers behind it.

## What L1 is, in plain language

L1 asks: when both tracks are playing, how much *extra* bass (under 120 Hz) is there compared to just the louder track's bass? If the two basses are at the same level, they add about 3 dB, so the line is "fail above 3.0 dB."

The catch: the check runs on every bar of the blend, even when both basses are so quiet you cannot hear them. `l1a` is the same number, but only on bars whose combined bass is within 12 dB of the track's normal (body) bass — the overlap you can actually hear.

L1 is **not** one of the official hard checks (those are beat clash, bass hole, pump, and the new-track-vanishes check). It is a diagnostic we have been using to score fade variants, and it also appears in the older quality suite (`eval_graphcut.py`), which already ignores very quiet bars (combined bass must be within 25 dB of the outgoing track's body).

## What the fade grid showed (our renders)

On the 27 dev blends (r4/r5, no early exit), **every L1 fail had l1a = 0**. None of them would have failed an audible-level check:

| blend | arm | L1 (dB) | l1a | bass at the fail bar | vs normal bass |
|---|---|---|---|---|---|
| liquiddnbftw__10 | base / fit2 / ex35 | 4.21 / 3.7 / 3.7 | 0.0 | about −67 and −70 dB | a breakdown; overall level still ~−29 dB, but the *bass* is 40+ dB down |
| liquiddnbftw__16 | fit2 / ex35 | 3.0 | 0.01 | residual old bass on a bass-light intro, ~−37 dB | ~20 dB down |
| sirenity__56 | fit2 / ex35 | 3.22 | 0.01 | −47.0 vs −47.8 dB | body bass ~−20 dB, so ~27 dB down |
| kushsessions__04 | ex35 only | 3.06 | 0.0 | quiet overlap | inaudible |

ex35 was the closest fade to the pros, but those inaudible flags made it look worse than it is (4 L1 fails vs base 1). That is the test being untrustworthy, not a reason to loosen 3.0 by hand.

## What the pro mixes do (33 pinned clips, 30 with a long enough overlap)

Measured on the pro recordings themselves, with each track's bass attributed by the same method we use elsewhere (NNLS), and with the same L1 maths as the fade fitter. No 4 dB clip. Script and raw rows: `pro_l1_p95.py`, `pro_l1_p95.json`.

"p95" means 95% of those pro overlaps stay at or under this number.

| measure | p50 | p95 | max | how many over 3.0 dB |
|---|---|---|---|---|
| L1, every bar (ungated) | 1.80 | **3.17** | 4.36 | 4 / 30 |
| l1a (only audible bars, within 12 dB of body) | 0.58 | **2.98** | 4.36 | 2 / 30 |
| official-style floor (within 25 dB of outgoing body) | 1.41 | **2.98** | 4.36 | 2 / 30 (the same two) |

The four pro clips over 3.0 dB ungated:

- **hybrid_minds_ukf__08**: 4.36 dB, *audible* (both basses around −18 / −20 dB, combined −13.5, near full body). A real-sounding moment of two basses together, 1.36 dB over the line.
- **maduk_liquicity_lunar2025__02**: 3.03 dB, audible, only a hair over 3.0 (basses −24.9 and −25.5).
- **hybrid_minds_ukf__19**: 3.19 dB at about −53 dB, 39 dB below body. **l1a 1.98** — same inaudible pattern as our false flags.
- **maduk_liquicity_lunar2025__05**: 3.14 dB at about −57 dB, 33 dB below body. **l1a 0.39**.

A fifth number I did *not* use: comparing the *mixed recording's* bass to the two attributed tracks. That p95 is 9 dB and flags 21 of 30 clips, because the recording has leftover low end (room, PA, rumble) that is not in either source. That is not the same quantity as L1 on our isolated decks, so it is not a fair p95.

## Recommendation

**Later, gate the fade-fitter L1 on audible overlap (use l1a, or the official "within 25 dB of body" floor). Keep the 3.0 dB line. Do not change anything now.**

Reasons:

1. The 3.0 dB line is already the pro p95 of the *audible* metric (2.98 dB). Switching to l1a is a gating change, not a loosening of the threshold. Raising 3.0 to the ungated pro p95 (3.17) would be the wrong fix: it would clear a few quiet flags (3.06, 3.14, 3.22) and still miss liquiddnbftw__10 (3.7), while pretending quiet equal-bass is a problem.
2. The official quality-suite L1 already has an audible floor. The fade fitter should not be stricter in a way that punishes silence.
3. Two pro clips still go over 3.0 dB even on l1a (4.36 and 3.03). If we ever promoted L1 into a hard check, we would need to decide whether hybrid_minds__08 is a true "pros also double the bass sometimes" case (then a hard check at 3.0 would be slightly tighter than the pros) or leave L1 as a diagnostic. That decision is for a later chunk, and only after a listen, not a threshold tweak.
4. Do not write this into `hardcheck.py` or `rules.json` until the r6 grid and the pola02 listen are in, and only then as a dated, tested change.

Until then, keep reporting both L1 and l1a, and do not reject a fade variant solely for an L1 fail whose l1a is 0.
