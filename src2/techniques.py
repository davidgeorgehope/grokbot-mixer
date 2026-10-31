"""Ratings scale + transition-technique menu with a diversity rule (the listener 2026-10-31: '5/5 is good, 3/5 is mediocre').
pref_score: 5 good (+1), 4.5 (+0.5), 4 OK (0), 3 or below bad (-1, -1.5 at 2, -2 at 1). Planner cost subtracts PREFW*pref_score.
MENU: techniques chosen per pair; pick() enforces: no technique on >MAXSHARE of blends, never 3 in a row,
echo-outs <= ECHO_MAX per mix and >=4 blends apart, outgoing-phrase loops (repeat) <= LOOP_MAX per mix."""
import os
GOOD,OK=5.0,4.0
def pref_score(r):
  r=float(r)
  if r>=OK:return (r-OK)/(GOOD-OK)
  return -1.0-0.5*max(0.0,3.0-r) if r<=3 else -(OK-r)  # 3.5 -> -0.5
def label(r):return 'good' if r>=GOOD else 'ok' if r>=OK else 'bad'
# name: blend bars, bass-swap bars, high-swap offset, extras (engine support flag)
MENU={
 'long_blend':     dict(X=32,swap=2,hofs=4,supported=True),
 'short_blend':    dict(X=16,swap=1,hofs=2,supported=True),
 'slow_bass_swap': dict(X=32,swap=8,hofs=8,supported=True),
 'quick_cut':      dict(X=4,swap=0,hofs=0,phrase_cut=True,supported=False),
 'drop_on_drop':   dict(X=16,swap=1,hofs=0,align='drop',supported=False),
 'double_drop':    dict(X=32,swap=0,hofs=0,align='drop',both_bass=True,supported=False),
 'filter_sweep':   dict(X=16,swap=2,hofs=4,hpf_out=True,supported=False),
 'echo_out':       dict(X=16,swap=1,hofs=2,echo=True,supported=True),
}
MAXSHARE=float(os.environ.get('TECH_MAXSHARE',0.4));ECHO_MAX=int(os.environ.get('ECHO_MAX',2));LOOP_MAX=int(os.environ.get('LOOP_MAX',3))
def allowed(seq,name,n_total,loops=0,will_loop=False):
  if len(seq)>=2 and seq[-1]==seq[-2]==name:return False
  if seq.count(name)+1>max(1,int(MAXSHARE*n_total)):return False
  if name=='echo_out':
    if seq.count('echo_out')>=ECHO_MAX:return False
    if any(s=='echo_out' for s in seq[-3:]):return False
  if will_loop and loops>=LOOP_MAX:return False
  return True
def pick(scores,n_total,supported_only=True):
  """scores: list (one per blend) of {technique: cost}; greedy lowest-cost choice under the diversity rule"""
  seq=[]
  for sc in scores:
    opts=sorted((c,t) for t,c in sc.items() if t in MENU and (MENU[t]['supported'] or not supported_only))
    ch=next((t for c,t in opts if allowed(seq,t,n_total)),opts[0][1] if opts else 'long_blend');seq.append(ch)
  return seq
