# diagnose round 0: mix05v3r0
13 fails {'V1': 4, 'W1': 4, 'C2': 1, 'R1': 1, 'O1': 2, 'N1': 1}; refs mix05n 0 fails, mix06i12 0 fails
**REGRESSION SUSPECTED - delivery blocked for this round**

## C2 x1 -> TRADEOFF
event kinds {'loop': 1} (new vs refs: False); in passing refs: 0
- 11:00 trans 3 [loop]: outgoing KDRPfuZfNYw -10.0 dB under its body in the first half of the overlap

## N1 x1 -> REGRESSION
event kinds {'lx': 1} (new vs refs: True); in passing refs: 0
- 45:25 trans 15 [lx]: master level step +9.9 dB at entry
- suspect code /_lx|LX_|beat-only/ in engine/mix_simple/beatstem; commits: c4d8843 12:29 grokbot-mixer: snapshot 2026-11-01 12:29 EST; 2b0df8b 09:38 grokbot-mixer: snapshot 2026-11-01 09:38 EST; d05b716 07:38 grokbot-mixer: snapshot 2026-11-01 07:38 EST

## O1 x2 -> TRADEOFF
event kinds {'blend': 2} (new vs refs: False); in passing refs: 0
- 35:07 trans 12 [blend]: only 7 bars with both decks audible at musical level (need >= 8)
- 38:04 trans 13 [blend]: only 5 bars with both decks audible at musical level (need >= 8)

## R1 x1 -> TRADEOFF
event kinds {'blend': 1} (new vs refs: False); in passing refs: 0
- 23:54 trans 8 [blend]: 2s3M6oX2lfo vs nT25guf4DRU median onset xcorr 0.09 < 0.2 over 7 overlap bars (drums fighting — wrong tempo or feel)

## V1 x4 -> TRADEOFF
event kinds {'blend': 3, 'loop': 1} (new vs refs: False); in passing refs: 0
- 3:47 trans 0 [blend]: NaY3x3GRDF4 & rpIpJQ7ujzc both singing 1 bars from 3:47
- 5:57 trans 1 [blend]: rpIpJQ7ujzc & OPuVVhbkicU both singing 1 bars from 5:57
- 13:14 trans 4 [loop]: YNz30crm5g0 & 5196v8VY1LI both singing 2 bars from 13:14
- 51:04 trans 17 [blend]: F1NCnCxyhqc & j9AuFRpLk7U both singing 1 bars from 51:04
- note: V1 rows carry sec=0 (time only in t_hint): flags were pinned to 0:00/trans 0; diagnose re-maps by t_hint. Fix in guardrails V1 output

## W1 x4 -> TRADEOFF
event kinds {'blend': 2, 'lx': 2} (new vs refs: False); in passing refs: 0
- 3:18 trans 0 [blend]: NaY3x3GRDF4 vs rpIpJQ7ujzc see-saw ['WOBBLE']: outgoing rise 0.7 dB, wobble 4, anti r 0.29
- 5:53 trans 1 [blend]: rpIpJQ7ujzc vs OPuVVhbkicU see-saw ['WOBBLE']: outgoing rise 3.7 dB, wobble 4, anti r 0.3
- 30:31 trans 10 [lx]: 6YDKymmWe9o vs h1RNzaTfRyY see-saw ['OUT_RISE']: outgoing rise 5.0 dB, wobble 0, anti r 0.27
- 45:25 trans 15 [lx]: AC3eEHeLd8A vs n1dOiesZS1g see-saw ['OUT_RISE', 'WOBBLE']: outgoing rise 4.7 dB, wobble 5, anti r -0.15
- note: 3:18 W1 wobble-only with outgoing rise 0.7 dB <1 dB: likely FALSE_POS
