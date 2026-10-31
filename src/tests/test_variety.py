"""Variety + ratings scale (the listener 2026-10-31: Mix 05 blends all felt the same, 3/5 = mediocre, 'echoey').
Unit tests always run; mix checks apply to builds stamped eq_mode.VARIETY (Mix 06+)."""
import os,sys,json,pytest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import checks as C
sys.path.insert(0,C.SRC);import techniques as TQ
def test_ratings_scale_5_good_4_ok_3_bad():
  assert TQ.pref_score(5)>0 and TQ.pref_score(4)==0 and TQ.pref_score(3)<0 and TQ.pref_score(1)<TQ.pref_score(3)
  assert [TQ.label(r) for r in (5,4,3.5,3,1)]==['good','ok','bad','bad','bad']
def test_pair_prefs_3_is_penalised_not_neutral():
  P=json.load(open(f'{C.SRC}/pair_prefs.json'));threes=[k for k,v in P.items() if not k.startswith('_') and v==3]
  assert all(TQ.pref_score(P[k])<0 for k in threes)
def test_diversity_rule():
  sc=[{'long_blend':0,'short_blend':1,'slow_bass_swap':2,'echo_out':0.5}]*20;seq=TQ.pick(sc,20)
  assert max(seq.count(t) for t in set(seq))<=8 and seq.count('echo_out')<=TQ.ECHO_MAX
  assert not any(seq[i]==seq[i+1]==seq[i+2] for i in range(len(seq)-2))
def _meta():
  p=f'{C.SRC}/{C.NAME}_meta.json'
  if not os.path.exists(p):pytest.skip('mix meta missing')
  M=json.load(open(p))
  if not M.get('eq_mode',{}).get('VARIETY'):pytest.skip('pre-variety build')
  return M
def test_outgoing_repeat_under_variety_rule():
  """the 32-bar outgoing repeat (last 16-bar phrase played 3x) is a normal technique (the listener 2026-10-31 12:30: loops are fine),
  under the variety rule: on <=40% of blends and never 3 blends in a row"""
  M=_meta();r=[]
  for d in M['decks'][:-1]:
    s=[a for a,_ in d['full_map']];j=[k for k in range(1,len(s)) if s[k]<s[k-1]];r.append(len([k for k in j if k>len(s)-40])>1)
  assert sum(r)<=TQ.MAXSHARE*len(r),f'{sum(r)}/{len(r)} blends repeat the outgoing phrase'
  assert not any(all(r[i:i+3]) for i in range(len(r)-2)),r
def test_echo_outs_capped():
  M=_meta();n=sum(bool(t.get('echo_out')) for t in M['trans']);assert n<=TQ.ECHO_MAX
