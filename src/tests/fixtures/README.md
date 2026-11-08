# Small offline fixtures

`generate.py` creates deterministic copyright-free full mix and drums+bass sources
in a caller-supplied directory. The pytest fixture owns that temporary directory
and deletes its generated audio and cards at teardown. Generated sources are
3.57 MB total; the checked-in generator and metadata are about 133 KB.

The four `*.grid.json` snapshots are small real-track feature regressions for
section detection, not dependencies on their commercial audio. `pair_prefs.json`
is the small fixed input for the 5-rated pin/ratings tests. The historical
`guardrails_*.json` checks report integrity, not a fresh audio analysis.

Run offline regressions: `python3 -m pytest src/tests -q`.
For a freshly built actual mix, the build entry points additionally run
`src/build_qa`, with explicit `MIX_NAME`, `MIX_WAV`, `MIX_MP3` before cleanup.
Synthetic sources must never certify an actual mix. No blanket missing-render
skips or archival-audio fixtures belong in the default regression suite.

See `docs/test-fixture-repair.md` for exact before/after counts and all 72 original
skip reasons, plus the list of 44 preserved live-build checks.
