# Corpus growth resume — 2026-11-08 ET

## Did we keep going after 13:11?
No. Verified job mtimes stopped at 13:11 ET. This run resumed at ~19:16 ET.

## Transport diagnosis
- Configured ingestion host: SSH alias from mixes/config.env `HOST` (residential download machine).
- Path: SSH BatchMode over a mesh VPN `nc` proxycommand to that alias (CGNAT address recorded only in local `jobs/grow-transport-diagnosis.log`).
- This is **not** the same control plane as Cursor ListMachines. At retry, the registered desktop machines were offline in Cursor; the config.env SSH alias still succeeded.
- Earlier 13:05 failure: SSH banner-exchange timeout / UNKNOWN port 65535 — mesh path to the residential download host was unreachable then.
- Recovery used: wait/retry the existing SSH+yt-dlp path. No alternate downloader, cookie scrape, or control bypass.

## Growth result
- Admitted corpus: **33** (**21 train / 12 held-out**).
- Target held-out ≥10: **met (12)**.
- DJ-level split preserved: Maduk and Pola & Bryson are entirely held-out; train DJs unchanged (Hybrid Minds, Joe Syntax).
- Gates applied per candidate: version locate/BPM, talkover, real-blend v3 (≥2.5 bars @ −12 dB). No threshold retuning for individual clips.

### Newly admitted
- maduk_liquicity_lunar2025__02, __03, __05
- pola_bryson_puzzlewood__00, __02, __04

### Rejected among processed candidates
- maduk_liquicity_lunar2025__00: dj_talkover 6.78s
- maduk_liquicity_lunar2025__01: dj_talkover 5.7s
- maduk_liquicity_lunar2025__04: b locate before blend
- pola_bryson_puzzlewood__01: weak locate
- pola_bryson_puzzlewood__03: weak locate
- pola_bryson_puzzlewood__05: weak locate

GLXY Fabric set was not ingested because the held-out target was already met after Pola & Bryson.

## Fresh baseline
- train **25.31** (n=21); held-out **25.19** (n=12); failures 0.
- Rules/weights unchanged; means describe the expanded cohort.

## Verification / cleanup
- Tests: 74 passed, 0 skipped, 0 failed (`jobs/grow-tests-final2.log`).
- Orphan src2/st stems for dropped unused sources removed; admitted sources complete.
- Mix downloads deleted by process_mix; cache/mixes cleared.
- Jobs via runjob.sh: grow-ssh-probe, grow-meta-ok, grow-corpus, grow-baseline, grow-tests-final2, grow-backup.
