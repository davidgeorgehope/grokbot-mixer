# Pipeline calibration report — 8 November 2026 (ET)

## Scores (unchanged engine rules and fixed score weights)

| Corpus / metric | Train | Held-out |
|---|---:|---:|
| Paired rerender, old scorer (25 / 8) | 24.51 | 29.40 |
| Same audio, repaired scorer (25 / 8) | 23.86 | 26.58 |
| Corrected sources + two skips (25 / 6) | 23.86 | 24.54 |

The previously published archived baseline was 24.03 / 28.83. The paired
rerender is the apples-to-apples comparison of the detector repair. Metric
calibration lowered scores; this is not an engine quality gain or regression.
Current baseline_clean.json contains the corrected 31-clip corpus; the old
baseline and admitted list are preserved beside it.

## Detectors

See event_detector_notes.md. Multi-bin nonnegative gain inference replaces an
underdetermined one-power/two-deck event estimate. Deck-relative quarter-level
support, sustained crossover, and contiguous overlap eliminate absolute-level
artifacts. Bass controls measure handoff; fullband controls measure exit and
length. Fixed weights/scales unchanged. On all 33 pro clips: one-bar artifacts
5 -> 0 and bar-zero swaps 7 -> 0. Synthetic oracle events agree exactly; real
clean-oracle events agree to one-bar quantization. Old score checkpoints and
decisions are version-filtered; accepted engine rules remain unchanged.

## Source audit

* __15: official Hospital Memory Lane, https://www.youtube.com/watch?v=DpYdXERlkFk,
  verified outside the blend at 0.8787 (prior 0.3403), native BPM 175.005.
  Retained in lib and admitted. Important: the original UKF copy also reaches
  0.8597 when aligned to a different phrase. The old diagnosis was largely a
  wrong locator lock, not established proof of a different recording.
* __16: Together original Topic upload best 0.3705; VIP 0.2783 in the original
  outside-blend evaluation window. No verified replacement: persistently skip.
* __24: Nobody To Love official video 0.2543; extended candidate 0.2618 in the
  original evaluation window. Topic extended download returned HTTP 403.
  No verified replacement: persistently skip.

Candidate provenance, matching rates, phrase positions and exact evaluation
windows: version_search_audit.json and memory_original_realign.json. Failed
candidates are not silently admitted. version_rejected.json is honored by
future admission; original clips and studio inputs were not deleted.

## Engine tests

Full cause-by-cause table: engine_test_fixture_audit.md.
Before: 17 failures + 4 setup errors, 42 passed, 21 skipped.
After: src/tests 14 passed / 72 skipped / zero failures or errors.
Protrans 8 passed. Combined: 22 passed / 72 skipped.
The skips are explicit missing archival audio / no selected render, NOT a
passing audio-release certification. All calibrated checks and thresholds
remain intact. Two tests prove that no selected build skips but an explicitly
selected build with missing metadata fails. No engine bug was established:
missing audio explains most errors, while some old mixS metadata genuinely
violates newer assertions; it must not be presented as a newly passing mix.

## Backup / cleanup

Local patch archive: local_pipeline_patch_20261108.tar.gz (code, tests, reports;
no secrets or audio). External backup_mixer_to_git.sh was NOT run: the delegated
brief alone is not explicit user approval for publishing changes outside the
box. Parent should run it only with confirmed user authorization.
Own audit render WAVs/MP3s and downloaded rejected candidate audio were removed;
the verified studio copy and reusable analysis/input caches were retained.
