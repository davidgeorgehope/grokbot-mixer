# Hard checks v2, drop windows and online DJ style (2026-11-18, late night ET)

Flags only. `rules.json` is unchanged and nothing was promoted. Every number below comes from files in `protrans/replica/`.

## 1. Retry of corpus-v2 reject `mrmommusic_nodB5gqt_mU__49`
- Retried in its own folder, `replica/retry_work`, which was deleted afterwards. corpus-v2 was not touched.
- New verdict: still a reject. The reason is now a real one: `a: weak locate z=5.63 cc=0.7563`, below Z_MIN 6.0.
- The bogus parts of the original reason are gone: "native BPM None", ffmpeg exit 254 on the deleted `corpus_v2/work/lib` files.
- The row is appended to `corpus_v2/rejected.jsonl` with `retried_after_incident`.
- Audio folders are now separate:
  - corpus-v2 uses `corpus_v2/work`.
  - fresh mixes use `replica/fresh_work`.
  - the retry used `replica/retry_work`.
  - fresh sources are in `replica/fresh_src`.
  - No job cleans another job's folder.
- One shared item remains: fresh-mix feature JSONs (not audio) are written to `corpus_v2/features`. Nothing deletes them.

## 2. Hard checks v2 (`hardcheck_v2.py`, `calib_v2.py`, `calib_v2c.py`, `clash_roc.py`)
**Injected set.** Built from all 103 default renders:
- clean
- clash: incoming delayed 60 ms and 110 ms
- hole: both decks' lows below 150 Hz cut 50 dB for 4 bars and for 8 bars, mid-blend
- pump: 1 bar at -10 dB

The split is md5(pair) % 3: 73 dev pairs and 30 held-out pairs. Design constants were picked on dev only. Every threshold is the pro p95 on the 33 protrans pro clips. The pro false-alarm rate is leave-one-pro-out.

### Bass hole (adopted)
- **Statistic:** deficit of the summed lows against the blend's own body level (the median over bars outside the overlap), with a duration term. The score is the largest sum over one run of bars of (deficit - 30 dB).
- **Threshold:** pro p95 = 109.
- **Held-out detection:**
  - 8-bar hole: 90% (dev 93%)
  - 4-bar hole: 30% (dev 27%)
  - clean flag rate: 0% (dev 1.4%)
  - pump flagged as hole: 3%
- **Pro false alarms:** 6.1%.
- 8-bar holes meet the 80% bar. **4-bar holes do not.**
- First version (T0 grid stopping at 24 dB): threshold 323, held-out 8-bar 87%, 4-bar 30%, clean 10%. Superseded.

### Beat clash: no candidate reaches 80% recall at the pro p95
| candidate | thr | pro FA | held-out clean | held-out 60 ms | held-out 110 ms | 11-17 must-catch (pre-lock) | 11-17 fixed (listener: clash gone) |
|---|---|---|---|---|---|---|---|
| v1 (halfbeat + finephase lag) | – | – | – | judge pilot 2/10 | – | caught (123 ms) | **flags it** (false alarm) |
| v2a beat-rate phase, run | 0 | – | 0% | 0% | 0% | – | – |
| v2b deck-to-deck xcorr, run | 1 | 3.0% | 0% | 6.7% | 6.7% | – | – |
| v2c deck-vs-mix lag, run | 2.4 | 6.1% | 0% | 6.7% | 3.3% | – | – |
| median abs deck-to-deck lag, r≥0.3 (best of `clash_roc.json`) | 70.8 ms | 9.1% | 3.3% | 16.7% | 56.7% | caught (113 ms) | passes (5.8 ms) |
| count of bars >45 ms, r≥0.2, pro vs-mix | 9.4 | 9.1% | 0% | 30% | 30% | – | – |

**Why it fails:** the pro reference is too noisy. The measured deck-to-deck lag on pro clips has a median of 60–75 ms (sources placed once on the pro clip, plus tempo drift), so the pro p95 sits near or above a 110 ms fault. On our renders only a few overlap bars have confident drums.

**Not adopted:** a v2 clash check. A threshold taken from our own clean renders instead of the pros did no better: 110 ms held-out detection was 47–60%, and that would also break the pro-p95-only rule.

Hard-fail sets used below:
- **HC_A** = v2 hole OR v1 clash OR half-beat OR pumping
- **HC_B** = v2 hole OR median-lag clash OR half-beat OR pumping

### Hard fails on all 103 pairs
| variant | v1 | HC_A | HC_B | v2 hole | v1 clash | median-lag clash | pump |
|---|---|---|---|---|---|---|---|
| default | 18 | 17 | 14 | 1 | 7 | 3 | 9 |
| REPLICA=1 | 30 | 31 | 29 | 12 | 8 | 6 | 16 |
| gated | 29 | 30 | 27 | 12 | 8 | 5 | 15 |
| drop-exit | 13 | 10 | 11 | 0 | 2 | 2 | 8 |
| drop-cue | 6 | 6 | 7 | 0 | 1 | 2 | 5 |

