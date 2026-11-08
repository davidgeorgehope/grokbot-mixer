# Talkover filter progress
- [x] talkover.py (demucs vocal residual + source-quiet gating), tests/test_talkover.py passing
- [x] admit.py hook (process_pair rejects, apply_talkover()), run_admitted_tune.load_recs filters flagged
- [x] stems/run (4 flagged: hosp393_04, netsky_10, joe_10, wilk_10) over 37 (scratch_talk/*.npz, results/talkover.json) -- rerun: TALK_STEM_DIR=$PWD/scratch_talk python3 talkover.py --force
- [ ] calibrate, apply_talkover, baseline, backup, cleanup scratch_talk
