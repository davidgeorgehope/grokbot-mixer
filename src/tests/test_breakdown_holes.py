"""breakdown_holes (RCA 2026-11-24 fix 2): a track's own deep breakdown left solo is flagged; blended over or shallow it is not."""
import pathlib,sys,json,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'src2'))
import breakdown_holes as BH

def lv(dip=-38.0):
  """body -18; 16-bar breakdown at -30 (12 dB under: an excused own breakdown) with a 3-bar dip (bars 107-109)"""
  a=[-40.0]*4+[-18.0]*196+[-40.0]*8
  for k in range(100,116):a[k]=-30.0
  for k in range(107,110):a[k]=dip
  return a
def deck(i,s,n,src0,gain):return dict(id=i,start_bar=s,end_bar=s+n,full_map=[[src0+k,'mix'] for k in range(n)],auto={'gain':gain},acap=False)

def test_mask_marks_deep_mid_track_breakdown_only():
  m=BH.track_mask(lv());assert m['deep'] and m['deep']<=set(range(107,110))
  assert not BH.track_mask(lv(dip=-30.0))['deep']   # 12 dB under body: guardrails excuse it as an own breakdown

def test_solo_exposure_is_flagged_and_blended_cover_is_not():
  A=deck('a',0,208,0,[[0,1.0],[180,1.0],[208,0.0]]);M=dict(decks=[A],bar_sec=1.379)
  X=BH.exposures(M,levels_of=lambda t:lv());assert [x[0] for x in X]==['E1-deep'] and 107<=X[0][4][0]<=109
  B=deck('b',90,40,0,[[90,1.0],[130,1.0]])   # another deck at full gain over the breakdown: not solo
  assert not BH.exposures(dict(decks=[A,B],bar_sec=1.379),levels_of=lambda t:lv() if t=='a' else [-18.0]*208)

def test_mix10_r5_hayling_hole_and_clean_r6c():
  src=pathlib.Path(__file__).resolve().parents[2]/'src2'
  r5,r6=src/'mix10_r5_meta.json',src/'mix10_r6_meta.json'
  if not (r5.exists() and r6.exists() and (src/'st'/'3cOEsXf-ic0.json').exists()):
    import pytest;pytest.skip('Mix 10 metas/features not on this box')
  X=[x for x in BH.exposures(json.load(open(r5)),src=str(src)) if x[0]=='E1-deep']
  assert [(x[1],round(x[2]*1.3793/60,1)) for x in X]==[('3cOEsXf-ic0',14.4)]
  assert not [x for x in BH.exposures(json.load(open(r6)),src=str(src)) if x[0]=='E1-deep']
