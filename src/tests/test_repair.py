"""repair.py (DJustify-style): a failing blend gets its incoming track swapped for another crate track, windows re-picked,
and the loop stops at the first candidate the dry check passes. Synthetic table + dry; no audio, no crate files."""
import pathlib,sys,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'src2'))
import repair as R

def W(kind='n',e=128,p=None,ib=32,X=32,voc=0):return dict(w=[kind,e,p,ib,X],voc=voc,pen=0)
def table(pairs):
  ids={x for k in pairs for x in k.split('>')}
  return dict(tracks={i:{} for i in ids},pairs={k:dict(key_ok=True,wins=v) for k,v in pairs.items()})
def step(i,w=None):
  d={'id':i,'kw':{'pre':16,'build':True},'anchor':False,'tech':'blend'}
  if w:d['out_win']=w
  return d
ok=lambda T,a,b,w,ia:not w['voc'] and w['w'][3]<=80
cost=lambda T,a,b,w:w['pen']

def fake_dry(bad,length_per_track=3.0):
  """all_ok unless a bad pair is still adjacent; length = tracks x length_per_track minutes"""
  calls=[]
  def dry(P,tag):
    ids=[p['id'] for p in P];calls.append(ids)
    hit=[(a,b) for a,b in zip(ids,ids[1:]) if (a,b) in bad]
    return dict(all_ok=not hit,len_min=len(P)*length_per_track,tests=dict(vocal=not hit),
      vocal_clash=[dict(a=a,b=b) for a,b in hit])
  return dry,calls

