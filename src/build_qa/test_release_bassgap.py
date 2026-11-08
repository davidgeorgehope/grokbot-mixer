"""BASSGAP (the listener 2026-11-02 19:33 ET): no low-end (<150 Hz) hole >GAP_DB under the groove for >1 bar inside a blend, unless the sources break down there."""
import os,sys,json
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'../../src2'))
import bassgap as G
R=os.path.join(os.path.dirname(__file__),'../..')
def test_no_bass_gap_in_overlaps():
  n=os.environ.get('MIX_NAME');w=os.environ.get('MIX_WAV')
  if not n or not w or not os.path.exists(w):
    import pytest;pytest.skip('MIX_NAME/MIX_WAV not set')
  os.chdir(os.path.join(R,'src2'));M=json.load(open(f'{n}_meta.json'))
  K=json.load(open(os.path.join(R,'eval/bassgap_known.json'))).get(n,[]);bad=[b for b in G.check(M,w) if [b[0],b[1]] not in K];assert not bad,f'bass gaps (trans,mix bar,bars): {bad}'
