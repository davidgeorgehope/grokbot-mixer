"""Song-structure planning + gradual outgoing tails (the listener 2026-10-31: Mix 05 blends 'start off good then quickly and abruptly fade out').
Mix 05 measured: outgoing -6 dB right at the bass swap, -20 dB ~10 bars later, steepest -7..-11 dB/bar in 18/19 blends,
and the outgoing usually left before its outro (e.g. Breathe out at bar 96 = its breakdown, 65 bars of music unplayed)."""
import os,sys,json,numpy as np,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C
sys.path.insert(0,C.SRC);import sections as S
KNOWN={'F1NCnCxyhqc':dict(drop1=40,breakdown=88,drop2=120),'NaY3x3GRDF4':dict(drop1=64,breakdown=104,drop2=144,outro_start=168),
       'OPuVVhbkicU':dict(drop1=48,breakdown=96,drop2=128),'2s3M6oX2lfo':dict(drop1=32,breakdown=96,drop2=128,outro_start=144)}
@pytest.mark.parametrize('b',sorted(KNOWN))
def test_sections_known_tracks(b):
  if not os.path.exists(f'{C.SRC}/st/{b}.json'):pytest.skip('grid missing')
  s=S.detect(json.load(open(f'{C.SRC}/st/{b}.json')))
  for k,v in KNOWN[b].items():assert abs(s[k]-v)<=8,(b,k,s[k],v)
  assert s['drop1']<=s['outro_start']<s['music_end'] and s['music_end']-s['outro_start']>=16
def _meta():
  for p in (f'{C.SRC}/{C.NAME}_meta.json',f'{C.SRC}/{C.NAME}_dry_meta.json'):
    if os.path.exists(p):
      M=json.load(open(p))
      if not M.get('eq_mode',{}).get('STRUCT'):pytest.skip('pre-structure build')
      return M
  pytest.skip('mix meta missing')
def _decks(M,i):return M['decks'][i],M['decks'][i+1]
def test_plan_respects_outro_and_intro():
  M=_meta();T=M['trans'];out_ok=drop_ok=0
  for i,t in enumerate(T):
    A,B=_decks(M,i);X=int(t['end_bar']-t['start_bar']);sa,sb=S.get(t['a'],C.SRC),S.get(t['b'],C.SRC)
    out_ok+=A['full_map'][-1][0]+1>=sa['outro_start']
    fb=[s for s,_ in B['full_map']];drop_ok+=X<len(fb) and abs(fb[X]-sb['drop1'])<=8
  assert out_ok>=0.7*len(T),f'outgoing reached its outro in {out_ok}/{len(T)} blends'
  assert drop_ok>=0.5*len(T),f'incoming drop landed at the blend end in {drop_ok}/{len(T)} blends'
def test_blend_lengths_vary():
  M=_meta();L=[int(t['end_bar']-t['start_bar']) for t in M['trans']];assert len(set(L))>=2 and max(L.count(x) for x in set(L))<=0.8*len(L),L
def test_outgoing_fader_tail_is_gradual():
  """outgoing crossfader level: never more than 3 dB/bar while above -24 dB, and still above -20 dB for >=35% of the blend after the bass swap"""
  M=_meta();bad=[]
  for t in M['trans']:
    s,e=t['start_bar'],t['end_bar'];X=e-s;xs=np.array(t['xfader']);bars=np.arange(s,e+1e-9,1.0)
    g=20*np.log10(np.cos(np.interp(bars,xs[:,0],xs[:,1])*np.pi/2)+1e-9);d=np.diff(g)
    steep=[float(x) for x,v in zip(d,g[1:]) if v>-24 and x<-3]
    sw=(t['bass_swap'][1] if t.get('bass_swap') else s+0.35*X);ride=float(np.sum(g[bars>=sw]>-20))
    if steep or ride<0.35*X-1:bad.append((t['a'],s,steep[:3],ride,X))
  assert not bad,bad
def test_outgoing_audio_tail_never_drops_abruptly():
  """what the mix does to the outgoing deck (crossfader + bass/high swaps, measured as rendered minus the same bars dry) never
  takes more than 6 dB off in one bar while the deck is still within 20 dB of its pre-blend level. The track's own outro
  dynamics are reported, not gated. Needs stems (restore_audio.py); runs at render time."""
  M=_meta();os.environ.setdefault('NUDGE',os.path.join(C.SRC,'nudge.json'))
  if not all(os.path.exists(f"{C.SRC}/st/{d['id']}.wav") for d in M['decks']):pytest.skip('stems not restored')
  cwd=os.getcwd();os.chdir(C.SRC)
  try:
    import engine as E;BS=E.BS;bad=[]
    for i,t in enumerate(M['trans']):
      A=M['decks'][i];y=E.render_deck(A);dry=E.render_deck(dict(A,auto={}));d0=A['start_bar']
      db=lambda z,k:10*np.log10(np.mean(z[int((k-d0)*BS):int((k-d0+1)*BS)]**2)+1e-12)
      ks=range(int(t['start_bar']),int(t['end_bar']));G=[db(y,k)-db(dry,k) for k in ks];ref=db(y,t['start_bar']-1);L=[db(y,k)-ref for k in ks]
      st=[round(float(G[k]-G[k-1]),1) for k in range(1,len(G)) if L[k-1]>-20 and G[k]-G[k-1]<-6 and L[k]-L[k-1]<-6]  # both: what we take off AND what is heard (a bass-less fill bar makes the ratio alone jump)
      if st:bad.append((t['a'],t['start_bar'],st))
  finally:os.chdir(cwd)
  assert not bad,bad
