# Grok chart-judge pilot (2026-11-18 night)

Asked by the listener ("Yeah try whatever"; "the grok judge could be a smaller component of judgement"). This is a small calibration
of a Grok vision judge reading our diagnostic PNGs. It is a supporting signal only. Nothing in `rules.json` or the defaults
changed. Code and data are in `protrans/llm_judge/`.

## Verdict

- **Defect detection from a single blend chart (beat clash, bass hole, level pump, bad cue): not reliable.** Don't use it
  as a gate or a tiebreak. At most it can draft RCA wording, and a person or hard check has to confirm every claim.
- **Pairwise "which blend is less defective" from two charts: not reliable.** It was at chance (48%), and it often flipped
  when the A/B order was swapped.
- **Pairwise "which plan is closer to the pro" on simple decision-timeline charts: useful for triage, and a weak tiebreak at
  best.** It was 100% right when one plan was clearly far off. On close calls it was 78% right, with a strong first-slot bias,
  so a close-call answer only counts if it survives an order swap.

## What was built

| File | What it does |
| --- | --- |
| `judge.py` | xAI-only client. Model `grok-4.20-0309-non-reasoning`, temperature 0, JSON output. The key comes from the 1Password vault Grokbot ("xAI API key") through a box-private file and is never printed. Every call is logged to `runs/calls.jsonl` with xAI's own cost ticks. |
| `redact.py` | Whites out every panel title before the judge sees a chart, because titles carry pick ids, scores, dip numbers and the half-beat PASS/FAIL. `panels()` splits a figure into one image per panel (used for v3). |
| `gen_cases.py` | Run as job `llm-judge-cases`, finished rc=0 at 20:56 ET. For 30 real default renders from `replica/gate_ckpt/default.jsonl` it writes the standard blend_diag figure (`cases/<id>__clean.png`), plus one copy with a known defect injected into the deck audio (`__inj_<defect>.png`). Injections: incoming deck delayed 110 ms; both decks' lows below 150 Hz cut by 50 dB for 6 bars; or both decks -10 dB for 1 bar. `hardcheck.check` is re-run on every figure. Manifest: `cases.jsonl` (60 cases). |
| `human_cases.py` | 9 delivered diagnostics with labels from the listener's ratings and comments and the RCAs: 11-17 clash, 11-17 fixed, 11-14 bass hole plus bad cue, 11-14 fix, the 4/5 days, 11-16 "can't tell", and the 11-11 engine rebuild. Also 3 better/worse pairs. Files: `cases_human.jsonl`, `pairs_human.jsonl`. |
| `decision_charts.py` | No audio. Each composite chart shows REF (the pro plan) and candidates X and Y as section timelines with the blend window and bass swap marked. Ground truth is the candidate with the smaller bar error versus the pro (exit + cue + overlap + swap). There are three kinds. `ours_vs_near` is our real default plan against the pro plus up to 4 bars of jitter. `near_vs_far` is jitter of up to 4 bars against up to 40 bars. `close_call` is jitter of up to 6 bars against up to 16 bars. Every chart is also drawn with X and Y swapped. 96 cases in `cases_dec.jsonl`. |
| `prompts.py`, `run_eval.py`, `metrics.py`, `cost.py` | Prompts v1 and v2 (v3 is the v2 text with per-panel images), the runner, and the scoring: precision and recall, Wilson 95% intervals, first-slot rate, swap consistency, and repeat flips. |

**Split.** Cases are grouped by pair id, using an md5 hash, so about a third of the pairs are held out. A pair's clean
render, its injected copy and its decision charts all sit on the same side. The held-out human cases are the 11-14 pair, the
11-13 and 11-16 days and the 11-11 engine rebuild. The held-out slice was run once, after the prompt was frozen.

## Prompt iterations (dev slice only)

| Version | Defect detection | Less-defective pair | Decision chart |
| --- | --- | --- | --- |
| v1 | Called beat clash on 20 of 20 charts. The per-bar offset panel is noisy even on locked blends. It found 0 bass holes and 0 pumps. | 58% | 90% overall, close calls 74% |
| v2 (conservative, panels named by content, forced lows readout) | Fewer false alarms (4 of 13 clean charts) but caught only 8 of 20 defects. Bass hole precision 0.18. | 50% | 90% |
| v3 (v2 text, one image per panel) | No better: 5 of 14 clean false alarms, 10 of 22 caught | 45% | not run |
| v2 on `grok-4.20-0309-reasoning` | Worse: flagged bass hole on 11 of 11 clean charts | 30% | not run |
| v2 on `grok-4.7` | Aborted after 13 rows: about 100 s per call, 4 API errors and $0.43 spent. No usable numbers. | n/a | not run |

v2 on the non-reasoning model was frozen for the held-out run. It was chosen for fewer false alarms, not for being good.
The v1 dev run covered fewer cases (20) because cases were still being generated, so the dev rows above aren't on identical
sets.

## Held-out results (v2, non-reasoning, temperature 0, every prompt asked 3 times)

Source: `runs/v2_heldout.jsonl` (285 calls, 0 errors), with metrics in `runs/v2_heldout.metrics.json`. Defect precision and
recall use repeat 1. n is tiny, so read these as direction only.

