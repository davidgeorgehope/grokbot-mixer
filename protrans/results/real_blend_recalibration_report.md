# Real-blend recalibration and corpus growth — 2026-11-08 ET

## Outcome

Gate recalibration, fresh baseline and tests completed. **Corpus growth is blocked**, not complete: no new pro audio was ingested and the target of ten held-out clips was not reached. Actual cohort: **27 (21 train, 6 held-out)**.

## Gate choice

Use the same source-fitted full-band deck gains and -12 dB audibility criterion, but require **at least 2.5 total simultaneously audible bars** instead of eight. This is one fixed half-bar minimum for all clips, not a clip-specific exception or a new gap classifier. No gap-closing adds silent time. Existing version and talkover checks remain independent vetoes. Source file fingerprints were checked before reusing identical overlap measurements under the new threshold.

- Hospital __04: retained 46.7 s pro excerpt measures **2.356 bars**, rejected. The original full WAV remains unavailable; do not report this as a full-original-clip measurement.
- Joe Syntax __17: **0 bars**, rejected.
- Netsky __15: **3.262 bars**, readmitted.
- Positive Hybrid Minds __08: **33.528 bars**, admitted.
- Calibration sensitivity: Hospital excerpt is rejected at -9 and -12 dB, but passes at -15 dB (3.081 bars). We kept -12 dB unchanged. The chosen 2.5-bar boundary is only about one fitted frame beyond this negative; it is not a universally validated talk-gap detector. Talkover exclusion remains essential.

## Readmitted

- joe_syntax_hospital__00: 3.625 overlap bars
- joe_syntax_hospital__09: 3.262 overlap bars
- joe_syntax_hospital__14: 7.068 overlap bars
- hybrid_minds_ukf__13: 4.893 overlap bars
- hybrid_minds_ukf__23: 5.075 overlap bars
- netsky_hospital_classics__15: 3.262 overlap bars
- netsky_hospital_classics__23: 4.168 overlap bars

## All measured clips

| Clip | Total overlap bars | Status |
|---|---:|---|
| hybrid_minds_ukf__00 | 21.386 | admit |
| hybrid_minds_ukf__08 | 33.528 | admit |
| hybrid_minds_ukf__09 | 13.411 | admit |
| hybrid_minds_ukf__10 | 11.961 | admit |
| hybrid_minds_ukf__11 | 9.424 | admit |
| hybrid_minds_ukf__12 | 41.865 | admit |
| hybrid_minds_ukf__13 | 4.893 | admit |
| hybrid_minds_ukf__19 | 25.554 | admit |
| hybrid_minds_ukf__20 | 2.356 | reject |
| hybrid_minds_ukf__23 | 5.075 | admit |
| hybrid_minds_ukf__25 | 9.605 | admit |
| hybrid_minds_ukf__28 | 19.030 | admit |
| hybrid_minds_ukf__33 | 1.812 | reject |
| hybrid_minds_ukf__40 | 18.305 | admit |
| hybrid_minds_ukf__45 | 34.253 | admit |
| joe_syntax_hospital__00 | 3.625 | admit |
| joe_syntax_hospital__01 | 17.580 | admit |
| joe_syntax_hospital__08 | 16.130 | admit |
| joe_syntax_hospital__09 | 3.262 | admit |
| joe_syntax_hospital__11 | 13.230 | admit |
| joe_syntax_hospital__12 | 19.754 | admit |
| joe_syntax_hospital__13 | 19.754 | admit |
| joe_syntax_hospital__14 | 7.068 | admit |
| joe_syntax_hospital__17 | 0.000 | reject |
| joe_syntax_hospital__18 | 1.994 | reject |
| netsky_hospital_classics__02 | 16.311 | admit |
| netsky_hospital_classics__06 | 13.593 | admit |
| netsky_hospital_classics__15 | 3.262 | admit |
| netsky_hospital_classics__17 | 16.855 | admit |
| netsky_hospital_classics__23 | 4.168 | admit |
| wilkinson_boomtown2026__33 | 30.991 | admit |

## Fresh baseline and verification

- Freshly rerendered/rescored all 27 pairs: **train 25.31 (n=21), held-out 24.54 (n=6)**, zero failures.
- Rules and score weights unchanged; these are new cohort means, not engine improvements.
- Tests: **74 passed, 0 skipped, 0 failed**; covers boundary controls, source-fitted synthetic real/gap audio, daily/admission shared gating and all three ingestion gates.
- Daily admission smoke: 27 ids, Netsky __15 present, Hospital __04 and Joe __17 absent.
- Each baseline render cleaned in its worker; zero `/tmp/protrans_bench/realblend_*` leftovers. No growth audio was downloaded, so there is no partial growth audio to clean.

## Growth attempt and staged continuation

Existing `fetch.meta_remote` was invoked for the new Liquicity Maduk set via `jobs/runjob.sh`. It failed with `Connection timed out during banner exchange` / `UNKNOWN port 65535`. Registered-device status showed mac.lan connected but other devices offline; this does not mean the configured ingestion SSH host was reachable. No browser-cookie, proxy, alternate downloader or other workaround was attempted.

Public tracklist research staged **16 candidates across three entirely held-out DJs** in `results/growth_queue.json`:
- Maduk, Special Lunar set @ Liquicity Festival 2025 — 6 candidate pairs. https://www.youtube.com/watch?v=PZ6aQYEIqm0 ; tracklist opened: https://whatstheid.com/mix/youtube/PZ6aQYEIqm0/maduk-special-lunar-set-at-liquicity-festival-2025
- Pola & Bryson, Live From Puzzlewood (Shogun) — 6 candidate pairs. https://www.youtube.com/watch?v=nNpy62IMI-A ; indexed tracklist: https://idscouter.app/set/nNpy62IMI-A
- GLXY, Fabric Rooftop (Shogun) — 4 candidate pairs. https://www.youtube.com/watch?v=wRxePyKWgdU ; indexed tracklist: https://idscouter.app/set/wRxePyKWgdU
The last two tracklists were visible in search results but direct fetches failed; queued identities/times remain secondary-source candidates, not verified admitted audio. Nothing in this queue counts toward baseline or corpus size.
`grow_corpus.py` can resume through the **existing** metadata/download and `admit.process_mix` pipeline once its transport is available, retaining version, talkover and real-blend checks. It introduces no alternate auth/transport, routine or schedule. At least four additional clips must pass all gates before the ten-held-out target is satisfied.

Job evidence: `jobs/real-blend-grow-probe.log` (failed transport), `real-blend-recalibration-controls.log`, `real-blend-recalibration-verified.log`, `real-blend-recalibration-baseline.log` (successful).
