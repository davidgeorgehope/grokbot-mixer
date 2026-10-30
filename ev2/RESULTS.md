# Ears v2 (learned blend-quality model) - 2026-10-29
Not live in the gate: it does not beat the current check on the listener's held-out blend ratings.
Data: 2,824 8-bar windows from 3 pro sets (transitions + segments = clean; bar-aligned overlays = clean;
off-grid shifts 16th/half-beat/beat/30-120 ms and 1/6-semitone overlays = bad). Held-out: 8 blends the listener rated (bad = 2/5 or less).
Trained with PyTorch MPS on the GPU host (ev2/train*.py), leave-one-pro-set-out validation.
| model | pro-set val acc | held-out (8) acc | notes |
| current gate (ears + direct drums must agree) | - | 7/8 | fails only 34:05 (1/5); misses 15:00 (2/5) |
| current ears alone | - | 2/8 | 5 false alarms on blends rated 3-4/5 |
| v2a log-mel CNN | 53-66% | 4/8 | ranks 34:05 worst, but 30:56 (5/5) flagged and 15:00 passed |
| v2b bar-folded onsets + chroma CNN | 41-67% | 2/8 | flags everything (synthetic overlays don't look like real mixes) |
Why it lost: too few real bad blends (2) and synthetic clashes don't transfer to real mixdowns. Next: train on per-deck stems
(what the gate already renders) and on every new rating; revisit at 20+ rated blends.