**Single-chart defects (21 charts: 8 clean renders, 8 injected, 5 human):**

| Defect | Hit | False alarm | Missed | Precision | Recall |
| --- | --- | --- | --- | --- | --- |
| Beat clash | 0 | 1 | 1 | 0 | 0 |
| Bass hole | 5 | 7 | 1 | 0.42 | 0.83 |
| Level pump | 0 | 1 | 4 | 0 | 0 |
| Bad cue (only the 11-14 human case) | 0 | 0 | 1 | n/a | 0 |

- Any defect: it caught 9 of 11 defective charts but also flagged 5 of 10 clean ones. Accuracy was 0.67.
- Human cases: it flagged a bass hole on 11-14 (correct). It also flagged holes on 2 of 4 good human charts. It missed the
  11-14 bad cue.
- Repeats at temperature 0 still changed the answer on 6 of 21 charts.

**Pairwise, less defective (blind, both orders, 3 repeats):**

- Overall: 48% of 48 calls (95% CI 34–62%). Only 4 of 24 (case, repeat) pairs were right in both orders, and 10 of 16
  (case, order) groups flipped between repeats.
- Injected pairs: 50% of 36 calls.
- Human pairs (11-14 fix vs before; 11-11 engine vs phrase cut): 42% of 12 calls, and 0 of 6 right in both orders.

**Decision charts, closer to the pro (both orders, 3 repeats, 174 calls):**

- Our default plan vs near-pro: 100% (60 calls, CI 94–100%), swap-consistent 30 of 30.
- Near vs far: 100% (60 calls), swap-consistent 30 of 30.
- Close calls (6 vs 16 bars of jitter): 78% (54 calls, CI 65–87%). It picked the first-listed candidate 72% of the time and
  was swap-consistent on only 15 of 27.
- Overall: 93% (CI 88–96%). It flipped between repeats on 2 of 58 groups.

## The hard checks are not a clean ground truth

These are limitations of the pilot itself, and they need fixing separately.

- **Clean renders labelled by hard checks.** Real renders have no human label, so their "truth" is `hardcheck.check`. 7 of
  the 30 were flagged:
  - pumping: ukf__11, ukf__00, ukf__40
  - clash: joe_syntax 11, joe_syntax 12, ukf__28
  - hole: pola00 (clean render, flagged hole)

  An injected case's label lists only the defect we injected, so a render that already had a flagged issue carries label
  noise. Clean renders with any flag were left out of the less-defective pairs.
- **Clash injections.** The hard check caught only 2 of 10 injected 110 ms clashes. Missed: wilkinson 33, joe_syntax 08,
  netsky 02, ukf__00, ukf__10, joe_syntax 14, hybrid_minds 23 and netsky 15.
- **Bass-hole injections.** The hard check caught 0 of 10. Its threshold is the pro p95 summed-lows dip of 45.34 dB, and our
  normal renders already dip 20–45 dB. Missed examples include joe_syntax 09 and netsky 23.
- **Checks firing on the wrong defect.** The maduk03 injected hole tripped the clash check. Clash also fired on 2 injected
  pumps, and pumping fired on 2 injected holes and 1 injected clash.
- **Pumping** caught 10 of 10 injected pumps, the only clean pass. The judge caught 0 of them, because a 1-bar notch is too
  small to see at chart resolution.
- **Human cases.** The 11-17 clash the listener heard and the 11-14 hole RCA both passed the shipped checks at the time.

So "agreement with hard checks" measures two weak signals against each other. Injection truth is only as good as the
injection: a 6-bar lows cut that lands where the render already dips is hard to see for anyone.

## Other limitations

- The sample is small: 21 held-out defect charts, 8 held-out injected pairs, and 2 held-out human pairs. The confidence
  intervals are wide.
- Defects are synthetic except for the human cases. Only 1 human beat clash (dev) and 1 human hole plus bad cue (held-out)
  exist.
- The decision charts are drawn by us and are easy to read. The judge read where boxes sit; it never judged musical
  quality. Near-pro candidates are jittered pro plans, not real alternative engine plans.
- The per-bar offset panel in blend_diag is noisy on locked blends. That alone drove v1's 100% clash false alarms, so a
  chart change would need to come before any re-test.
- No audio was used, and nothing about taste was measured.

## Cost and calls

758 logged calls, $2.52 total, using xAI's cost ticks (`python3 protrans/llm_judge/cost.py`):

| Model | Calls | Cost |
| --- | --- | --- |
| grok-4.20-0309-non-reasoning | 701 | $1.26 |
| grok-4.20-0309-reasoning | 47 | $0.83 |
| grok-4.7 | 10 | $0.43 (aborted) |

4 calls errored, all in the aborted grok-4.7 and reasoning dev runs.

## If we keep it

- Use it only as a decision-chart triage helper, for example to flag an engine plan that sits clearly far from the pro.
  Always ask in both orders and drop any answer that changes when the order is swapped.
- Never use it to pass or fail a blend, and never as a default-changing signal.
- Before any re-test of defect reading, fix the offset panel, calibrate injections against the hard checks, and get more
  human-labelled defects.
