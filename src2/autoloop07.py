"""Mix 07 render/repair loop: plan -> render -> master -> guardrails -> pytest; ban failing pairs/windows; escalate with A/B if needed."""
import os,sys,json,subprocess,time,glob,re
os.chdir('/workspace/mixes/src2');R='/workspace/mixes';P=f'{R}/PROGRESS_mix07.md';LOG=f'{R}/mix07'
os.makedirs(LOG,exist_ok=True)
def log(m):open(P,'a').write(f"- {time.strftime('%H:%M')} ET: [07] {m}\n");print(m,flush=True)
def sh(c,t=None):
  try:return subprocess.run(c,shell=True,timeout=t).returncode
  except subprocess.TimeoutExpired:return 124

ORDER=','.join(json.load(open(f'{R}/mix07/order.json')))
ENV=dict(LOOP32='0',ECHO_MAX='2',STRUCT='1',FADE='tail',PREF_W='0',PREFW='0',PAIR_TABLE='pair_table_07.json',TABLE_K='40',ORDER=ORDER,
  DROPPEN='60',BOTHMIN='8',COVPEN='300',OUTPEN='300',FAMBAN='0',BW='200,800',DROP_FRAC='0.2',BADW_NEWONLY='1',WIN_TOPK='400',SOFT='1',
  SWAP_PHRASE='1',HIGH_SWAP='1',NUDGE='nudge05n.json')
for k,v in ENV.items():os.environ[k]=v
env_prefix=' '.join(f'{k}={v}' for k,v in ENV.items())
BAR=60/174*4;MP3=f'{LOG}/dj-mix-07.mp3';ROUNDS=int(os.environ.get('ROUNDS',4))

def render(name,plan):
  sh(f'rm -f {name}_raw.wav {name}_master.wav')
  if sh(f"python3 restore_audio.py >/dev/null && {env_prefix} python3 mix_simple.py --plan {plan} --out {name} > {LOG}/{name}_render.log 2>&1 && bash ../src/master.sh {name}_raw.wav {MP3} 9.3 {name}_master.wav >> {LOG}/{name}_render.log 2>&1"):return None
  sh(f"python3 ../src/guardrails.py --name {name} --mp3 {MP3} --nudge nudge05n.json --png >> {LOG}/{name}_render.log 2>&1")
  G=json.load(open(f'guard_{name}/guardrails.json'));log(f"{name}: {G['n_fail']} fails {G['by_check']}");return G

plan0='plan_mix07.json'
if not os.path.exists(plan0):
  log('no plan_mix07.json yet');sys.exit(2)

name='mix07r0'
G=render(name,plan0)
if G is None:log('render failed');sys.exit(3)
if G['n_fail']==0:
  rc=sh(f"MIX_NAME={name} MIX_MP3={MP3} MIX_WAV=/workspace/mixes/src2/{name}_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests > {LOG}/{name}_pytest.log 2>&1")
  log(f'pytest exit {rc}: '+open(f'{LOG}/{name}_pytest.log').read().strip().splitlines()[-1])
  open(f'{LOG}/FINAL_NAME','w').write(f'{name} {plan0}')
  sys.exit(rc)

# diagnose + blend_loop repair for failing pairs
import diagnose
M=json.load(open(f'{name}_meta.json'));T=M['trans'];bad=set()
for f in G['failures']:
  i=f.get('trans')
  if i is None:
    b=f['sec']/BAR;i=min(range(len(T)),key=lambda k:0 if T[k]['start_bar']-4<=b<=T[k]['end_bar']+24 else min(abs(b-T[k]['start_bar']),abs(b-T[k]['end_bar'])))
  bad.add(f"{T[i]['a']}>{T[i]['b']}")
log(f'failing pairs {sorted(bad)}')
# write escalate stub + try blend_loop once
try:
  import blend_loop
  CUR={f"{p['id']}>{q['id']}":p.get('out_win') for p,q in zip(M['plan'],M['plan'][1:]) if p.get('out_win')}
  picks,rep=blend_loop.run(sorted(bad),CUR,{},tag='m07_',regress=())
  json.dump(rep,open(f'{LOG}/blend_loop_repair.json','w'),indent=1,default=float)
  CH=dict(CUR);CH.update(picks)
  # re-search with PINW
  pin=json.dumps(CH)
  rc=sh(f"{env_prefix} PINW='{pin}' SOFT=1 PS_KEEP=1 python3 plan_search.py search --base plan_mix07_base.json --out plan_mix07_r1.json --min 60 --max 90 --verify 1 --beam 400 > {LOG}/search_r1.log 2>&1",t=3600)
  if os.path.exists('plan_mix07_r1.json'):
    G2=render('mix07r1','plan_mix07_r1.json')
    if G2 and G2['n_fail']==0:
      rc=sh(f"MIX_NAME=mix07r1 MIX_MP3={MP3} MIX_WAV=/workspace/mixes/src2/mix07r1_master.wav python3 -m pytest -q -p no:cacheprovider ../src/tests > {LOG}/mix07r1_pytest.log 2>&1")
      log(f'r1 pytest {rc}');open(f'{LOG}/FINAL_NAME','w').write('mix07r1 plan_mix07_r1.json');sys.exit(rc)
except Exception as e:
  log(f'repair err {e}')

# escalate
os.makedirs(f'{R}/deliver/ab',exist_ok=True)
esc=dict(mix=7,status='escalate',fails=G['by_check'],pairs=sorted(bad),note='guardrails did not clear; see mix07/ and deliver/ab/')
json.dump(esc,open(f'{LOG}/ESCALATE.json','w'),indent=1)
json.dump(esc,open(f'{R}/deliver/ab/ESCALATE_mix07.json','w'),indent=1)
log('ESCALATE written');sys.exit(1)
