"""2026-11-11: FADE=long exposed two checks that assumed the outgoing rides to the window end."""
import ast,sys
import numpy as np
sys.path.insert(0,'/workspace/mixes/src2')
import fade_long as F

def c2_half(rows, s, e, sw, refAh, xfader=None):
  """loaded from src/guardrails.py so the test and the check cannot drift."""
  src=open('/workspace/mixes/src/guardrails.py').read();mod=ast.parse(src)
  fn=next(n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name=='c2_half')
  ns={};exec(compile(ast.Module([fn],type_ignores=[]),'c2_half','exec'),ns);return ns['c2_half'](rows,s,e,sw,refAh,xfader)

def _x(b,X,solo=16):
  return F.xlong(b/X,X,solo=F.solo_bars(X,solo=solo))

def test_late_high_swap_centre_is_outside_x_window_on_long_16():
  """The old check used x at high_bar; X1 uses the centre (high_bar+2). On a 16-bar long fade that put a swap at x=0.90."""
  X=16;solo=F.solo_bars(X,solo=16)  # clipped to 0
  assert _x(12,X,solo=solo)<=0.9  # start looks legal
  assert _x(14,X,solo=solo)>0.9   # centre is not

def test_a_legal_high_swap_exists_on_typical_long_windows():
  for X,solo in ((16,0),(32,16),(32,8),(16,16)):
    s=F.solo_bars(X,solo=solo);c=F.exit_start(X,solo=s)
    ok=[h for h in range(4,X,4) if abs(h-c)>=4 and 0.1<=_x(h+2,X,solo=s)<=0.9]
    assert ok, (X,s,c)

def _xf(X,solo=0):
  """per-bar xfader points for a long fade (bar, x)."""
  return [[float(b),float(_x(b,X,solo=solo))] for b in range(0,X+1)]

def test_c2_half_ignores_the_incoming_solo():
  # 32-bar long window, solo 16: designed outgoing drops below -10 dB during the exit (~bar 8-16),
  # first half is the plateau, even though the rendered outgoing is gone by bar 20.
  rows=[dict(bar=b,Ah=(0 if b<16 else -25),Bh=0) for b in range(32)]
  half=c2_half(rows,0,32,8,0,_xf(32,16))
  assert half[-1]['bar']<16 and not [r for r in half if r['Ah']<-10]

def test_c2_half_still_flags_an_early_drop_in_the_overlap():
  # tail-style xfader rides to the window end; outgoing audio drops at bar 4 of 16 — still in the first half
  rows=[dict(bar=b,Ah=(0 if b<4 else -20),Bh=0) for b in range(16)]
  xf=[[float(b),b/16] for b in range(17)]  # linear 0->1, outgoing still above -10 dB at bar 8
  half=c2_half(rows,0,16,6,0,xf)
  assert any(r['Ah']<-10 for r in half) and half[0]['bar']==0

def test_c2_half_falls_back_to_window_when_no_xfader():
  rows=[dict(bar=b,Ah=-30,Bh=-30) for b in range(16)]
  half=c2_half(rows,0,16,6,0,None)
  assert [r['bar'] for r in half]==list(range(0,8))
