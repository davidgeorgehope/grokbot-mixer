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
  p=os.path.join(os.path.dirname(__file__),'fixtures',f'{b}.grid.json')
  s=S.detect(json.load(open(p)))
  for k,v in KNOWN[b].items():assert abs(s[k]-v)<=8,(b,k,s[k],v)
  assert s['drop1']<=s['outro_start']<s['music_end'] and s['music_end']-s['outro_start']>=16
def _pinned(M):
  """outgoing ids whose blend the plan pins to its original fader ('fade' key): only the listener's 5/5-rated pairs (pair_prefs.json), kept bit-identical on request"""
  PR=json.load(open(f'{C.SRC}/pair_prefs.json'));ids=[p['id'] for p in M['plan']]
  return {p['id'] for i,p in enumerate(M['plan']) if 'fade' in p and i+1<len(ids) and PR.get(f"{p['id']}>{ids[i+1]}",0)>=5}

def test_pin_exemption_only_for_5_rated_pairs(monkeypatch):
  """a 'fade' pin on a pair the listener did not rate 5 is not exempt"""
  monkeypatch.setattr(C,'SRC',os.path.join(os.path.dirname(__file__),'fixtures'))
  M=dict(plan=[dict(id='j9AuFRpLk7U',fade='lin'),dict(id='cxS6yd0UAxw'),dict(id='x',fade='lin'),dict(id='y')])
  assert _pinned(M)=={'j9AuFRpLk7U'}
