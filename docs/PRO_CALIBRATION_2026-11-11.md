# Pro calibration 2026-11-11 (America/New_York): outgoing ride after the bass swap

Rule: `src/build_qa/test_release_structure_tail.py::test_outgoing_fader_tail_is_gradual`, second half. For each blend window of
X bars, count the bars from the bass swap to the window end where the outgoing deck is above -20 dB; fail if that count is under
`RIDE_FRAC*X - 1`. With the old `RIDE_FRAC=0.35`, a 32-bar window needed ~10 bars, which blocked FADE=long (its decisive 8-bar
exit gives ~6-7 bars after the swap). The first half of the test (no more than 3 dB per bar while above -24 dB) is unchanged.

Measured by `src/calib/ride_vs_pro.py` on the 33 admitted pro transitions (`protrans/results/admitted.json`), same corpus,
source alignment and deck-gain fit as `src/calib/guard_vs_pro.py` (2026-11-10). Results: `src/calib/ride_vs_pro_results.json`.

Pros have no crossfader to read, so the outgoing level is its full-band NNLS deck gain per bar (`diagnose_gap.band_gains`),
relative to its own p90. The bass swap is the bass-band event (the scorer's `events_from_pair` rule). The window runs from the
incoming's first 2 bars above -24 dB to the outgoing's last bar above -24 dB (the test's audible line).

| | result |
|---|---|
| pros breaking the old 0.35 rule | 5 of 33 (15.2%) |
| largest RIDE_FRAC each pro passes: p5 / p10 / median | 0.149 / 0.269 / 0.674 |
| new `RIDE_FRAC` (p5 = 95% of pros pass) | **0.15** |
| need at 32 bars: old / new | 10.2 / 3.8 bars |

Caveats, both stated plainly:
- The pro clips are 46 bars long, so in 30 of 33 the window touches the clip edge (the blend is longer than the clip or a deck
  never drops under -24 dB in the fit). Only 3 clips are fully inside; 1 of those 3 fails 0.35.
- The NNLS fit leaves a muted deck at about -7..-12 dB, which makes a pro's outgoing look longer than it is, so pros look like
  they pass more than they do. That biases the count toward keeping the rule, not loosening it.
- Sensitivity: with a -18 or -12 dB window line instead of -24, 3 of 33 pros fail 0.35 and the p5 is 0.26 / 0.24. 0.15 is the
  like-for-like (-24 dB) number.

Pros who break it: Netsky Hospital Classics 17 and 23, Pola & Bryson Puzzlewood 00, Joe Syntax Hospital 00 and 11; each takes the
outgoing to near silence within 3-8 bars of the bass swap.

Calibrated the same way as the 2026-11-10 bass-dip guards (pro p95), approved by the listener 2026-11-11. Nothing else changed.
Tests: `src/tests/test_ride_calibration.py` (metric, constant equals the measured p5, FADE=long 32-bar window passes now and
failed the old rule).
