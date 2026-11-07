import os,sys,json,time
os.chdir('/workspace/mixes/src2')
sys.path.insert(0,'/workspace/mixes/src2')
for k,v in dict(LOOP32='0',ECHO_MAX='2',STRUCT='1',FADE='tail',PREF_W='0',PREFW='0',
    PAIR_TABLE='pair_table_07.json',TABLE_K='400',DROPPEN='60',BOTHMIN='8',COVPEN='300',
    OUTPEN='300',FAMBAN='0',BW='200,800',BADW_NEWONLY='1',WIN_TOPK='400',SOFT='0',
    SWAP_PHRASE='1',HIGH_SWAP='1',NUDGE='nudge05n.json',STEPMAX='6',STEPPEN='15',
    PYTHONUNBUFFERED='1').items():
    os.environ[k]=v
# do not set DROP_FRAC so the dry structure test uses 1/3
os.environ.pop('DROP_FRAC', None)
os.environ.pop('ORDER', None)
os.environ.pop('PINW', None)
import plan_search as PS
print('searching...', flush=True)
t0=time.time()
done,K,st=PS.search('plan_mix07_base.json',60,90,400,BW=(200,800),fix_open=False,
                    exclude=('cxS6yd0UAxw','_K2sC9nrf_A'))
print(f'search {st}s complete={len(done)} feasible={sum(not d["fails"] for d in done)}', flush=True)
pool=[d for d in done if not d['fails']]
def rank(d):
    drop=sum(PS._drop_ok(w) for w in d['bl'])
    outr=sum(PS._outro_ok(w) for w in d['bl'])
    n=max(1,len(d['bl']))
    return (-drop/n, -outr/n, sum(w['pen'] for w in d['bl']))
pool.sort(key=rank)
print('top drop/outro fractions:')
for d in pool[:8]:
    n=len(d['bl']); print(n, 'drop', sum(PS._drop_ok(w) for w in d['bl']), 'outro', sum(PS._outro_ok(w) for w in d['bl']), 'len', round(d.get('bars',0)*PS.C.BAR/60,2) if False else '?')
seen=set(); tried=0; best=None
for d in pool:
    vk=tuple(d['seq'])
    if vk in seen: continue
    seen.add(vk); tried+=1
    P=PS.to_plan(d,'plan_mix07_base.json')
    v=PS.dry(P, tried)
    tests=v.get('tests') or {}
    fail=[t for t,o in tests.items() if not o] if tests else [v.get('error','?')]
    print(f"dry {tried}: {'ALL OK' if v.get('all_ok') else 'fail '+str(fail)} drop={sum(PS._drop_ok(w) for w in d['bl'])}/{len(d['bl'])} outro={sum(PS._outro_ok(w) for w in d['bl'])}/{len(d['bl'])} tracks={len(d['seq'])}", flush=True)
    if v.get('all_ok'):
        json.dump(P, open('plan_mix07_r1.json','w'), indent=1)
        json.dump({'order':d['seq'],'blends':[{'a':w['a'],'b':w['b'],'w':w['w'],'voc':w.get('voc'),'both':w.get('both'),'R':w.get('R'),'step':w.get('step')} for w in d['bl']],
                   'pred':v}, open('/workspace/mixes/mix07/plan_mix07_r1_info.json','w'), indent=1, default=str)
        print('WROTE plan_mix07_r1.json', flush=True)
        best=P; break
    if tried>=30: break
print('done best', bool(best), 'elapsed', round(time.time()-t0,1), flush=True)
sys.exit(0 if best else 2)
