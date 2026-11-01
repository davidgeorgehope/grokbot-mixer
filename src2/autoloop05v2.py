"""Mix 05 v2 repair loop: plan_search -> render -> master -> guardrails; ban the pairs the guardrails fail on; repeat. Then full pytest."""
import os,sys,json,subprocess,time
os.chdir('/workspace/mixes/src2');R='/workspace/mixes';P=f'{R}/PROGRESS_mix06.md'
def log(m):
  open(P,'a').write(f"- {time.strftime('%H:%M')} ET: {m}\n");print(m,flush=True)
def sh(c):return subprocess.run(c,shell=True).returncode
BAN=set();EX='none'
env='FAMBAN=0 BW=200,800 DROP_FRAC=0.25 OUTPEN=300 BADW_NEWONLY=1 PAIR_TABLE=pair_table_05v2.json TABLE_K=400 ORDER=NaY3x3GRDF4,rpIpJQ7ujzc,OPuVVhbkicU,KDRPfuZfNYw,YNz30crm5g0,5196v8VY1LI,MoYkYkoeb84,7Itbo72XEz4,2s3M6oX2lfo,nT25guf4DRU,6YDKymmWe9o,h1RNzaTfRyY,kKu3fIOTiHk,nAV4i1YIwQI,EiZVTuiqo0w,AC3eEHeLd8A,n1dOiesZS1g,F1NCnCxyhqc,j9AuFRpLk7U,cxS6yd0UAxw PINW=\'{"j9AuFRpLk7U>cxS6yd0UAxw":["lb",176,null,48,32]}\' DROPPEN=60 BOTHMIN=8 COVPEN=300'
BAR=60/174*4;MP3='/workspace/mixes/mix05v2/dj-mix-05-v2.mp3'
start=int(sys.argv[1]) if len(sys.argv)>1 else 0
for it in range(start,start+20):
  name=f'mix05v2i{it}';plan=f'plan_{name}.json'
  if False:sh(f'cp plan_mix06e.json {plan}');name0='mix06e'
  else:
    name0=None
    SBF='/workspace/mixes/mix05v2/seesaw_bans.json';nsb=lambda:sum(map(len,json.load(open(SBF)).values())) if os.path.exists(SBF) else 0
    for rnd in range(8):  # W1 dry-run fails are learned into SBF; re-search while it keeps learning
      n0=nsb();rc=sh(f"{env} python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 300 --beam 2500  > ../mix05v2/{name}_search.log 2>&1")
      if os.path.exists(plan) or nsb()==n0:break
      log(f'iter {it}: search round {rnd}: no plan, W1 dry-run bans {n0}->{nsb()}, re-searching')
    if not os.path.exists(plan):  # last ladder rung: swap a neighbour pair (gold pin j9Au>cxS6 and its order kept), never stop on 'no plan'
      O=env.split('ORDER=')[1].split()[0].split(',')
      for i in range(1,len(O)-3):
        O2=O[:];O2[i],O2[i+1]=O2[i+1],O2[i];e2=env.replace(','.join(O),','.join(O2))
        sh(f"{e2} python3 plan_search.py search --base plan_mix05v2_base.json --out {plan} --min 56 --max 63 --verify 100 --beam 2500 > ../mix05v2/{name}_swap{i}.log 2>&1")
        if os.path.exists(plan):log(f'iter {it}: nudge pair_swap {O[i][:4]}<->{O[i+1][:4]} gave a plan');open('/workspace/mixes/mix05v2/nudges.jsonl','a').write(json.dumps(dict(t=time.strftime('%H:%M'),plan=plan,nudge='pair_swap',swap=[O[i],O[i+1]]))+'\n');env=e2;break
    if not os.path.exists(plan):log(f'iter {it}: search found no plan even after neighbour swaps, stopping');sys.exit(2)
  if name0:  # reuse render e's guardrails
    gname=name0
  else:
    gname=name
    sh(f'rm -f {name[:5]}*_raw.wav {name[:5]}*_master.wav')
    if sh(f"python3 restore_audio.py >/dev/null && python3 mix_simple.py --plan {plan} --out {name} > ../mix05v2/{name}_render.log 2>&1 && bash ../src/master.sh {name}_raw.wav {MP3} 9.3 {name}_master.wav >> ../mix05v2/{name}_render.log 2>&1"):log(f'iter {it}: render failed');sys.exit(3)
    sh(f"python3 ../src/guardrails.py --name {name} --mp3 {MP3} --nudge nudge05n.json --png >> ../mix05v2/{name}_render.log 2>&1")
  G=json.load(open(f'guard_{gname}/guardrails.json'));M=json.load(open(f'{gname}_meta.json'));T=M['trans']
  if G['n_fail']==0:
    log(f'iter {it}: {plan} guardrails 0 fails; running full pytest');open('../mix05v2/FINAL_NAME','w').write(f'{gname} {plan}')
    rc=sh(f"DROP_FRAC=0.25 MIX_NAME={gname} MIX_MP3={MP3} MIX_WAV=/workspace/mixes/src2/{gname}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests > ../mix05v2/{gname}_pytest.log 2>&1")
    log(f'pytest exit {rc}: '+open(f'../mix05v2/{gname}_pytest.log').read().strip().splitlines()[-1]);sys.exit(rc)
  bad=set()
  for f in G['failures']:
    i=f.get('trans')
    if i is None:
      b=f['sec']/BAR;i=min(range(len(T)),key=lambda k:0 if T[k]['start_bar']-4<=b<=T[k]['end_bar']+24 else min(abs(b-T[k]['start_bar']),abs(b-T[k]['end_bar'])))
      f['trans_guess']=i
    bad.add(f"{T[i]['a']}>{T[i]['b']}")
  json.dump(G,open(f'guard_{gname}/guardrails.json','w'),indent=1)  # bad_windows() now skips exactly these windows next search
  log(f"iter {it}: {G['n_fail']} guardrail fails {G['by_check']}; windows banned on {sorted(bad)}")
