# Learned ranker and corpus_v2

the listener, 15 November 2026, agreed to a learned-model approach after every
hand-written rule overfit the 33-pair pro corpus. Step 1 is scaling the
data. Step 2 (a small CPU ranker) starts only after 150 accepted
transitions.

## Isolation

The new dataset lives in `protrans/corpus_v2/` and is separate from the
33-pair scoring cohort. The pipeline never writes `protrans/rules.json`,
`protrans/results/admitted.json`, the official `clips/` or `lib/` trees,
or the 33-pair score checkpoints. Quality gates are unchanged: locate
z ≥ 6 and cc ≥ 0.28, native BPM 169–179, talkover veto, real-blend v3
(≥ 2.5 bars at −12 dB). Rejects are logged in
`protrans/corpus_v2/rejected.jsonl`.

The six official scoring mixes (Hybrid Minds UKF, Joe Syntax Hospital,
Netsky Hospital Classics, Maduk Liquicity Lunar 2025, Pola & Bryson
Puzzlewood, Wilkinson Boomtown 2026) are not re-ingested and are not
used to train the ranker. They stay an eval-only set.

## How a mix is admitted

Same method as the existing protrans mining path (`fetch.meta_remote` /
`fetch.ytdlp_remote` on the configured download host, `version_match`,
`talkover.check_clip`, `real_blend.assess`):

1. Find a tracklisted live DJ mix (YouTube chapters or timestamped
   description; yearmixes and megamixes are out).
2. Keep Goldilocks neighbours only (outgoing listed for 90–280 s, no
   IDs, no bootlegs).
3. Fetch both studio sources through the existing yt-dlp flow.
4. Admit only when alignment confidence is high and the real-blend and
   talkover gates pass.
5. Record the cue bar and section, outgoing exit section, blend length,
   rise and tail, per-band EQ, and per-track features (drops,
   breakdowns, intro length, bass per section, energy, BPM).
6. Archive source audio, the mix, and accepted clips to Google Drive
   (`gdrive:DJ Mixes Archive/protrans/corpus_v2/`), verify the copy, and
   delete the local audio so the box stays lean.

## Split

Held-out is reserved by mix, not by transition, with a fixed seed
(20261115). At least 20% of mixes with an accepted transition are
held-out. No model sees those mixes during training.

## Ranker (only at 150+ accepted)

A small CPU ranker (LightGBM LambdaMART, or a histogram-boosting
fallback) scores the engine's candidate windows per pair — cue window,
SNAP_IN or not, and the long hold — by similarity to what the pro did.
It is behind a flag with defaults unchanged. We report how often the
top pick matches the pro's incoming cue section on the held-out mixes,
and (when that flagged scorer run is done) held-out 33-pair scores
against 34.05. The flag stays off unless that evaluation clears the
floor with no failures; this document will name the flag and the scores
when that run exists.

## Commands

Long job (status file + webhook):

```
bash jobs/runjob.sh corpus-v2 python3 protrans/run_corpus_v2.py all
```

Resumable pieces: `discover`, `ingest`, `split`, `train`. Progress is
`protrans/corpus_v2/progress.json`; the compact manifest is
`protrans/corpus_v2/manifest.json`.

## Tracklist parsing (15 November 2026)

The first corpus-v2 pass ingested YouTube *chapters* whenever there were
four or more of them. On Hospital Podcasts those chapters are often
talk-segment labels ("Politics", "Cmon Cookies", "Etherwood and chat
debate"), not "Artist - Title" lines, while the official tracklist sat
in the description without timestamps. The resolver then searched those
junk or partial strings and almost every candidate failed with "no
confident search hit." Alignment quality gates were not the cause and
were not loosened.

The parser now keeps a line only when it has a timestamp and an
"Artist - Title" shape. It prefers a description or an official
Tracklist: block over chapters, and may bind official titles to chapter
*times* when they clearly line up. A mix needs at least eight such
lines. Source search uses the full "Artist - Title" string. Rejects
continue to be logged.

## Title normalizer and throughput (16 November 2026)

Track names from chapters often carry a leading `//`, bullet, list number, or leftover timestamp. Those tokens made source search miss (score -25 on a clean DC Breaks title). `fetch.normalize_track_title` now strips that junk before search, while leaving cue timestamps intact for the line parser and leaving artist names like `1991 - Nine Clouds` alone. Copies off the download host retry the copy only, without re-encoding, and subsequent ingest prefetches two studio sources at a time. Alignment and the quality gates are unchanged. A slash-resolve retry walks earlier rejects whose reason was a resolve miss with a `//` prefix.
