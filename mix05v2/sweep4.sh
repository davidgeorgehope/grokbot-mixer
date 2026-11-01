cd /workspace/mixes/src2
for o in 2 0; do for k in 1 2 3 4 5 6; do i=sw3_$o
 FAMBAN=0 BW=200,400,800 DROP_FRAC=0.25 OUTPEN=300 BADW_NEWONLY=1 PAIR_TABLE=pair_table_05v2.json TABLE_K=400 SEESAW_BANFILE=/workspace/mixes/mix05v2/seesaw_bans.json ORDER=$(cat ../mix05v2/$i.order) PINW='{"j9AuFRpLk7U>cxS6yd0UAxw":["lb",176,null,48,32]}' DROPPEN=60 BOTHMIN=8 COVPEN=300 python3 plan_search.py search --base plan_mix05v2_base.json --out /workspace/mixes/mix05v2/plan_$i.json --min 56 --max 63 --verify 40 --beam 2500 > ../mix05v2/${i}_s$k.log 2>&1
 echo "$i round $k: $(head -1 ../mix05v2/${i}_s$k.log)"; [ -f ../mix05v2/plan_$i.json ] && exit 0
done & done; wait
