# Blend planning as a decision problem: design memo (2026-11-01, no code changed)

## 1. What the research says (links checked 2026-11-01)
- **Scaling Test-time Compute for LLM Agents** (Zhu et al. 2025): https://arxiv.org/abs/2506.12928
  The findings: more test-time compute helps, more varied rollouts help, and **list-wise selection** (show all candidates together and pick one) beats scoring each one alone. Table 4 gives BoN 56.36→58.79, beam 53.94→56.97 and tree 50.91→55.76. Caveat: the judge is an LLM that was never checked against ground truth, and pass@4 (69) is far above what the judge picks (63). The selector is the bottleneck.
- **Trust but Verify! A Survey on Verification Design for Test-time Scaling** (Venktesh et al. 2025): https://arxiv.org/abs/2508.16665. It sorts verifiers into prompt-based, discriminative and generative, and into outcome vs process checks.
- **A Survey on Test-Time Scaling in LLMs: What, How, Where, How Well** (Zhang et al. 2025): https://arxiv.org/abs/2503.24235. I could not find the "+18% on math from voting" figure the listener quoted in the abstract, so I'm treating it as unverified.
- **Large Language Monkeys** (Brown et al. 2024): https://arxiv.org/abs/2407.21787. Coverage keeps rising as samples grow. With an automatic verifier such as unit tests, that becomes real gains (SWE-bench Lite 15.9%→56%). Without one, voting and reward models **plateau**. This is the strongest evidence that the verifier is the bottleneck.
- **Training Verifiers to Solve Math Word Problems** (Cobbe et al. 2021): https://arxiv.org/abs/2110.14168. Generate 100 candidates, then rank them with a trained verifier. The verifier **doesn't help at small data sizes because it overfits**, which matters for us with about 20 ratings.
- **Let's Verify Step by Step** (Lightman et al. 2023): https://arxiv.org/abs/2305.20050. Step-level (process) checks beat outcome-only checks. For us a step is one blend, and the mix is the outcome.
- **Scaling LLM Test-Time Compute Optimally** (Snell et al. 2024): https://arxiv.org/abs/2408.03314. Adapting compute to how hard the problem is beats flat best-of-N by about 4x in efficiency. For us that means spending candidates on hard pairs.
- **Deep RL from Human Preferences** (Christiano et al. 2017): https://arxiv.org/abs/1706.03741. It learns a Bradley-Terry reward from pairwise human comparisons, with few labels and active querying.
- **Active Ranking using Pairwise Comparisons** (Jamieson & Nowak 2011): https://arxiv.org/abs/1109.3701. With good features, adaptive queries need about d·log n comparisons, against roughly all pairs when queries are random. That is how to get the most out of few ratings from the listener.
- Not located or verified: the specific "reasoning survey" on tree search that the listener quoted. The general claim (tree search is only as good as how branches are scored) matches the Agents paper, where tree search with scoring was the *worst* setting at 50.91.

## 2. Where we are today (src2/plan_search.py)
- Beam search (beam=300) over the track sequence. Each pair has a precomputed table of windows `(kind,e,p,ib,X)`. Cost is a weighted sum of about 20 hand-tuned penalties (soft_cost, pro_shape, pen, DROPPEN, OUTPEN…), plus a small `PREFW` term from pair_prefs.
- The real verifier (render → guardrails O1/F1/L1/E1/E4/N1/R1/C2/W1, ears gate, pytest) only runs **after** a full 60-minute plan is chosen. A failure bans windows and triggers a full re-search. That is the "autoloop found no plan" spiral (iters 14, 16, 17).
- `predict()` and seesaw use *predicted* levels from meta. The Remedy→Ignite case shows the prediction can miss what the render really does (a fill in a looped section).
- Ground truth is thin: ratings.jsonl has 17 lines and eval/example_ratings.jsonl has 6. Roughly 12 rated blends, plus 1 loved track and the gold 5/5 blend.

Diagnosis in the papers' terms: we have **one sample** (the beam's top plan) and an **outcome-only verifier at the end**, and the scorer was never fitted to the listener. That is the worst corner of all three papers.

## 3. Proposed design: generate → render → verify → pick, per blend
### 3a. Per-blend candidates (process-level)
For each adjacent pair a→b, produce K≈8 **diverse** candidates instead of the single cheapest window. Pick them for diversity, e.g. the best one from each family:
1. natural outro (no loop), long X (≥32)
2. natural outro, short X (16)
3. 'la' loop on the cleanest phrase
4. 'lx' beat-only outro (drums+bass stem)
5. 'lb'/'ab' incoming loop
6. early vs late cue for the incoming track (two ib choices)
7. bass-swap bar early vs late (pro curves: outgoing bass cut 1–2 bars, highs leave last)
8. the Wilkinson-style long quiet sneak-in (incoming about −15 dB with hats up, ~30 bars)
"Diverse" means the families differ, not just neighbouring cue bars. The Agents paper and Monkeys both credit diversity, and correlated candidates fail the same way voting does.

