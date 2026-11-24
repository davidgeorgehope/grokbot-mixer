#!/usr/bin/env python3
"""BLEND_AUDIO_GATE: prove each blend on its own audio before a plan is trusted (RCA 2026-11-24, docs/RCA_mix10_failure_loop.md, fix 1).

For blend i of a plan's meta (mix_simple --dry or a render meta):
  1. crop every deck that sounds in [start-PRE, end+POST] bars (PRE=16, POST=8), render each crop with engine.render_deck
     (same full_map, automation, nudges, locks), sum, and master with src/master.sh at the planned gain (the real chain);
  2. write the clip as a tiny build (meta shifted to bar 0 + raw wav + master wav + mp3) under src2/blend_gate_clips/;
  3. run the release checks on it, imported, not copied: src/guardrails.py (subprocess, every fail-check) and the blend-local
     src/build_qa tests (called in-process, same functions, same thresholds);
  4. cache the verdict in src2/blend_gate_cache/<key>.json, key = sha1(check-code hash, feature-content hash of the clip's tracks,
     the clip window itself: shifted deck crops + automation + the transition, gain, nudges for those tracks).

Thresholds are never touched here. Mix-level checks are tagged so callers can route them (P1 true peak -> master gain,
E4 whole-mix lull -> plan level); the clip still reports them.

Off by default: callers (plan_search / repair) consult the gate only when BLEND_AUDIO_GATE=1 (enabled()).
usage:
  python3 blend_gate.py --meta mix10_r6_meta.json [--trans 2,3] --gain 9.0 [--nudge nudge08_r9c.json] [--json out.json] [--jobs 3]
  python3 blend_gate.py --plan plan.json --gain 9.0 ...        (runs mix_simple --dry first; source the mix env first)
"""
import os,sys,json,copy,hashlib,glob,time,subprocess,argparse,functools
HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(HERE)
CACHE=os.path.join(HERE,'blend_gate_cache');CLIPS='blend_gate_clips'
PRE,POST=16,8
# release tests that judge one blend (called with the shared functions). Excluded on purpose, all mix-level:
# anchors/body/32-bar share/bob16 share/beatless share/outro share/lengths_vary/variety/echo cap/44k1 glob/ears (need ears json)/
# guardrails_zero (replaced by running guardrails.py itself)/diagnostic figures.
TESTS=[('test_release_bassgap','test_no_bass_gap_in_overlaps'),
  ('test_release_eq_swap','test_bass_never_doubles'),('test_release_eq_swap','test_phrase_swaps_land_on_phrase_boundary'),
  ('test_release_eq_swap','test_no_level_dip_at_swap'),('test_release_eq_swap','test_eq_lanes_monotonic_in_every_blend'),
  ('test_release_eq_swap','test_high_swaps_on_phrase_apart_from_bass'),('test_release_eq_swap','test_high_swap_no_doubled_highs'),
  ('test_release_crossfader','test_x1_on_mix'),('test_release_crossfader','test_mix_bass_swaps_monotonic_smooth'),
  ('test_release_mix','test_beat_drift_across_transitions'),('test_release_mix','test_global_grid_no_drift'),
  ('test_release_mix','test_downbeats_aligned'),('test_release_mix','test_beat_overlap_16_bars'),('test_release_mix','test_no_key_clash'),
  ('test_release_mix','test_no_unintentional_energy_drops'),('test_release_mix','test_no_abrupt_cuts'),('test_release_mix','test_true_peak'),
  ('test_release_mix','test_every_deck_on_its_planned_bar'),('test_release_mix','test_no_vocal_clash'),
  ('test_release_mix','test_mixdown_beats_aligned_every_overlap_bar'),
  ('test_release_mix02_traits','test_no_long_drums_only_stretch'),('test_release_mix02_traits','test_loops_only_repeat_the_phrase_just_played'),
  ('test_release_seesaw','test_no_seesaw_between_decks'),('test_release_halfbeat','test_no_half_beat_blends'),
  ('test_release_structure_tail','test_outgoing_fader_tail_is_gradual'),('test_release_structure_tail','test_outgoing_audio_tail_never_drops_abruptly'),
  ('test_release_echo_out','test_echo_tail_lands_on_phrase_boundary'),('test_release_echo_out','test_echo_tail_clear_of_incoming_kick'),
  ('test_release_echo_out','test_echo_tail_no_level_jump'),('test_release_echo_out','test_echo_tail_decays_within_4_bars'),
  ('test_release_echo_out','test_echo_out_leaves_dry_deck_identical')]
