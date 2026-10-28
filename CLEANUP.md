# Cleanup 2026-10-28: simple crossfader engine becomes the only engine

## Inventory before cleanup (engine code and who imports what)
| File | Role | Imported/called by | Fate |
|---|---|---|---|
| src2/mix_simple.py | crossfader engine (produced current Mix 03, mixS) | run_simple.sh | KEEP (only engine) |
| src2/engine.py | shared core: track(), nudge(), srcbar(), Deck (stem/EQ/HPF/voc render), echo_tail | mix_simple, mix2/mix2b/mix3*, src/tests/deckpair.py | KEEP, trimmed to track/nudge/render_deck (no stems, no Deck/EQ/echo) |
| src2/engine_pre60.py | old engine copy | none | DELETE |
| src2/mix3.py (+ .bak_0915, mix3_pre_fill/guard/hold.py) | v3 stem/duck/fill/build/echo engine | render_and_test3/4.sh, rebuild_mix03_f.sh, add7.sh | DELETE |
| src2/mix2.py, mix2b.py, src/mix2b.py, src/mix.py | v1/v2 engines | render_and_test.sh | DELETE |
| src2/runs.py | bass-run finder for mix2/mix3 (writes order2.json runs) | mix2/mix3, add5-8.sh | DELETE |
| src2/makefx.py, src2/fx/ | risers/impact/roll for mix3 builds | mix3 | DELETE |
| src2/mixpoints.py | mix-point-map pass for MIX_POINT_MAP_PLAN (old engine) | none | DELETE |
| src2/analyze*.py | per-mix analysis json for old mix metas (mix360_meta) | none current | DELETE |
| src2/barfeats.py + barfeats2.py | per-bar dB features (all/low/hat/voc/drums) | add*.sh | MERGE into barfeats.py (BF glob env, keeps cached voc) |
| src2/sdev.py, verify.py, src/verify.py, src/barcheck.py, src/analyze.py | one-off diagnostics | none | DELETE |
| src2/add3..8.sh, addnew*.sh | per-batch track prep scripts | manual | REPLACE with src2/add_track.sh |
| src2/rebuild_mix03_f.sh, run_simple.sh, watch_e4_finish.sh | one-off loops | manual | DELETE (run_simple -> src/render_and_test.sh) |
| src/render_and_test.sh, render_and_test3.sh, render_and_test4.sh, iterate.sh | old render loops (mix2b / mix3) | manual | DELETE; new src/render_and_test.sh (crossfader) |
| post_render_03.sh, post_render_03v3.sh | one-off delivery watchers with hardcoded private hostnames | manual | DELETE |
| src/autofix.py (+ .bak_0915) | nudge auto-fix for F1/N1/G1 timing (uses deckpair) | iterate.sh | KEEP autofix.py (engine-agnostic), delete .bak |
| src/prep.py, src/fixgrid.py, src/drift.py | stale duplicates of src2 copies | none | DELETE |
| src/gen_tracklist_03.py | tracklist from mix360d meta | rebuild_mix03_f.sh | DELETE; gen_tracklist_03f.py -> src/gen_tracklist.py |
| src/guardrails.py | guardrails | render loop, tests | KEEP minus Q1/M1/H1/D1 and their helpers |
| src/tests/checks.py, conftest.py, deckpair.py, test_mix.py, test_guardrails.py, test_crossfader.py, test_pbpm.py | tests | pytest | KEEP (deckpair now renders via engine.render_deck) |
| src/tests/checks_pre60/pre_guard/pre_perbar.py | old copies | none | DELETE |
| src/tests/test_fader_guardrails.py | Q1/H1/M1 tests on mix360e fixture | pytest | DELETE |
| visuals/code render_visuals.py, procedural_backdrops.py, liquid.frag, analyze_mix_pre60.py, fal_backdrops.py | v1 visuals | none | DELETE (v2 kept) |
| src2/ENGINE_FIX_FADER.md, MIX_POINT_MAP_PLAN.md | old-engine design docs | - | DELETE |

## Data / renders
- DELETE: src2/sep (demucs stems, 8.3G; only barfeats needed them, features are cached in st/*.json), mix360e/f_raw.wav, mix2_raw.wav, src/master.wav (master.sh now writes <name>_master.wav), src/mix_raw.*, src/st, src/wav, src/djmix(+.tar) (mix 01 caches), all old metas/qa reports/guard_* dirs/plans/nudges/logs
- KEEP: eval/sets/demucs_cache (1.8G, used by the scorer analyze_pro_set.py), src2/mixS_master.wav (the tests read it), src2/st (stretched audio + grids/features), src2/wav (raw decode; T1 and pbpm test use it), src2/*.m4a, mixS_raw.wav + mixS_meta.json + guard_mixS (current master's inputs), dj-mix-03-60.mp3 (current master), plan_60f.json, nudge60f.json, keys_full.json, order.py/order2.json, visuals mp4 (pending iCloud retry), published mixes 01/02b mp3s

## Result (2026-10-28)
- 252 paths deleted, about 16.8 GB, including 8.3 GB of demucs stems.
- Only one engine remains: src2/mix_simple.py + engine.py (render is bit-identical to the pre-cleanup output).
- Single entry point: src/render_and_test.sh.
- pytest on mixS: 6 failed / 17 passed. Before: 6 failed / 27 passed. The same 6 known failures remain; the 10 deleted Q1/H1/M1 tests account for the difference in the pass count.
- Guardrails on mixS: 39 fails (V1 6, O1 4, N1 5, R1 6, L1 14, E1 3, E2 1). Before: 38 fails (V1 6, O1 7, N1 5, R1 5, L1 11, E1 3, E2 1). Per-deck renders now go through the real engine (1-beat seams) instead of the old Deck path, so the deck-alone checks shift slightly.
