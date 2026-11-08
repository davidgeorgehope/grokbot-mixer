import os, sys, json, numpy as np, pytest
import checks as C
import seesaw as S

def _current_meta():
  """the build under test (MIX_NAME, set by the build loops / deliver). Unset = no build under test: skip instead of judging the stale 'mixS' default"""
  import os,pytest
  n=os.environ.get('MIX_NAME');p=f'/workspace/mixes/src2/{n}_meta.json'
  if not n or not os.path.exists(p):pytest.skip('MIX_NAME not set: no build under test')
  return json.load(open(p))


def test_no_seesaw_between_decks():
  bad=[r for r in S.check(_current_meta()) if r['fails']]
  assert not bad,'\n'.join(f"{int(r['t']//60)}:{int(r['t']%60):02d} {r['a']}>{r['b']} {r['fails']} rise {r['out_rise']} wob {r['wobble']} r {r['anti_r']}" for r in bad)

