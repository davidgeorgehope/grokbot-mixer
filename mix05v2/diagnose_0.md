# diagnose round 0: mix05v3r0
9 fails {'O1': 3, 'W1': 3, 'L1': 1, 'R1': 1, 'F1': 1}; refs mix05n 0 fails, mix06i12 0 fails
**no engine regression**

## F1 x1 -> TRADEOFF
event kinds {'blend': 1} (new vs refs: False); in passing refs: 0
- 47:58 trans 16 [blend]: n1dOiesZS1g vs F1NCnCxyhqc beats 16.0 ms apart

## L1 x1 -> TRADEOFF
event kinds {'loop': 1} (new vs refs: False); in passing refs: 0
- 14:38 trans 4 [loop]: both decks carry full bass at once

## O1 x3 -> TRADEOFF
event kinds {'blend': 3} (new vs refs: False); in passing refs: 0
- 5:53 trans 1 [blend]: only 5 bars with both decks audible at musical level (need >= 8)
- 36:02 trans 12 [blend]: only 7 bars with both decks audible at musical level (need >= 8)
- 37:53 trans 13 [blend]: only 5 bars with both decks audible at musical level (need >= 8)

## R1 x1 -> TRADEOFF
event kinds {'loop': 1} (new vs refs: False); in passing refs: 0
- 41:11 trans 14 [loop]: EiZVTuiqo0w vs AC3eEHeLd8A median onset xcorr 0.16 < 0.2 over 15 overlap bars (drums fighting — wrong tempo or feel)

## W1 x3 -> TRADEOFF
event kinds {'blend': 1, 'loop': 2} (new vs refs: False); in passing refs: 0
- 5:53 trans 1 [blend]: rpIpJQ7ujzc vs OPuVVhbkicU see-saw ['WOBBLE']: outgoing rise 3.7 dB, wobble 5, anti r 0.06
- 24:16 trans 8 [loop]: 2s3M6oX2lfo vs nT25guf4DRU see-saw ['OUT_RISE']: outgoing rise 9.6 dB, wobble 1, anti r 0.52
- 43:24 trans 15 [loop]: AC3eEHeLd8A vs n1dOiesZS1g see-saw ['OUT_RISE']: outgoing rise 5.2 dB, wobble 2, anti r -0.0
