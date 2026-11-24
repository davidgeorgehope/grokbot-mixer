"""n1_grid_align: a thin intro that is consistently ~19 ms early vs a drop-locked grid
gets a per-bar source offset; the drop is left alone. Uses the same metric as guardrails N1.
Does not change N1_ms or any other threshold.
"""
import os,sys,json,shutil
import numpy as np
import pytest

HERE=os.path.dirname(os.path.abspath(__file__))
SRC2=os.path.join(HERE,'..','..','src2')
sys.path.insert(0,SRC2)
import n1_grid_align as A

def test_when_my_love_intro_is_early_drop_is_on_grid():
  wav=os.path.join(SRC2,'st','7Itbo72XEz4.wav')
  if not os.path.exists(wav):
    pytest.skip('When My Love source not on this box')
  cwd=os.getcwd();os.chdir(SRC2)
  try:
    rows=A.bar_rows('7Itbo72XEz4',bars=list(range(15,40)))
    intro=[r['p16'] for r in rows if 16<=r['bar']<=23 and r['p16'] is not None]
    drop=[r['p16'] for r in rows if 32<=r['bar']<=39 and r['p16'] is not None]
    assert intro and float(np.median(intro))<=-14, intro  # ~-19 ms, the N1 fail
    assert drop and abs(float(np.median(drop)))<10, drop  # drop already passes N1
    n=A.nudges_for('7Itbo72XEz4')
    assert all(abs(n[k]-19.1)<3 for k in range(16,24)), n
    assert all(k not in n for k in range(32,40)), n
    after=A.bar_rows_nudged('7Itbo72XEz4',n,bars=list(range(16,24)))
    xs=[r['p16'] for r in after if r['p16'] is not None]
    assert xs and all(abs(x)<10 for x in xs), after
  finally:
    os.chdir(cwd)

def test_synthetic_early_intro_is_nudged_drop_is_not(tmp_path):
  # 16-bar two-step intro 19 ms early, then 16 bars on the grid
  from test_halfbeat import drums,grid,SR,BAR
  early=0.019
  d0=0.5
  y_in=drums(nbars=16,t0=d0-early,two_step=True,seed=1)
  y_drop=drums(nbars=16,t0=d0+16*BAR,two_step=True,seed=2)
  n=max(len(y_in),len(y_drop));y=np.zeros(n,np.float32)
  y[:len(y_in)]+=y_in;y[:len(y_drop)]+=y_drop
  g=grid(d0,32)
  st=tmp_path/'st';st.mkdir()
  import soundfile as sf
  sf.write(st/'syn.wav',np.stack([y,y],1),SR,subtype='FLOAT')
  json.dump(g,open(st/'syn.json','w'))
  # measure from tmp as src
  n=A.nudges_for('syn',g=g,src=str(tmp_path))
  intro=[n.get(k,0) for k in range(0,16)]
  drop=[n.get(k,0) for k in range(16,32)]
  # not every intro bar may be confident; the mid-intro run should be ~+19
  mid=[n[k] for k in range(4,12) if k in n]
  assert mid and abs(float(np.median(mid))-19)<8, (n, mid)
  assert all(abs(v)<A.MIN_MS for v in drop), (drop,n)