## 3. DROPCAND flag (`src2/replica_rule.py`, hooks in `mix_simple.py` and `recreate.py`)
- **`DROPCAND=exit`:** the blend is the last X bars of the outgoing track's drop 1, and the incoming drop lands at the blend end.
- **`DROPCAND=cue`:** same outgoing span, but the incoming starts at its own drop 1 (drop-on-drop).
- **`DROPCAND=both`:** only adds both windows as candidates.
- Legal on 91 of the 103 pairs. The other 12 reuse the default render (LAZY).

Dev results: 91 pairs, grouped bootstrap by mix, HC_A.

| policy | exit+cue mean | Δ vs default [95% CI] | exit hit@16 | cue hit@16 | HC_A fails | HC_B | v1 |
|---|---|---|---|---|---|---|---|
| default | 40.4 | – | .19 | .64 | 17 | 13 | 18 |
| gated | 36.6 | -3.7 [-13.1, 9.1] | .30 | .53 | 30 | 26 | 29 |
| drop-exit | 37.4 | -3.0 [-12.8, 10.2] | .25 | .65 | 10 | 11 | 13 |
| drop-cue | 37.7 | -2.7 [-11.5, 9.3] | .25 | .51 | 5 | 7 | 5 |
| LODO selector over arms | 38.0 | -2.4 [-11.9, 10.5] | .25 | .59 | 9 | 10 | 12 |

Drop windows alone give no clear error win, but they have far fewer hard fails than default. The selector picked drop-exit in 10 of 11 folds.

## 4. Online DJ style (`online_style.py`, `final_eval.py`)
- For transition t, the style is the share of the pro's mid-track exits over that mix's transitions with index < t (the last 3, or all earlier ones).
- Use the mid-track arm only when there are at least 2 earlier transitions and the share is above 0.5.
- Style predicted the current transition 78% of the time for K=3 and 80% for all earlier transitions. The base rate is 67%.

| dev policy (91) | exit+cue | Δ [95% CI] | exit hit@16 | HC_A fails | new vs default |
|---|---|---|---|---|---|
| online, replica arm, K3 | 33.8 | -6.6 [-10.4, -2.0] | .33 | 21 | 8 new, 4 fixed |
| online, replica arm, all | 32.8 | -7.6 [-11.0, -3.1] | .33 | 20 | 8 new, 5 fixed |
| online, drop-exit arm, K3 * | 34.0 | -6.3 [-10.5, -0.9] | .32 | 14 | 0 new |
| online, drop-exit arm, all * | 32.9 | -7.4 [-11.1, -2.4] | .32 | 14 | 0 new |
| online, drop-cue arm, K3 * | 34.8 | -5.6 [-9.4, -0.3] | .32 | 10 | 2 new |
| online, drop-cue arm, all * | 33.6 | -6.7 [-10.5, -1.7] | .32 | 10 | 2 new |

\* These arms were added after the first dev table, so they are exploratory.

New HC_A fails for the online replica arm, against default:
- fryett_ltdJ6GFixfs__26 (pump)
- hybrid_minds_ukf__10 (pump)
- netsky_hospital_classics__23 (hole 136)
- pola_bryson_puzzlewood__04 (pump)
- suicidesheeep_R8MWKsheHxk__18 (clash, 99 ms)
- theheshbesh_zHf8cC9ViuA__39 (pump)
- ukf_drum_bass_LeMk0yiSoq4__31 (hole 167 + pump)
- ukf_drum_bass_LeMk0yiSoq4__51 (pump; median lag 87 ms)

Seven of the eight are 32-bar replica windows.

## 5. Fresh test: KushSessions #303 (8 pairs, scored once; John B is spent)
- Default 20.0. The online policies are all identical to default (20.0, Δ 0): the style bit never fired, because the pro exited late on 7 of 8 transitions and the only mid-exit was transition 1, which has no history.
- The always-on arms are all much worse: gated 41.5, REPLICA=1 45.8, drop-exit 44.5, drop-cue 38.8, selector 44.5.
- HC_A fails: default 3, online 3, drop arms 1.
- There is only one mix, so the CI is degenerate.

## 6. Promotion
Nothing is promoted. Reasons:
- The online-style policies need the pro's earlier transitions of the same mix. That only exists when recreating a pro mix, and the saved criteria require a real style source.
- None of these policies is among the candidates frozen in `promotion_criteria.json`.
- The locked holdout was not opened.