# size guards inside a test that assume a whole hour-long mix; on a clip they say nothing about the blend
SIZE_GUARDS=('too few measurable overlap bars',)
# Mix-level: reported, not a blend verdict. P1/test_true_peak -> master gain (gain_step.py); E4 compares to the WHOLE-mix median;
# test_global_grid_no_drift allows 3% of the whole mix's grid points off (on a 1-minute clip that is 0 of ~7 points, so one
# borderline point decides it: the per-blend grid gates are guardrails G1 and N1, which stay blend verdicts).
# test_every_deck_on_its_planned_bar measures each deck at its MIDDLE (its solo body in a full mix); a cropped deck's middle sits
# inside the blend, where the other deck confuses the lag search (Mix 10 r6c blend 19: 1028 ms at corr 0.64, full mix passed).
# Blend alignment is judged by test_mixdown_beats_aligned_every_overlap_bar, test_downbeats_aligned, test_beat_drift and N1/G1.
MIX_LEVEL={'P1','test_true_peak','E4','test_global_grid_no_drift','test_every_deck_on_its_planned_bar'}
CODE=['src2/blend_gate.py','src2/engine.py','src2/bassgap.py','src2/seesaw.py','src2/halfbeat.py','src2/beatmelody.py','src2/finephase.py',
  'src2/sections.py','src/master.sh','src/guardrails.py']+[os.path.relpath(p,ROOT) for p in sorted(glob.glob(f'{ROOT}/src/tests/*.py')) if not os.path.basename(p).startswith('test_')]+\
  [os.path.relpath(p,ROOT) for p in sorted(glob.glob(f'{ROOT}/src/build_qa/*.py'))]

def enabled():return os.environ.get('BLEND_AUDIO_GATE','0')=='1'

@functools.lru_cache()
def code_hash():
  h=hashlib.sha1()
  for p in CODE:
    f=os.path.join(ROOT,p)
    if os.path.exists(f):h.update(p.encode());h.update(open(f,'rb').read())
  return h.hexdigest()[:16]
@functools.lru_cache(None)
def feat_hash(tid):
  """content of the track's features (st json) + identity of its audio (size, mtime): a vocfix/re-prep changes the key"""
  h=hashlib.sha1();j=os.path.join(HERE,'st',f'{tid}.json');w=os.path.join(HERE,'st',f'{tid}.wav');ng=os.path.join(HERE,'st',f'{tid}.nudge.json')
  if os.path.exists(j):h.update(open(j,'rb').read())
  if os.path.exists(ng):h.update(open(ng,'rb').read())
  if os.path.exists(w):s=os.stat(w);h.update(f'{s.st_size}:{int(s.st_mtime)}'.encode())
  return h.hexdigest()[:16]
def _nudge_for(ids,nudge):
  try:N=json.load(open(nudge if os.path.isabs(nudge) else os.path.join(HERE,nudge)))
  except Exception:N={}
  return {i:N.get(i,{}) for i in sorted(ids)}

# ---------- clip construction (pure; unit-tested) ----------
def _sh_pts(pts,s0):return [[p[0]-s0,*p[1:]] for p in pts]
def clip_bounds(M,i,pre=PRE,post=POST):
  """[start-PRE, end+POST), clamped so no third deck sounds: after the previous blend ends (plus its echo tail) and before the
  next one starts. The release tests index decks by transition (trans k = decks[k] -> decks[k+1]), so a clip holds exactly A and B."""
  t=M['trans'][i];s0,s1=int(t['start_bar'])-pre,int(t['end_bar'])+post
  if i>0:
    p=M['trans'][i-1];tail=4 if p.get('echo_out') else 0;s0=max(s0,int(round(p['end_bar']))+tail)
  if i+1<len(M['trans']):s1=min(s1,int(M['trans'][i+1]['start_bar']))
  return s0,s1
def crop_decks(M,s0,s1):
  """[(abs_deck, j0)]: each deck sounding in [s0,s1) cropped to it; abs_deck keeps absolute bars (what engine.render_deck needs)"""
  out=[]
  for d in M['decks']:
    if d.get('acap') or d['end_bar']<=s0 or d['start_bar']>=s1:continue
    j0=int(max(0,s0-d['start_bar']));j1=int(min(len(d['full_map']),s1-d['start_bar']));dd=copy.deepcopy(d)
    cut_end=j1<len(d['full_map'])
    dd['full_map']=d['full_map'][j0:j1];dd['start_bar']=d['start_bar']+j0;dd['end_bar']=dd['start_bar']+len(dd['full_map'])
    dd['map']=dd['full_map'][:1]+dd['full_map'][-1:]
    if dd.get('ib'):dd['ib']=dict(dd['ib'],k0=dd['ib']['k0']-j0,k1=dd['ib']['k1']-j0)  # deck-relative indices follow the crop (blend_bench)
    if cut_end:dd.pop('echo_out',None)  # its echo belongs to a later exit outside the clip
    out.append((dd,j0))
  return out