def test_failing_pair_gets_incoming_swapped():
  T=table({'A>B':[W()],'B>D':[W()],'A>X':[W(),W(ib=96)],'X>D':[W(voc=3),W(ib=16)],'A>Y':[W()]})  # Y cannot reach D
  plan=[step('A',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('D')]
  dry,calls=fake_dry({('A','B')},length_per_track=21)
  ctx=R.Ctx(T,['A','B','D','X','Y'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','L1')],ctx,log=lambda *_:None)
  assert [p['id'] for p in P]==['A','X','D']
  assert hist[0]['action']=='replace_in' and hist[0]['track']=='X'
  assert P[0]['out_win'][3]<=80 and P[1]['out_win']==['n',128,None,16,32]   # vocal window and ib>80 skipped
  assert R.passes(res)

def test_insert_when_no_replacement_and_length_rule_holds():
  T=table({'A>B':[W()],'A>X':[W()],'X>B':[W()]})
  plan=[step('A',['n',128,None,32,32]),step('B')]
  dry,_=fake_dry({('A','B')},length_per_track=21)   # 2 tracks = 42 min, 3 = 63
  ctx=R.Ctx(T,['A','B','X'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','G1')],ctx,log=lambda *_:None)
  assert [p['id'] for p in P]==['A','X','B'] and hist[0]['action']=='insert' and res['len_min']>=60

def test_phase_failure_on_loop_avoids_loop_windows():
  T=table({'A>B':[W()],'A>X':[W(kind='lx',p=112,X=16),W(kind='n')],'X>B':[W()]})
  plan=[step('A',['lx',144,128,0,16]),step('B')]
  dry,_=fake_dry({('A','B')},length_per_track=21)
  ctx=R.Ctx(T,['A','B','X'],ok=ok,cost=cost,dry=dry)
  P,_,_=R.repair(plan,[('A','B','G1')],ctx,log=lambda *_:None)
  assert P[0]['out_win'][0]=='n'

def test_budget_bounds_the_loop_and_reports_unresolved():
  T=table({'A>B':[W()],'A>X':[W()],'X>B':[W()]})
  plan=[step('A',['n',128,None,32,32]),step('B')]
  dry,calls=fake_dry({('A','B'),('A','X'),('X','B')},length_per_track=21)
  ctx=R.Ctx(T,['A','B','X'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','L1')],ctx,max_dry=2,log=lambda *_:None)
  assert len(calls)<=2 and [p['id'] for p in P]==['A','B'] and hist[0]['action'] in('budget','unresolved') and not R.passes(res)

def test_render_culprits_from_guardrails_and_pytest_log(tmp_path):
  M=dict(bar_sec=1.38,trans=[dict(a='AAAAAAAAAAA',b='BBBBBBBBBBB',start_bar=100,end_bar=116),dict(a='BBBBBBBBBBB',b='CCCCCCCCCCC',start_bar=300,end_bar=332)])
  (tmp_path/'m_meta.json').write_text(json.dumps(M));(tmp_path/'guard_m').mkdir()
  (tmp_path/'guard_m'/'guardrails.json').write_text(json.dumps(dict(failures=[dict(check='G1',sec=300*1.38-10)])))
  (tmp_path/'guard_m'/'pytest.log').write_text("E     AssertionError: [('AAAAAAAAAAA', 100, [-8.2])]\n../src/build_qa/test_release_structure_tail.py:78: AssertionError\n")
  c=R.render_culprits('m',src=str(tmp_path))
  assert ('BBBBBBBBBBB','CCCCCCCCCCC','G1') in c and ('AAAAAAAAAAA','BBBBBBBBBBB','tail') in c

def test_culprit_pair_never_recreated_and_unresolved_is_reported():
  T=table({'A>B':[W()],'A>X':[W()]})   # X has no way on to B, nothing else in the crate: no repair exists
  plan=[step('A',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('C')]
  T['pairs']['B>C']=dict(key_ok=True,wins=[W()])
  dry,calls=fake_dry(set(),length_per_track=21)   # dry passes everything: only the render knew A>B was bad
  ctx=R.Ctx(T,['A','B','C','X'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','L1')],ctx,log=lambda *_:None)
  assert not R.resolved(hist) and all(('A','B') not in list(zip(c,c[1:])) for c in calls[1:])

def test_render_failure_feeds_the_next_swap_round():
  T=table({'A>B':[W()],'B>D':[W()],'A>X':[W()],'X>D':[W()],'A>Y':[W()],'Y>D':[W()]})
  plan=[step('A',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('D')]
  dry,_=fake_dry(set(),length_per_track=21)
  ctx=R.Ctx(T,['A','B','D','X','Y'],ok=ok,cost=lambda T,a,b,w:0 if 'X' in(a,b) else 1,dry=dry)
  renders=[]
  def render(P,k):
    ids=[p['id'] for p in P];renders.append(ids)
    return ('X' not in ids),([('A','X','G1')] if 'X' in ids else [])   # the render finds A>X bad too
  P,rounds,passed=R.loop(plan,[('A','B','L1')],ctx,render,rounds=3,log=lambda *_:None)
  assert passed and renders==[['A','X','D'],['A','Y','D']] and len(rounds)==2

def test_soft_tier_used_only_when_strict_filter_leaves_nothing():
  T=table({'A>X':[W(voc=2,ib=16),W(voc=1,ib=48)],'A>Y':[W(),W(voc=1)]})
  strict=lambda T,a,b,w,ia:not w['voc']
  soft=lambda T,a,b,w,ia:10*w['voc']
  ctx=R.Ctx(T,['A','X','Y'],ok=strict,cost=cost,soft=soft,dry=None)
  assert [w for _,w in R.pick(ctx,'A','Y',0,k=5)]==[['n',128,None,32,32]]          # strict window exists: soft ones never offered
  assert [w[3] for _,w in R.pick(ctx,'A','X',0,k=5)]==[48,16]                        # none strict: cheapest soft first, dry decides

def test_earlier_miss_gets_second_pass_after_later_fix_adds_length():
  # A>B fails and its only repair is 0.5 min short; C>D's repair adds length, after which the A>B repair passes
  T=table({'A>X':[W()],'X>C':[W()],'C>Y':[W()],'Y>E':[W()],'A>B':[W()],'B>C':[W()],'C>D':[W()],'D>E':[W()]})
  plan=[step('A',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('C',['n',128,None,32,32]),step('D',['n',128,None,32,32]),step('E')]
  L={'A':12,'B':12,'C':12,'D':12,'E':12,'X':11.5,'Y':13}
  def dry(P,tag):
    ids=[p['id'] for p in P];return dict(all_ok=True,len_min=sum(L[i] for i in ids),tests={})
  ctx=R.Ctx(T,['A','B','C','D','E','X','Y'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','L1'),('C','D','L1')],ctx,log=lambda *_:None)
  assert [p['id'] for p in P]==['A','X','C','Y','E'] and R.resolved(hist) and R.passes(res)

def test_rewindow_fill_offers_soft_windows_after_the_only_strict_one():
  T=table({'A>B':[W(e=112),W(e=144,voc=1),W(kind='la',e=144,p=128,voc=1)]})
  ctx=R.Ctx(T,['A','B'],ok=lambda T,a,b,w,ia:not w['voc'],cost=cost,soft=lambda T,a,b,w,ia:w['voc'],dry=None)
  assert len(R.pick(ctx,'A','B',0,k=3))==1 and [w[1] for _,w in R.pick(ctx,'A','B',0,k=3,fill=True)]==[112,144,144]

def test_short_but_clean_repair_gets_a_length_pad_elsewhere():
  T=table({'A>X':[W()],'X>C':[W()],'C>D':[W(e=128),W(e=160)],'A>B':[W()]})
  plan=[step('A',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('C',['n',128,None,32,32]),step('D')]
  def dry(P,tag):
    ids=[p['id'] for p in P];extra=0.6 if P[2]['out_win'][1]==160 else 0
    return dict(all_ok=True,len_min=(59.7 if 'X' in ids else 61)+extra,tests={})
  ctx=R.Ctx(T,['A','B','C','D','X'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','L1')],ctx,log=lambda *_:None)
  assert [p['id'] for p in P]==['A','X','C','D'] and P[2]['out_win'][1]==160 and R.passes(res) and '+pad' in hist[0]['action']

def test_render_proved_bad_window_is_never_repicked():
  T=table({'A>B':[W(e=160),W(e=128)]})
  ctx=R.Ctx(T,['A','B'],ok=ok,cost=lambda T,a,b,w:0 if w['w'][1]==160 else 1,dry=None)
  assert R.pick(ctx,'A','B',0,k=1)[0][1][1]==160
  ctx.badwin={('A','B',('n',160,None,32,32))}
  assert [w[1] for _,w in R.pick(ctx,'A','B',0,k=5)]==[128]

def test_drop_outgoing_then_pad_insert_elsewhere():
  # A>S fails, nothing can follow or replace S: drop S (P>A... ) and win the length back with an unused track elsewhere
  T=table({'Q>A':[W()],'A>S':[W()],'S>B':[W()],'A>B':[W()],'B>C':[W()],'B>Z':[W()],'Z>C':[W()],'Q>S':[W()]})
  plan=[step('Q',['n',128,None,32,32]),step('A',['n',128,None,32,32]),step('S',['n',128,None,32,32]),step('B',['n',128,None,32,32]),step('C')]
  def dry(P,tag):
    ids=[p['id'] for p in P];return dict(all_ok=True,len_min=57+3.5*(len(ids)-4),tests={})   # 4 tracks 57 (short), 5 tracks 60.5
  ctx=R.Ctx(T,['Q','A','S','B','C','Z'],ok=ok,cost=cost,dry=dry)
  P,res,hist=R.repair(plan,[('S','B','G1')],ctx,log=lambda *_:None)
  ids=[p['id'] for p in P]
  assert 'S' not in ids and 'Z' in ids and R.passes(res) and hist[0]['action'].startswith('drop')

def test_render_culprits_parse_bassgap_trans_and_swap_pairs(tmp_path):
  M=dict(bar_sec=1.38,trans=[dict(a='AAAAAAAAAAA',b='BBBBBBBBBBB',start_bar=100,end_bar=116),dict(a='BBBBBBBBBBB',b='CCCCCCCCCCC',start_bar=300,end_bar=332)])
  (tmp_path/'m_meta.json').write_text(json.dumps(M));(tmp_path/'guard_m').mkdir()
  (tmp_path/'guard_m'/'pytest.log').write_text(
    "____ test_no_bass_gap_in_overlaps ____\nE     AssertionError: bass gaps (trans,mix bar,bars): [(1, 918, 2)]\n"
    "____ test_no_level_dip_at_swap ____\nE     AssertionError: [(23.54, 'AAAAAAAAAAA', 'BBBBBBBBBBB', 12, np.float32(-4.1))]\n")
  c=R.render_culprits('m',src=str(tmp_path))
  assert c==[('BBBBBBBBBBB','CCCCCCCCCCC','bassgap'),('AAAAAAAAAAA','BBBBBBBBBBB','swapdip')]

def test_energy_failure_can_rewindow_same_pair():
  # swapdip/bassgap/N1 may keep the pair if the window is clearly different (exit, ib, or length)
  T=table({'A>B':[W(e=128,ib=0),W(e=144,ib=16)]})
  plan=[step('A',['n',128,None,0,32]),step('B')]
  dry,_=fake_dry(set(),length_per_track=31)
  ctx=R.Ctx(T,['A','B'],ok=ok,cost=lambda T,a,b,w:0 if w['w'][3]==16 else 10,dry=dry)
  P,res,hist=R.repair(plan,[('A','B','swapdip')],ctx,log=lambda *_:None)
  assert hist[0]['action']=='rewindow' and P[0]['out_win'][3]==16 and R.passes(res)
