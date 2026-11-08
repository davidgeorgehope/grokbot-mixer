# Gain-event calibration

The fixed W dictionary and time_sim scales are unchanged. This is a scorer
repair, not an engine-rule hill-climb or a claimed audio-quality improvement.

Previously each 23ms frame's one power observation was fit against two deck
powers with an underdetermined pseudoinverse. That cannot separate a solo
passage from a blend reliably. Absolute -25/-28dB gates additionally made
mastering level masquerade as overlap length or bar-zero bass takeover.

Event-only measurements now fit the two aligned studio fingerprints using
non-negative spectral multi-bin gains (the existing phase-tolerant oracle
fitter). Deck-curve similarity itself is not changed. Bass handoff is read
from bass-band controls; outgoing exit and overlap from fullband controls.
Per-deck active-level normalization, quarter-amplitude (-12dB) presence,
a two-bar sustained crossover (1dB fit tolerance), and longest contiguous
common support replace absolute energy crossings and first/last noise hits.
An empty intersection is zero, not a fabricated one-bar blend. A swap needs
prior outgoing dominance, so starting with incoming already dominant is not
called a bar-zero swap. Outgoing exit is the end of audible support, not the
first 6dB decline during a long fade.

"Blend length" is common support above quarter level, not the entire barely
audible fade. For a linear 32-bar crossfade this central support is about
16 bars. This definition is consistently applied to pro and recreation.

Tests cover gain/mastering-level invariance, silence, a long fade, a synthetic
clean gain-curve oracle (exact event agreement), a real clean Joe Syntax
oracle (within one bar of quantization), and incompatible scorer checkpoints.
SCORER_VERSION prevents the nightly checkpoint reader from mixing old metric
scores with this calibration.

Known limit: source locating and the gain fit are still approximate. This
repair is not a perfect-transcription claim. In the version search, Memory
Lane's original copy also reached 0.8597 outside the blend when a different
phrase hit was selected: its previous 0.3403 was largely a locator failure,
not proof of a different recording. The official Hospital replacement
verified at 0.8787 and was retained. Together and Nobody To Love stayed
unverified and are skipped, not scored as engine mistakes.
