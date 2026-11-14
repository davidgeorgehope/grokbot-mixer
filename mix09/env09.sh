# Mix 09 engine env (sourced by search/render/repair). Repo defaults (planner): BASS_SWAP_BARS=3 (hill-climb 2026-11-11), HIGH_OFS=8, LINGERW=0.15 (hill-climb 2026-11-13); full mix stays FADE=tail.
export STRUCT=1 FADE=tail LOOP32=0 ECHO_MAX=2 PREF_W=0 PREFW=0 SWAP_PHRASE=1 HIGH_SWAP=1 BASS_SWAP_BARS=3 HIGH_OFS=8 LINGERW=0.15
export CRATE_FILE=/workspace/mixes/mix09/crate.txt PAIR_TABLE=pair_table_09r3.json
unset PSKILL PSDBG
export LX=0  # no beat-stem loop exits (Mix 08: two lx exits slipped +8 ms G1; repair already bans them); la/lb phrase loops still on
