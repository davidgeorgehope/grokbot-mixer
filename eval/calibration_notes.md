# Guardrail calibration, 2026-11-01 (the listener, after Mix 05 v2 escalation)

Evidence: the listener's picks on the 3 escalations (2B, 3B "really nice", 1C), "none of the escalated options sounded terrible",
and ratings.jsonl (the only bad-rated blend is Mix 06 28:00 Remedy>Ignite, 2/5, "tracks fight, fading randomly in and out").

Priority order (listener rule): 1 see-saw (strict), 2 abrupt fades (block by default, musical cuts allowed), 3 everything else = warnings unless ratings show it sounds bad.

| Check | Before | After |
|---|---|---|
| W1 see-saw (src2/seesaw.py) | blocks on OUT_RISE > 4.5 dB, WOBBLE >= 4 reversals, ANTI r <= -0.5 | blocks on TRADE (louder deck flips >= 2 times, 3 dB hysteresis) or ANTI; OUT_RISE and WOBBLE are warnings |
| Abrupt tail (test_structure_tail) | any >6 dB one-bar drop of the outgoing within 20 dB of its pre-blend level blocks | same, except a deliberate cut: drop lands on a phrase boundary (outgoing source bar %8==0 or blend bar %8==0) AND incoming is already at full level (within 3 dB of its level 4 bars after the blend) |
| O1 overlap | fail < 8 bars | warning (< 8 bars) |
| R1 drum xcorr | fail < 0.20 | warning (< 0.20) |
| F1 flam | fail > 15 ms | warning (> 15 ms) |
| 32-bar blends >= half (test_mix02_traits) | fail | warning |
| beat-on-beat 16 bars >= half (test_mix02_traits) | fail | warning |

TRADE validation: on mix06i12, mix05n, mix05v3r2 and mix05v2i10 only Remedy>Ignite (3 flips) blocks; the gold Lilies>Just Hold On passes;
2B/3B-type cases (outgoing rise 3.7/5.2 dB, wobble 5) become warnings.

Fix playbook: eval/fix_playbook.json (test code -> ordered automatic fixes; diagnose.strategies walks it, logs `fix` in nudges.jsonl, escalates when exhausted).