def shift_meta(M,i,decks,s0,s1):
  """clip meta in clip bars (0 = s0) with only transition i (neighbours' audio stays, their checks belong to their own clip)"""
  D=[]
  for d,_ in decks:
    e=copy.deepcopy(d);e['start_bar']=d['start_bar']-s0;e['end_bar']=d['end_bar']-s0
    e['auto']={k:_sh_pts(v,s0) for k,v in (d.get('auto') or {}).items()}
    if e.get('dswap'):e['dswap']=dict(e['dswap'],bar=e['dswap']['bar']-s0)
    D.append(e)
  t=copy.deepcopy(M['trans'][i])
  for k in ('start_bar','end_bar','swap_bar','high_bar'):
    if t.get(k) is not None:t[k]=t[k]-s0
  t['xfader']=_sh_pts(t['xfader'],s0)
  if t.get('bass_swap'):t['bass_swap']=[x-s0 for x in t['bass_swap']]
  ids=[d['id'] for d in D];plan=[p for p in M.get('plan',[]) if p.get('id') in ids]
  return dict(engine=M.get('engine'),eq_mode=M.get('eq_mode'),decks=D,trans=[t],fx=[],plan=plan,bar_sec=M['bar_sec'],
    len_sec=(s1-s0)*M['bar_sec'],clip=dict(trans=i,s0=s0,s1=s1,a=t['a'],b=t['b']))
def clip_key(cm,gain,nudge):
  ids=sorted({d['id'] for d in cm['decks']})
  core=dict(decks=[{k:v for k,v in d.items() if k not in('label',)} for d in cm['decks']],trans={k:v for k,v in cm['trans'][0].items() if k not in('notes','tech')},
    gain=float(gain),nudge=_nudge_for(ids,nudge),feat={i:feat_hash(i) for i in ids},code=code_hash(),pre_post=(PRE,POST),
    env={k:os.environ.get(k) for k in ('BLEND_LOCK','FINE_LOCK','BAR_RESYNC','LX_PHASE','LX_TRIM','LX_TRIM_DB')})
  return hashlib.sha1(json.dumps(core,sort_keys=True,default=float).encode()).hexdigest()[:20]

# ---------- render ----------
def render_clip(M,i,gain,nudge,name):
  """returns (clip_meta, seconds). Writes src2/<name>_meta.json, _raw.wav, _master.wav, .mp3"""
  import numpy as np,soundfile as sf
  os.environ['NUDGE']=nudge;sys.path.insert(0,HERE);os.chdir(HERE)
  import engine
  from engine import BS,SR
  t0=time.time();s0,s1=clip_bounds(M,i);dk=crop_decks(M,s0,s1);n=int(round((s1-s0)*BS));mix=np.zeros((n,2),np.float32)
  for d,_ in dk:
    y=engine.render_deck(d);o=int(round((d['start_bar']-s0)*BS));m=max(0,min(len(y),n-o))
    if o<0:y=y[-o:];m=min(len(y),n);o=0
    mix[o:o+m]+=y[:m]
  for k in list(engine._cache):engine._cache[k]['st'].clear()
  cm=shift_meta(M,i,dk,s0,s1);raw=f'{name}_raw.wav';sf.write(raw,mix,SR,subtype='FLOAT')
  json.dump(cm,open(f'{name}_meta.json','w'),default=float)
  r=subprocess.run(['bash',os.path.join(ROOT,'src/master.sh'),raw,f'{name}.mp3',str(gain),f'{name}_master.wav'],capture_output=True,text=True,
    env=dict(os.environ,DJ_NO_BACKUP='1'))
  if r.returncode:raise RuntimeError('master.sh failed: '+r.stderr[-300:])
  return cm,time.time()-t0

