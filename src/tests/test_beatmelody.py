"""Beats -> melody-only blends (the listener 2026-11-02): BM1 detector, incoming beat loop (ib) keeps the beat continuous,
drum swap on a phrase line (dswap) is a drums-only cut that TAIL allows while a full-mix abrupt fade still blocks."""
import os,sys,json,copy,numpy as np,pytest
SRC=os.environ.get('BM_SRC','/workspace/mixes/src2');sys.path.insert(0,SRC)
META=f'{SRC}/mix05v8_meta.json';PAIR=('MoYkYkoeb84','7Itbo72XEz4')  # Mix 05 v2 18:04: MoYk drums over 7Itb's beatless intro
@pytest.fixture
def M():
  if not os.path.exists(META):pytest.skip('mix05v8 meta missing')
  cwd=os.getcwd();os.chdir(SRC);yield json.load(open(META));os.chdir(cwd)
def _i(M):return next(i for i,t in enumerate(M['trans']) if (t['a'],t['b'])==PAIR)
def _crop(M,i,pre=8,post=8):
  """two decks around blend i, cropped (render speed); ib indices follow the crop like blend_bench.render"""
  t=M['trans'][i];s0,s1=int(t['start_bar'])-pre,int(t['end_bar'])+post;out=[]
  for d in M['decks'][i:i+2]:
    j0=max(0,s0-d['start_bar']);j1=min(len(d['full_map']),s1-d['start_bar']);dd=copy.deepcopy(d);dd['full_map']=d['full_map'][j0:j1];dd['start_bar']=d['start_bar']+j0
    if dd.get('ib'):dd['ib']=dict(dd['ib'],k0=max(0,dd['ib']['k0']-j0),k1=dd['ib']['k1']-j0)
    out.append(dd)
  return out
def _stems(*ids):
  if not all(os.path.exists(f'{SRC}/st/{b}.dnb.wav') and os.path.exists(f'{SRC}/st/{b}.wav') for b in ids):pytest.skip('drums+bass stems not cached (python3 beatstem.py <id>)')
def test_bm1_detector_flags_beats_into_melody(M):
  import beatmelody as BM
  R=BM.bm1(M);i=_i(M);hit=[r for r in R if r['trans']==i]
  assert hit and max(r['bars'] for r in hit)>=8,R
  M2=copy.deepcopy(M);BM.apply(M2,i,'ib');assert not [r for r in BM.bm1(M2) if r['trans']==i]  # beat loop fills the gap
  # melody over melody with no outgoing drums is never flagged
  M3=copy.deepcopy(M);A=M3['decks'][i];BM._D[(A['id'],'.')]=(BM.drums(A['id'])[0],np.zeros_like(BM.drums(A['id'])[1]),np.ones_like(BM.drums(A['id'])[2]))
  try:assert not [r for r in BM.bm1(M3) if r['trans']==i]
  finally:BM._D.pop((A['id'],'.'))
def test_ib_render_keeps_beats_continuous(M):
  _stems(PAIR[1]);import beatmelody as BM,engine as E
  i=_i(M);M2=copy.deepcopy(M);BM.apply(M2,i,'ib');B=M2['decks'][i+1];k1=B['ib']['k1']
  d=copy.deepcopy(B);d['full_map']=d['full_map'][:k1+8];d['auto']={}  # deck alone, no crossfader: what the ib layer adds
  y=E.render_deck(d);y0=E.render_deck(dict(d,ib=None));BS=E.BS
  beat=E._bars(E.track(B['id']),[s for s,_ in d['full_map']],E.track(B['id'])['st']['beat'],len(y))
  db=lambda z,k:10*np.log10(np.mean(z[int(k*BS):int((k+1)*BS)]**2)+1e-12)
  real=np.median([db(beat,k) for k in range(k1,k1+4)])
  lay=[db(y-y0,k) for k in range(1,k1)]  # loop layer per bar under the beatless intro
  assert min(lay)>real-6,(round(real,1),[round(x,1) for x in lay])  # beat present every bar, near the real beat level (static trim)
  assert max(lay)<real+6
  hand=[db(y,k) for k in range(k1-2,k1+3)];assert max(np.diff(hand))<6,hand  # no level jump at the handover
def test_dswap_is_not_a_full_mix_tail_fail(M):
  _stems(PAIR[0]);import beatmelody as BM,engine as E
  i=_i(M);M2=copy.deepcopy(M);BM.apply(M2,i,'dswap');A,B=_crop(M2,i);ds=A['dswap']
  M3=dict(M2,decks=[None]*i+[A,B]+[None]*(len(M2['decks'])-i-2))
  y=E.render_deck(A);mb=ds['bar']
  assert (mb-int(M2['trans'][i]['start_bar']))%4==0  # phrase line
  assert BM.tail_exempt(E,M3,i,mb,y)  # drums-only cut at the melody entry: allowed
  # same bar as a full-mix abrupt fade (crossfader cut to -40 dB in one bar, no dswap): still blocks
  F=copy.deepcopy(A);F.pop('dswap');F['auto']['gain']=[[p[0],p[1] if p[0]<mb else p[1]*0.01] for p in F['auto']['gain']]+[[mb-1e-3,next(q[1] for q in reversed(A['auto']['gain']) if q[0]<mb)]]
  F['auto']['gain'].sort();M4=dict(M3,decks=[None]*i+[F,B]+[None]*(len(M2['decks'])-i-2))
  assert not BM.tail_exempt(E,M4,i,mb,E.render_deck(F))
  F['dswap']=dict(ds);M5=dict(M3,decks=[None]*i+[F,B]+[None]*(len(M2['decks'])-i-2))
  assert not BM.tail_exempt(E,M5,i,mb,E.render_deck(F))  # dswap flag on top of a full-mix fade does not launder it
