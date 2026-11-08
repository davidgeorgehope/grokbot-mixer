import os, sys, json, numpy as np, pytest
import checks as C
import techniques as TQ

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

