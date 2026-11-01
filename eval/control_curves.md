# How pro liquid DJs ride faders/EQ: reverse-engineered from audio (v0, 2026-11-01)
Code: `src/eval/control_curves.py` (`validate`, `run`, `summarize`). Outputs: `eval/control_curves.jsonl` (per-bar, per-deck
low/mid/high gain in dB, fit r2), `eval/control_curves_summary.json`, `eval/control_curves_validation.json`,
`eval/djmix_transition_priors.json`. Sources: `src/eval/fetch_control_sources.sh` (YouTube ids in `pro_sets/src/*/NN.info`).
Method: Schwarz & Fourer DJ-mix reverse engineering + Kim et al. djmix-analysis, adapted to bars: chunk cross-correlation and RANSAC
for each track's time-stretch line (then sub-frame refinement), then a per-bar non-negative least-squares fit of the mix's 20
sub-band powers as a gain-weighted sum of the two stretched sources (plus a crowd/MC floor), with a smoothness prior between bars.
Bands are the same as our engine: low <150 Hz, mid 150-2000 Hz, high >2000 Hz.

## Validation (our own renderer, src2/engine.render_deck, known lanes; Remedy -> Ignite)
| case | median abs err low/mid/high (dB) | p90 | bass swap est/true (bar) | rebound est/true |
|---|---|---|---|---|
| monotonic, clean | 0.07 / 0.04 / 0.03 | 0.8 / 0.8 / 0.3 | 63.8 / 64 | 0.2 / 0 |
| monotonic, live (+1.5% tempo, saturation, noise -40 dB) | 0.27 / 0.16 / 0.15 | 0.7 / 0.9 / 0.6 | 64.7 / 64 | 0.5 / 0 |
| gain riding (-6 dB dip), clean | 0.08 / 0.04 / 0.04 | 0.8 / 0.9 / 3.1 | 63.7 / 64 | 6.2 / 6.0 |
| gain riding, live | 0.23 / 0.15 / 0.18 | 0.7 / 0.7 / 2.3 | 64.6 / 64 | 5.9 / 6.0 |
Tempo ratio error <= 0.0001. Errors are measured where the true band level is > -20 dB. Below that the masked deck is not
identifiable. Rebounds are only measured above -12 dB; a looser -20 dB gate produced a false 4.4 dB rebound in the live case.

## Real sets: the yield is the main caveat
There are 2 sets with a usable tracklist: Wilkinson @ Boomtown 2026 (YouTube chapters) and Hospital Podcast 393
(description tracklist). Dimension and Old Guard have no tracklists, so they were not run. 20 of 22 Boomtown tracks and 13 of
14 Hospital tracks were found and aligned. Boomtown plays at about 1.018x (about 177 BPM), but the studio versions only cover
40-110 s of each 3-6 min chapter (live VIPs/edits plus MC). As a result, only 9 transitions could be fitted, and 5 have a
median r2 >= 0.5. Those 5 are the evidence below (n is small, so treat these as indications, not norms).

## Findings
- **Bass handoff = a separate, fast EQ move.** Median curves aligned on the outgoing bass cut: outgoing low -1 dB (4 bars
  before) -> -7 dB at the cut -> -12 dB +4 bars -> about -15 dB floor. Incoming low is already about -1 dB by the cut.
  In the clearest set (Ultraviolet -> Afterglow), the outgoing bass goes from 0 to the floor within 1 bar (-36.7 dB/bar),
  while its mids take about 4 bars. The Cosmic Flowchart -> Don't You Leave Me fade is gentler (-2.6 dB/bar).
- **Outgoing decays in band order low/mid first, highs last.** Mid: -6.6 dB at the cut, -20 dB at +4, gone by +7. High:
  -3.6 dB at the cut, -5.6 at +2, -20 by +7. Hats and air ride out about 2-3 bars after the body.
- **Outgoing fader decay is never abrupt.** -3 dB to -20 dB takes 4.5 bars median (values 7, 5, 4, 1), about -3.5 to -4 dB per bar.
  The "1" is the S.P.Y -> Radiance cut, where the low r2 before the cut makes it uncertain.
- **Overlap.** The mids overlap for a median of 23 bars (10-39). Bars with both basses near full level have a median of 8
  (0, 0, 8, 15, 22). The Wilkinson incoming deck sat at about -15 dB mid/low for about 30 bars with highs louder (-6..-10 dB),
  then came up over about 8 bars before the bass swap. That looks like a high-first, low-cut entry.
- **Gain riding: no clear evidence.** The outgoing mid rebound has a median of 1.6 dB (values 1.9, 6.5, 1.6, 0.0, 1.3). The
  only value >= 6 dB sits in a bar range where the fit flips between -40 and -15 dB (masked deck), so it is likely artefact.
  Fades look like one monotonic move per band, which is consistent with the 2026-10-28 rule. The pros do move the EQ (the
  bass is cut separately from the fader, and the highs leave last), and our engine already has lanes for both.
- **Loops.** No clear loop or re-cue was found in these 5. Jump candidates logged in `run` output are mostly repeated chorus
  sections (multiples of 16 bars at 177 BPM), not DJ loops. Loop detection from this method is weak.
- **DJ Mix Dataset priors** (37,711 transitions, 4,995 mixes, mostly house/techno, metadata only): the median matched
  overlap is 56 bars (p25 33, p75 82). That is much longer than in DnB and includes inaudible parts, so it should not be used
  directly. 31% of overlaps are within 2 beats of a multiple of 32. Only 10.6% of incoming cue points sit on a 32-beat
  boundary of the track's own grid.

## Proposal (not enforced)
Soft score `pro_shape` in plan_search/score, as a template distance, not a gate:
1. Template = the median per-band curves above, aligned on the bass cut, with a +-1 bar tolerance and weights by band
   (low 0.4, mid 0.4, high 0.2).
   Score = mean |planned - template| dB over bars where either curve > -20 dB, mapped to 0..1. Use it as a tie-breaker among
   feasible plans, weight about 0.1-0.2, never a hard reject.
2. Soft preferences it encodes (all penalties, none of them bans): the outgoing -3 to -20 dB decay should take about 3-8 bars
   (smaller penalty outside that range, larger under 2 bars; this is the listener's no-abrupt-fade rule as a gradient); the
   outgoing highs should leave 1-3 bars after the mids (our HIGH_SWAP lane can do this); the bass handoff should take 1-2
   bars inside a 16-bar or longer mid overlap.
3. Gain riding: no change. The evidence doesn't show per-bar riding, so the one-monotonic-crossfade renderer stays as is.
4. Before relying on it, grow n. Run the remaining Hospital podcasts and Hospitality sets with description tracklists
   (studio mixes align far better than festival sets). The target is >= 30 reliable transitions.
