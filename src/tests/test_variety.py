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
  P=json.load(open(os.path.join(os.path.dirname(__file__),'fixtures','pair_prefs.json')));threes=[k for k,v in P.items() if not k.startswith('_') and v==3]
  assert all(TQ.pref_score(P[k])<0 for k in threes)
def test_diversity_rule():
  sc=[{'long_blend':0,'short_blend':1,'slow_bass_swap':2,'echo_out':0.5}]*20;seq=TQ.pick(sc,20)
  assert max(seq.count(t) for t in set(seq))<=8 and seq.count('echo_out')<=TQ.ECHO_MAX
  assert not any(seq[i]==seq[i+1]==seq[i+2] for i in range(len(seq)-2))