# ---------- checks (child process: checks.py reads its config from env at import) ----------
def _run_checks(name):
  sys.path[:0]=[HERE,os.path.join(ROOT,'src/tests'),os.path.join(ROOT,'src/build_qa')];os.chdir(HERE)
  import importlib,traceback
  import checks as C
  out=[];T=None
  for mod,fn in TESTS:
    try:
      m=importlib.import_module(mod);f=getattr(m,fn);import inspect
      if 'T' in inspect.signature(f).parameters:
        if T is None:T=C.transitions()
        f(T)
      else:f()
      out.append(dict(test=fn,status='pass'))
    except AssertionError as e:
      msg=str(e)[:600]
      if any(g in msg for g in SIZE_GUARDS) and fn=='test_mixdown_beats_aligned_every_overlap_bar':
        # same shared functions as the test, minus its whole-mix size guard
        R=C.bar_alignment_report();bad=C.alignment_failures(R)
        out.append(dict(test=fn,status='fail' if bad else 'pass',msg=str(bad[:5])[:600] if bad else ''))
      else:out.append(dict(test=fn,status='fail',msg=msg))
    except BaseException as e:
      if type(e).__name__=='Skipped':out.append(dict(test=fn,status='skip',msg=str(e)[:200]));continue
      out.append(dict(test=fn,status='error',msg=f'{type(e).__name__}: {e}'[:400]))
  print('@@JSON@@'+json.dumps(out,default=str))

def check_clip(name,nudge):
  """guardrails.py (all fail-checks, per-deck renders) + blend-local release tests on the clip build"""
  t0=time.time();env=dict(os.environ,NUDGE=nudge,MIX_SRC=HERE,MIX_NAME=name,MIX_WAV=os.path.join(HERE,f'{name}_master.wav'),
    MIX_MP3=os.path.join(HERE,f'{name}.mp3'),MIX_DIAG='0',PYTHONWARNINGS='ignore')
  gdir=os.path.join(HERE,f'{name}_guard');os.makedirs(gdir,exist_ok=True)
  g=subprocess.run([sys.executable,os.path.join(ROOT,'src/guardrails.py'),'--src',HERE,'--name',name,'--mp3',f'{name}.mp3','--nudge',nudge,'--out',gdir],
    capture_output=True,text=True,cwd=HERE,env=env)
  G=json.load(open(f'{gdir}/guardrails.json')) if os.path.exists(f'{gdir}/guardrails.json') else dict(error=g.stderr[-400:])
  tg=time.time()-t0
  p=subprocess.run([sys.executable,os.path.abspath(__file__),'_check',name],capture_output=True,text=True,cwd=HERE,env=env)
  js=[l for l in p.stdout.splitlines() if l.startswith('@@JSON@@')]
  P=json.loads(js[-1][8:]) if js else [dict(test='_runner',status='error',msg=p.stderr[-400:])]
  return G,P,tg,time.time()-t0-tg

def verdict(G,P):
  gf=[dict(check=f['check'],t=f.get('t'),msg=f.get('msg','')[:200]) for f in G.get('failures',[])] if 'error' not in G else [dict(check='guardrails_error',msg=G['error'])]
  pf=[dict(check=x['test'],msg=x.get('msg','')[:300]) for x in P if x['status'] in('fail','error')]
  blend=[f for f in gf+pf if f['check'] not in MIX_LEVEL];mix=[f for f in gf+pf if f['check'] in MIX_LEVEL]
  return dict(ok=not blend,blend_fails=blend,mix_level=mix,n_tests=len(P),
    n_skip=sum(x['status']=='skip' for x in P),warnings=[w['check'] for w in G.get('warnings',[])])

def gate_blend(M,i,gain,nudge,use_cache=True,keep=False):
  s0,s1=clip_bounds(M,i);dk=crop_decks(M,s0,s1);cm=shift_meta(M,i,dk,s0,s1);key=clip_key(cm,gain,nudge)
  cf=os.path.join(CACHE,key+'.json')
  if use_cache and os.path.exists(cf):
    r=json.load(open(cf));r['cached']=True;return r
  os.makedirs(os.path.join(HERE,CLIPS),exist_ok=True);name=f'{CLIPS}/bg_{key}_c'
  _,rs=render_clip(M,i,gain,nudge,name);G,P,tg,tp=check_clip(name,nudge)
  t=M['trans'][i];r=dict(key=key,trans=i,a=t['a'],b=t['b'],mix_t=f"{int(t['start_bar']*M['bar_sec']//60)}:{int(t['start_bar']*M['bar_sec']%60):02d}",
    window=(M.get('plan') or [{}]*(i+1))[i].get('out_win') if len(M.get('plan') or [])>i else None,clip_bars=[s0,s1],gain=gain,
    secs=dict(render=round(rs,1),guardrails=round(tg,1),tests=round(tp,1),total=round(rs+tg+tp,1)),code=code_hash(),**verdict(G,P),
    guard_fails=G.get('by_check'),tests=P,cached=False)
  json.dump(r,open(cf,'w'),indent=1,default=str)
  if not keep:
    for f in glob.glob(os.path.join(HERE,name+'*')):
      if os.path.isdir(f):
        import shutil;shutil.rmtree(f,ignore_errors=True)
      else:os.remove(f)
  return r

