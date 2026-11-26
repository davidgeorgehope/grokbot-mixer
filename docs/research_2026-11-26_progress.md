# Midnight Research Progress — 2026-11-26 (ET)

- 11:52 PM ET 11/25: started. Nightly `fit-pro-fade-5` (PRO_FADE grid) holds the render slot; corpus-v2 resume running (left alone).
- Prototype: `HIGH_GATE=1` (off by default) in `src2/mix_simple.py` (`above_both()`; high swap also allowed when both decks carry above-bass energy >= half the blend, not only drums-on-drums), passed through `protrans/recreate.py`. rules.json untouched.
- `highgate-smoke-1126` done rc=0: joe_syntax_hospital__12 v1 32.29 -> 35.59 (same window).
- ~12:00 AM ET: launched `highgate-cohort-1126` (`protrans/research_1126/eval_highgate.sh`: waits for render slot, then base / hg8 (HIGH_OFS 8) / hgm4 (HIGH_OFS -4) cohort + eval_tailexit + score_v2). If cut off: rerun the same command; eval_cohort checkpoints per pair.
