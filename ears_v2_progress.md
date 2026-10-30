# Ears v2 progress
- step0: started 21:52, surveying data
- step1: ev2/prep.py running (nohup) -> ev2/train.npz; audio of rated mixes in ev2/audio (from Drive)
- step2: ev2/held.py (held-out windows) running; ev2/train.py written
- step1b: fixed tempo-resample bug, prep rerun
- step3: training on GPU host ~/ears/v2 (train.log, ears_v2_results.json)
- step4: v2a (log-mel CNN) weak: LOSO 53-66%, held-out no better. Trying v2b features (bar-folded onsets+chroma): prep_b.py/held_b.py -> *_b.npz
- step5: train_b.py launched on GPU host
- step6: DONE. Neither v2a nor v2b beats current gate on held-out (7/8). Gate unchanged. Results in ev2/RESULTS.md
