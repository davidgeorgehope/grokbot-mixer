"""Mix 06 repair loop: plan_search -> render -> master -> guardrails; ban the pairs the guardrails fail on; repeat. Then full pytest."""
import os,sys,json,subprocess,time
os.chdir('/workspace/mixes/src2');R='/workspace/mixes';P=f'{R}/PROGRESS_mix06.md'
def log(m):
  open(P,'a').write(f"- {time.strftime('%H:%M')} ET: {m}\n");print(m,flush=True)
def sh(c):return subprocess.run(c,shell=True).returncode
BAN=set(open('../mix06/ban06.txt').read().strip().split(','));EX=open('../mix06/excl06.txt').read().strip()
env='DROPPEN=60 BOTHMIN=8 COVPEN=300 PREV_PLANS=../mix06/prev05.json'
BAR=60/174*4;MP3='/workspace/mixes/mix06/dj-mix-06.mp3'
start=int(sys.argv[1]) if len(sys.argv)>1 else 0
for it in range(start,start+20):
  name=f'mix06i{it}';plan=f'plan_{name}.json'
  if False:sh(f'cp plan_mix06e.json {plan}');name0='mix06e'
  else:
    name0=None
    rc=sh(f"{env} python3 plan_search.py search --base plan_mix06_base.json --out {plan} --min 58 --max 62 --verify 60 --beam 900 --exclude {EX} --ban '{','.join(sorted(BAN))}' > ../mix06/{name}_search.log 2>&1")
    if not os.path.exists(plan):log(f'iter {it}: search found no plan (bans {len(BAN)}), stopping');sys.exit(2)
  if name0:  # reuse render e's guardrails
    gname=name0
  else:
    gname=name
    sh(f'rm -f {name[:5]}*_raw.wav {name[:5]}*_master.wav')
    if sh(f"python3 restore_audio.py >/dev/null && python3 mix_simple.py --plan {plan} --out {name} > ../mix06/{name}_render.log 2>&1 && bash ../src/master.sh {name}_raw.wav {MP3} 9.3 {name}_master.wav >> ../mix06/{name}_render.log 2>&1"):log(f'iter {it}: render failed');sys.exit(3)
    sh(f"python3 ../src/guardrails.py --name {name} --mp3 {MP3} --nudge nudge05n.json --png >> ../mix06/{name}_render.log 2>&1")
  G=json.load(open(f'guard_{gname}/guardrails.json'));M=json.load(open(f'{gname}_meta.json'));T=M['trans']
  if G['n_fail']==0:
    log(f'iter {it}: {plan} guardrails 0 fails; running full pytest');open('../mix06/FINAL_NAME','w').write(f'{gname} {plan}')
    rc=sh(f"MIX_NAME={gname} MIX_MP3={MP3} MIX_WAV=/workspace/mixes/src2/{gname}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests ../src/build_qa > ../mix06/{gname}_pytest.log 2>&1")
    log(f'pytest exit {rc}: '+open(f'../mix06/{gname}_pytest.log').read().strip().splitlines()[-1]);sys.exit(rc)
  bad=set()
  for f in G['failures']:
    i=f.get('trans')
    if i is None:
      b=f['sec']/BAR;i=min(range(len(T)),key=lambda k:0 if T[k]['start_bar']-4<=b<=T[k]['end_bar']+24 else min(abs(b-T[k]['start_bar']),abs(b-T[k]['end_bar'])))
      f['trans_guess']=i
    bad.add(f"{T[i]['a']}>{T[i]['b']}")
  json.dump(G,open(f'guard_{gname}/guardrails.json','w'),indent=1)  # bad_windows() now skips exactly these windows next search
  log(f"iter {it}: {G['n_fail']} guardrail fails {G['by_check']}; windows banned on {sorted(bad)}")
