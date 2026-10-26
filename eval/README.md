# Pro-DJ eval (v0)
- src/eval/analyze_pro_set.py: blind or tracklist-anchored transition analysis (beat grid, novelty, bass-chroma swap, demucs vocals, key, beat clarity) -> eval/sets/*.json
- src/eval/build_profile.py -> eval/pro_profile.json (77 transitions from 4 pro sets)
- src/eval/score_mix.py -> eval/scores/*.json (per-transition + overall + variety + loop-overuse penalty)
- eval/validation.json: measured error on dj-mix-01 (true layout known)
- eval/example_ratings.jsonl: what the listener actually said (ground truth for calibration)
- eval/run_all.sh / run_rest.sh: reproduce (run the 1-hour sets one at a time; three in parallel ran out of memory)
Sources: Kim et al. ISMIR 2020 https://mir-aidj.github.io/djmix-analysis/ (1,557 mixes, transitions cluster on 32-beat phrases);
NIME sub-band EQ reverse-engineering https://nime.pubpub.org/pub/g7avj1a7/release/1 ; Hospital/Crossfader double-drop tutorial https://www.youtube.com/watch?v=ZQuIa741EwQ ;
Mixgraph double drop https://www.mixgraph.io/glossary/double-drop ; DJ.Studio DnB guide https://dj.studio/blog/mix-drum-and-bass ; Vibes transitions https://vibesdj.io/dj-tools/dj-transitions
Status: does NOT yet agree with the listener (mix02 scores 85.9 vs mix01 84.5) - vocal metric polluted by MCs, clash needs two-vocal detection.
