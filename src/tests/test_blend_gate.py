"""blend_gate (BLEND_AUDIO_GATE, RCA 2026-11-24 fix 1): clip crop/shift is exact and the cache key changes with code, features and window.
Pure: synthetic meta, no audio, no render."""
import pathlib,sys,copy
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'src2'))
import blend_gate as BG

def deck(i,s,n,src0=0):
  return dict(id=i,start_bar=s,end_bar=s+n,full_map=[[src0+k,'mix'] for k in range(n)],auto={'gain':[[s,0.0],[s+32,1.0]],'low':[[s+8,0.0],[s+12,1.0]]},
    echo=False,label='',map=[],acap=False,drop_bar=None)
def meta():
  A=deck('a',0,200);B=deck('b',168,200,16);C=deck('c',336,100)
  t0=dict(a='a',b='b',start_bar=168,end_bar=200,swap_bar=176,high_bar=184,xfader=[[168,0.0],[200,1.0]],bass_swap=[175,179],tech='x',notes=[])
  t1=dict(a='b',b='c',start_bar=336,end_bar=368,swap_bar=344,high_bar=None,xfader=[[336,0.0],[368,1.0]],bass_swap=None,tech='x',notes=[])
  return dict(engine='simple_crossfader',decks=[A,B,C],trans=[t0,t1],plan=[{'id':'a','out_win':['n',200,None,16,32]},{'id':'b'},{'id':'c'}],bar_sec=1.379)

def test_clip_spans_16_before_to_8_after():
  assert BG.clip_bounds(meta(),0)==(152,208)

def test_clip_never_holds_a_third_deck():
  M=meta();M['trans'][1]['start_bar']=204;assert BG.clip_bounds(M,0)==(152,204)   # next blend starts 4 bars after: stop there
  M=meta();assert BG.clip_bounds(M,1)==(320,376)
  M['trans'][0]['end_bar']=330;assert BG.clip_bounds(M,1)[0]==330                  # previous blend still running at start-16
  M['trans'][0]['echo_out']=True;assert BG.clip_bounds(M,1)[0]==334
  dk=BG.crop_decks(M,*BG.clip_bounds(M,1));assert [d['id'] for d,_ in dk]==['b','c']

def test_crop_keeps_absolute_bars_and_source_map():
  M=meta();dk=BG.crop_decks(M,152,208)
  assert [d['id'] for d,_ in dk]==['a','b']  # c starts at 336: not in the clip
  a,j0=dk[0];assert j0==152 and a['start_bar']==152 and a['full_map'][0]==[152,'mix'] and len(a['full_map'])==48
  b,j0=dk[1];assert j0==0 and b['start_bar']==168 and b['full_map'][0]==[16,'mix'] and b['end_bar']==208

def test_crop_drops_echo_of_a_later_exit():
  M=meta();M['decks'][1]['echo_out']=dict(bars=1);dk=BG.crop_decks(M,152,208)
  assert 'echo_out' not in dk[1][0]

def test_shift_moves_every_bar_field_to_clip_time():
  M=meta();dk=BG.crop_decks(M,152,208);cm=BG.shift_meta(M,0,dk,152,208);t=cm['trans'][0]
  assert (t['start_bar'],t['end_bar'],t['swap_bar'],t['high_bar'])==(16,48,24,32)
  assert t['xfader'][0][0]==16 and t['bass_swap']==[23,27]
  assert cm['decks'][0]['start_bar']==0 and cm['decks'][1]['start_bar']==16
  assert cm['decks'][1]['auto']['gain'][0]==[16,0.0] and cm['decks'][1]['auto']['low'][0]==[24,0.0]
  assert len(cm['trans'])==1 and cm['clip']['a']=='a' and cm['len_sec']==56*1.379
  assert M['trans'][0]['start_bar']==168  # source meta untouched

def test_key_changes_with_window_gain_code_and_features(monkeypatch):
  monkeypatch.setattr(BG,'feat_hash',lambda t:'f0');monkeypatch.setattr(BG,'_nudge_for',lambda ids,n:{})
  BG.code_hash.cache_clear() if hasattr(BG.code_hash,'cache_clear') else None
  M=meta();dk=BG.crop_decks(M,152,208);cm=BG.shift_meta(M,0,dk,152,208);k=BG.clip_key(cm,9.0,'n.json')
  assert k==BG.clip_key(copy.deepcopy(cm),9.0,'n.json')
  assert k!=BG.clip_key(cm,8.0,'n.json')
  cm2=copy.deepcopy(cm);cm2['decks'][1]['full_map'][0]=[17,'mix'];assert k!=BG.clip_key(cm2,9.0,'n.json')
  monkeypatch.setattr(BG,'feat_hash',lambda t:'f1');assert k!=BG.clip_key(cm,9.0,'n.json')
  monkeypatch.setattr(BG,'feat_hash',lambda t:'f0');monkeypatch.setattr(BG,'code_hash',lambda:'other');assert k!=BG.clip_key(cm,9.0,'n.json')

def test_verdict_routes_mix_level_checks():
  G=dict(failures=[dict(check='P1',t='0:00',msg='tp'),dict(check='N1',t='0:20',msg='grid')],warnings=[dict(check='F1')])
  P=[dict(test='test_true_peak',status='fail',msg='tp'),dict(test='test_no_bass_gap_in_overlaps',status='pass')]
  v=BG.verdict(G,P);assert not v['ok'] and [f['check'] for f in v['blend_fails']]==['N1'] and {f['check'] for f in v['mix_level']}=={'P1','test_true_peak'}
  v=BG.verdict(dict(failures=[dict(check='P1',msg='')],warnings=[]),[]);assert v['ok']

def test_gate_is_off_by_default(monkeypatch):
  monkeypatch.delenv('BLEND_AUDIO_GATE',raising=False);assert not BG.enabled()
  monkeypatch.setenv('BLEND_AUDIO_GATE','1');assert BG.enabled()

def test_shares_release_tests_instead_of_copying():
  import importlib;sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'build_qa'))
  for mod,fn in BG.TESTS:
    assert callable(getattr(importlib.import_module(mod),fn)),(mod,fn)

def test_proven_bad_windows_reads_only_current_code_blend_fails(tmp_path,monkeypatch):
  import json as J
  monkeypatch.setattr(BG,'CACHE',str(tmp_path))
  J.dump(dict(code='c1',ok=False,a='a',b='b',window=['n',200,None,16,32]),open(tmp_path/'1.json','w'))
  J.dump(dict(code='c1',ok=True,a='a',b='c',window=['n',190,None,16,32]),open(tmp_path/'2.json','w'))
  J.dump(dict(code='old',ok=False,a='x',b='y',window=['n',1,None,1,16]),open(tmp_path/'3.json','w'))
  assert BG.proven_bad_windows('c1')=={('a','b',('n',200,None,16,32))}