def proven_bad_windows(code=None):
  """{(a, b, tuple(out_win))} for every cached clip that failed a blend check under the current check code (plan_search.bad_windows /
  repair ctx.badwin can union this in when BLEND_AUDIO_GATE=1). Mix-level fails do not ban a window."""
  code=code or code_hash();out=set()
  for f in glob.glob(os.path.join(CACHE,'*.json')):
    try:r=json.load(open(f))
    except Exception:continue
    if r.get('code')==code and not r.get('ok') and r.get('window'):out.add((r['a'],r['b'],tuple(r['window'])))
  return out

def gate_dry_plan(plan,gain,nudge=None,jobs=3,tag='bgp'):
  """plan (list of steps) -> (all blends pass, {i: result}). For plan_search's verify loop and repair's per-try check:
  unchanged blends hit the cache, so a repair try costs only its changed blends."""
  f=os.path.join(HERE,f'_bg_{tag}_plan.json');json.dump(plan,open(f,'w'))
  try:M=dry_meta(f,tag)
  finally:
    if os.path.exists(f):os.remove(f)
  R=gate_plan(M,gain,nudge or os.environ.get('NUDGE','nudge08_r9c.json'),jobs=jobs,log=lambda r:None)
  return all(r['ok'] for r in R.values()),R

def dry_meta(plan_path,tag='bg'):
  out=f'_bg_{tag}';r=subprocess.run([sys.executable,'mix_simple.py','--plan',plan_path,'--out',out,'--dry'],cwd=HERE,capture_output=True,text=True)
  if r.returncode:raise RuntimeError('mix_simple --dry failed: '+(r.stderr.strip().splitlines() or ['?'])[-1])
  return json.load(open(os.path.join(HERE,out+'_dry_meta.json')))

def gate_plan(M,gain,nudge,trans=None,jobs=1,use_cache=True,log=print):
  idx=list(range(len(M['trans']))) if trans is None else list(trans);res={}
  if jobs<=1:
    for i in idx:
      res[i]=gate_blend(M,i,gain,nudge,use_cache);r=res[i]
      (print if log is print else (lambda *a,**k:None))(f"[{time.strftime('%H:%M:%S')}] blend {i} {r['a']}>{r['b']} @{r['mix_t']}: {'PASS' if r['ok'] else 'FAIL '+str(sorted({f['check'] for f in r['blend_fails']}))}"
          f"{' mix-level '+str(sorted({f['check'] for f in r['mix_level']})) if r['mix_level'] else ''} ({r['secs']['total']}s{' cached' if r['cached'] else ''})",flush=True)
  else:
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(jobs) as ex:
      fut={i:ex.submit(gate_blend,M,i,gain,nudge,use_cache) for i in idx}
      for i in idx:
        r=res[i]=fut[i].result()
        print(f"[{time.strftime('%H:%M:%S')}] blend {i} {r['a']}>{r['b']} @{r['mix_t']}: {'PASS' if r['ok'] else 'FAIL '+str(sorted({f['check'] for f in r['blend_fails']}))}"
              f"{' mix-level '+str(sorted({f['check'] for f in r['mix_level']})) if r['mix_level'] else ''} ({r['secs']['total']}s{' cached' if r['cached'] else ''})",flush=True)
  return res

if __name__=='__main__':
  if len(sys.argv)>2 and sys.argv[1]=='_check':_run_checks(sys.argv[2]);sys.exit()
  ap=argparse.ArgumentParser();ap.add_argument('--meta');ap.add_argument('--plan');ap.add_argument('--trans');ap.add_argument('--gain',type=float,required=True)
  ap.add_argument('--nudge',default=os.environ.get('NUDGE','nudge08_r9c.json'));ap.add_argument('--json');ap.add_argument('--jobs',type=int,default=1)
  ap.add_argument('--no-cache',action='store_true')
  A=ap.parse_args();os.chdir(HERE)
  M=json.load(open(A.meta)) if A.meta else dry_meta(A.plan)
  tr=[int(x) for x in A.trans.split(',')] if A.trans else None
  R=gate_plan(M,A.gain,A.nudge,tr,A.jobs,not A.no_cache)
  if A.json:json.dump({str(k):v for k,v in R.items()},open(A.json,'w'),indent=1,default=str)
  bad=[i for i,r in R.items() if not r['ok']];print('GATE',('ALL PASS' if not bad else f'FAIL blends {bad}'),'of',len(R));sys.exit(1 if bad else 0)
