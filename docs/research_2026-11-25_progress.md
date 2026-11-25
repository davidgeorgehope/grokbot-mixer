# Midnight Research Progress — 2026-11-25 (ET)

- 00:02–00:52 AM ET (interrupted run): Prototyped `MID_HOLD=1` (`src2/mix_simple.py`, `src2/engine.py`, `protrans/recreate.py`, off by default), passed `midhold-smoke-1125`, launched `midhold-cohort-1125` (`mhb1125_base`, `mh6_1125`, `mh10_1125`).
- 01:37–01:58 AM ET (resumed run):
  - Verified live literature & practitioner URLs (DJustify, MixWeaver, Mosaikbox, Raveform, Zehren *Signals* 2024, Arguello ISMIR 2024, Kim NIME 2021, CyberDJ, 35hz, BeatmatchGuru, X double-drop).
  - Completed `midhold-cohort-1125` (`done rc=0`): `mh6` and `mh10` both failed `X1` on 33/33 pairs (`0/33` must-pass) and lost on `v1` held-out (`33.92 -> 33.36 / 33.48`). Verified `mhb1125_base` passes `X1` on `33/33` (`X1: 0`, `29/33` overall, `12/12` held-out), proving the `X1` failure is a real `MID_HOLD` fault (`guardrails.py:64` forbids `'mid'` automation).
  - Scored all 3 variants with `protrans/score_v2.py` (`official_v2-place8c`, `midhold-v2-1125` & `midhold-v2-mh10-1125`, `done rc=0`): `mhb1125_base` all `33.86` (train `34.84`, test `32.15`) vs `mh6` `33.66` (`34.50` / `32.19`) vs `mh10` `33.52` (`34.26` / `32.21`).
  - Diagnosed losers (`maduk_liquicity_lunar2025__02`, `netsky_hospital_classics__15`, `joe_syntax_hospital__12`, `maduk_liquicity_lunar2025__05`, `joe_syntax_hospital__11`): holding incoming mids `-6/-10 dB` until the bass swap delays audible `entry` by 1–4 bars and collapses effective `blend_length`.
  - Ran read-only diagnostics on X1-compliant follow-ups (`high_at` gated by `bob()` only `3/33`, `high_bar` fired only `2/33`, vs `25/33` active above-bass pairs; 4-bar cue novelty vs pro cues on 32 pairs).
  - Launched `midhold-bandlag-1125` (`bandlag.py`) via `jobs/runjob.sh`.
  - Wrote final report `docs/RESEARCH_2026-11-25_midhold.md`. `protrans/rules.json` and all defaults/thresholds unchanged; no blind A/B clips cut (prototype lost).
