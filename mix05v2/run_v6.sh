set -x
cd /workspace/mixes/src2
export NUDGE=nudge05v6.json N=mix05v6 L=/workspace/mixes/mix05v2
rm -f ${N}_raw.wav ${N}_master.wav
python3 restore_audio.py >/dev/null && python3 mix_simple.py --plan plan_${N}.json --out $N > $L/${N}_render.log 2>&1 && bash ../src/master.sh ${N}_raw.wav $L/$N.mp3 9.3 ${N}_master.wav >> $L/${N}_render.log 2>&1 || { echo RENDERFAIL; exit 1; }
python3 ../src/guardrails.py --name $N --mp3 $L/$N.mp3 --nudge nudge05v6.json --png >> $L/${N}_render.log 2>&1; echo GUARD rc $?
DROP_FRAC=0.25 MIX_NAME=$N MIX_MP3=$L/$N.mp3 MIX_WAV=/workspace/mixes/src2/${N}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > $L/${N}_pytest.log 2>&1; echo PYTEST rc $?