### 3b. Environment verifier = real audio (strong check)
Render **only the blend snippet**: 8 bars before the blend + X + 8 bars after, through the real engine and an unchanged mastering chain, at a lower working sample rate if the engine allows. On the rendered audio, run measured checks: W1 seesaw on rendered RMS (not predicted), E4 lull, F1 fade tail, beat offset, vocal and key clash, the pro_shape distance on measured curves, and ears features. Hard fails stay only for things the listener called intolerable (abrupt outgoing fade, train-wreck beat offset). Everything else becomes a feature.

### 3c. Selector = pairwise (Bradley-Terry) model fitted to the listener
- Features per candidate: the measured check values above, plus family, X, loop/lx flags and pro_shape.
- Model: logistic BT, P(i≻j)=σ(w·(f_i−f_j)), with a strong prior. Initialise w from the current hand weights so it starts as today's cost and only moves where the listener's data disagrees. Cobbe et al. show learned verifiers overfit with few labels, so keep it linear, regularised and low-dimensional (≤10 features).
- Training pairs: every rated blend gives pairs against lower-rated ones (5 vs 3, 4 vs 2…). Gold Lilies→Just Hold On is the anchor. Within one blend, "the version the listener rated 2" vs "the fixed version" (Remedy→Ignite natural outro vs looped) is a clean pair too.
- Pick per blend **list-wise**: score all K together and take the top under BT. Report the margin. When the top two are within ε, flag it as "uncertain" instead of guessing.

### 3d. Sequence level: beam over blends with rendered scores (process + outcome)
- Keep the existing beam over track order (it is cheap and handles length/variety/coverage plan targets). Replace each edge cost with the **BT score of the best rendered candidate** for that pair-in-context. Cache by (a, b, incoming state).
- Plan-level targets (40% loops, drop_frac, outro share, 58–62 min) stay soft budget constraints. Because every edge has K options, the beam can trade one blend's family for another instead of dying, so a plan always exists.
- Final outcome check: render the full mix, full guardrails and pytest exactly as today. A failure now repairs **that blend locally** by swapping in the next-best candidate and re-rendering one snippet, not by re-running the whole search.

### 3e. Active learning from the listener (few ratings, max value)
After each mix, pick 3–4 blends where the model is least sure (small BT margin, or measured checks disagree with the model) and ask the listener only about those, as an A/B where possible ("version 1 or 2 at 28:00?"). That follows Jamieson & Nowak and Christiano: pairwise queries chosen adaptively. A/B snippets give a cleaner signal than 1–5 scores, and they suit his "3 = mediocre, only 5 = good" scale.

## 4. Cost estimate (box: 8 CPU cores, no GPU)
Not measured yet; these are assumptions to confirm in step 1.
- Snippet length is about 16 + X(16–48) + 8 bars, roughly 40–90 s of audio at 174 bpm. I assume a render plus measured checks takes 3–6 s of CPU each, since the engine is numpy and stems are already on disk. demucs is not in the loop: beat stems are precomputed at about 2.5 min/track, once per track.
- One fixed-order mix has 18 blends × K=8 = 144 snippets ≈ 7–15 CPU-min, or **about 1–2 min wall-clock on 8 cores**.
- Open order (the beam explores about 3–5 alternative neighbours per slot) is about 500–700 snippets ≈ 5–10 min wall-clock. The cache makes reruns nearly free.
- The final full render and pytest cost the same as today. Expected net effect is **faster** than the current autoloop, which spent hours (22:38→07:46) re-searching and found no plan.
- BT fit is under 1 s.

## 5. First step (small, verifiable, doesn't touch plan_search.py)
Build `src2/blend_bench.py`, a standalone script:
1. For the rated pairs we still have stems for (Remedy→Ignite, the gold Lilies→Just Hold On, plus the Mix 03/04/05n/06 rated pairs), generate the K=8 family candidates.
2. Render the snippets, time them (this confirms §4), and compute the measured features.
3. Fit BT on the listener's ratings, then check leave-one-out: does it rank the gold 5/5 above alternatives, and the 2/5 Remedy loop below the natural outro?
4. Write a ranked table and keep 2–3 A/B snippet pairs ready for the listener's next listening session.

Only after it passes do we wire the per-edge scores into plan_search, coordinated with whoever owns that file.

## 6. Risks
- About 12 labels is very little. The BT model must stay close to the hand prior, and the measured checks carry most of the weight early on.
- Snippet render ≠ full-mix context (mastering bus dynamics). Mitigate with 8-bar pre/post roll and the final full-render check.
- The ears model is our own judgment (the weak kind of verifier). Use it as a feature, never as the sole pick.
