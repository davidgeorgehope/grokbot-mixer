"""Demo A/B snippets for BM1 cases (beats -> melody-only), no full re-render: crop the two decks of one blend from a delivered
meta, apply a beatmelody option, render with engine.render_deck, master with ../src/master.sh. usage:
  NUDGE=... python3 bm_demo.py <meta.json> <trans index> <name>   -> deliver/ab/bm_<name>/{B_current,A_cut_on_melody_entry,C_ib_loop,AC_ib_plus_cut}.mp3"""
import sys,os,json,copy,subprocess,numpy as np,soundfile as sf
import engine as E,beatmelody as BM
R='/workspace/mixes';meta,i,name=sys.argv[1],int(sys.argv[2]),sys.argv[3];M0=json.load(open(meta));OUT=f'{R}/deliver/ab/bm_{name}';os.makedirs(OUT,exist_ok=True)
GAIN=os.environ.get('GAIN','9.3');PRE,POST=8,16
V=[('B_current','',"as delivered: outgoing beat fades gently over the incoming's beatless melody (family B, melody cross)"),
   ('A_cut_on_melody_entry','dswap','outgoing drums+bass cut over 1 bar on the phrase line nearest the incoming melody entry (family A)'),
   ('C_ib_loop','ib',"incoming's own drums+bass looped under its beatless intro, hands over to its real drums (family C)"),
   ('AC_ib_plus_cut','ib+dswap','hybrid: incoming beat loop + outgoing beat cut once the incoming is up')]
info=[]
for tag,mode,what in V:
  M=copy.deepcopy(M0);notes=[]
  if mode:
    try:notes=BM.apply(M,i,mode)
    except ValueError as ex:info.append(dict(file=None,variant=tag,skipped=str(ex)));continue
  t=M['trans'][i];s0,s1=int(t['start_bar'])-PRE,int(t['end_bar'])+POST;n=int(round((s1-s0)*E.BS));mix=np.zeros((n,2),np.float32)
  for d in M['decks'][i:i+2]:
    j0=max(0,s0-d['start_bar']);j1=min(len(d['full_map']),s1-d['start_bar']);dd=copy.deepcopy(d);dd['full_map']=d['full_map'][j0:j1];dd['start_bar']=d['start_bar']+j0
    if dd.get('ib'):dd['ib']=dict(dd['ib'],k0=max(0,dd['ib']['k0']-j0),k1=dd['ib']['k1']-j0)
    dd.pop('echo_out',None);y=E.render_deck(dd);o=int(round((dd['start_bar']-s0)*E.BS));m=min(len(y),n-o);mix[o:o+m]+=y[:m]
  raw=f'/tmp/bmx/{name}_{tag}_raw.wav';sf.write(raw,mix,E.SR,subtype='FLOAT')
  subprocess.run(['bash','../src/master.sh',raw,f'{OUT}/{tag}.mp3',GAIN,f'/tmp/bmx/{name}_{tag}_m.wav'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  st=s0*M['bar_sec'];BMr=[r for r in BM.bm1(M) if r['trans']==i]
  info.append(dict(file=f'{OUT}/{tag}.mp3',variant=tag,what=what,notes=notes,mix_start=f"{int(st//60)}:{int(st%60):02d}",blend=[t['start_bar'],t['end_bar']],bm1_left=[(r['t'],r['bars']) for r in BMr]))
  print(info[-1],flush=True)
json.dump(dict(meta=meta,trans=i,a=M0['trans'][i]['a'],b=M0['trans'][i]['b'],items=info),open(f'{OUT}/README.json','w'),indent=1)
