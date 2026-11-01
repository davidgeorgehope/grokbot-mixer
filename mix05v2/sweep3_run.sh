cd /workspace/mixes/src2
python3 - <<'P'
import json;R=json.load(open('../mix05v2/sweep3_cands.json'))
for i,r in enumerate(R):open(f'../mix05v2/sw3_{i}.order','w').write(','.join(r[2]))
P
for f in ../mix05v2/sw3_*.order; do i=$(basename $f .order)
 FAMBAN=0 BW=200,400,800 DROP_FRAC=0.25 OUTPEN=300 BADW_NEWONLY=1 PAIR_TABLE=pair_table_05v2.json TABLE_K=400 ORDER=$(cat $f) PINW='{"j9AuFRpLk7U>cxS6yd0UAxw":["lb",176,null,48,32]}' DROPPEN=60 BOTHMIN=8 COVPEN=300 python3 plan_search.py search --base plan_mix05v2_base.json --out /workspace/mixes/mix05v2/plan_$i.json --min 56 --max 63 --verify 60 --beam 2500 > ../mix05v2/$i.log 2>&1 &
done; wait
