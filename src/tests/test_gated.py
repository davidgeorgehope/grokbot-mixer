"""gated.py (BLEND_AUDIO_GATE wiring): a dry-OK plan still fails when a blend fails on its own audio or leaves a deep breakdown solo;
failing windows are banned for plan_search (SEESAW_BANFILE channel) and repair (ctx.badwin). Synthetic, no audio."""
import pathlib,sys,json,os
SRC2=pathlib.Path(__file__).resolve().parents[2]/'src2';sys.path.insert(0,str(SRC2))
cwd=os.getcwd()
import gated as G
os.chdir(cwd)

def test_dry_ok_plan_fails_on_blend_audio(monkeypatch):
  M=dict(plan=[{'id':'a','out_win':['n',200,None,16,32]},{'id':'b'}])
  monkeypatch.setattr(G,'dry_predict',lambda P,tag:(dict(all_ok=True,tests=dict(vocal=True)),M))
  monkeypatch.setattr(G,'gate_meta',lambda M,g,n,j:({0:dict(ok=False,secs=dict(total=40),cached=False)},[('a','b','bassgap',['n',200,None,16,32],'test_no_bass_gap_in_overlaps','4:46')],[]))
  p=G.gated_dry(M['plan'],'t',9.0,'n.json',log=lambda *a,**k:None)
  assert p['all_ok'] is False and p['tests']['blend_audio'] is False and p['tests']['solo_hole'] is True
  assert p['gate_fails'][0]['code']=='bassgap' and p['gate_fails'][0]['window']==['n',200,None,16,32]

def test_dry_failure_skips_the_gate(monkeypatch):
  monkeypatch.setattr(G,'dry_predict',lambda P,tag:(dict(all_ok=False,tests=dict(vocal=False)),{}))
  monkeypatch.setattr(G,'gate_meta',lambda *a:(_ for _ in ()).throw(AssertionError('gate must not run')))
  assert G.gated_dry([],'t',9.0,'n',log=lambda *a,**k:None)['all_ok'] is False

def test_bans_merge_with_the_mix_seesaw_bans(tmp_path,monkeypatch):
  monkeypatch.setattr(G,'BANFILE',str(tmp_path/'bans.json'));monkeypatch.setattr(G.BG,'proven_bad_windows',lambda:{('x','y',('n',1,None,1,16))})
  ss=tmp_path/'seesaw.json';json.dump({'p>q':[['n',9,None,9,32]]},open(ss,'w'));monkeypatch.setenv('SEESAW_BANFILE_BASE',str(ss))
  B=G.load_bans();assert B=={'x>y':[['n',1,None,1,16]]}
  assert G.add_bans(B,[('a','b',['n',200,None,16,32]),('a','b',['n',200,None,16,32])])==1
  m=json.load(open(G.merged_banfile(B)));assert m['p>q']==[['n',9,None,9,32]] and m['a>b']==[['n',200,None,16,32]] and 'x>y' in m

def test_solo_hole_bans_both_windows_around_the_track():
  P=[{'id':'a','out_win':['n',1,None,1,16]},{'id':'h','out_win':['n',2,None,2,16]},{'id':'c'}]
  assert G._hole_windows(P,[dict(track='h')])==[('a','h',['n',1,None,1,16]),('h','c',['n',2,None,2,16])]

def test_codes_match_repair_render_culprits():
  assert G.CODEMAP['test_no_bass_gap_in_overlaps']=='bassgap' and G.CODEMAP['N1']=='N1' and G.CODEMAP['test_no_level_dip_at_swap']=='swapdip'


def test_pool_skips_bans_the_window_not_the_pair():
  """a ban on one window of a pair skips only plans that use THAT window; another window of the same pair is still tried"""
  B={'a>b':[['n',176,None,48,16]]}
  pool=[dict(seq=['a','b'],bl=[dict(a='a',b='b',w=['n',176,None,48,16])]),
        dict(seq=['a','b'],bl=[dict(a='a',b='b',w=['n',160,None,48,16])]),
        dict(seq=['x','b'],bl=[dict(a='x',b='b',w=['n',176,None,48,16])])]
  s=G.pool_skips(pool,B,set())
  assert s['why']==['banned',None,None] and s['n_banned']==1


def test_pool_skips_reports_what_blocks_a_fully_banned_pool():
  """when every plan is skipped the report names the blocking windows and the exclusion count"""
  B={'a>b':[['n',1,None,16,16]]}
  pool=[dict(seq=['a','b','m'],bl=[dict(a='a',b='b',w=['n',1,None,16,16])]),dict(seq=['a','b'],bl=[dict(a='a',b='b',w=['n',1,None,16,16])])]
  s=G.pool_skips(pool,B,{'m'})
  assert s['why']==['excluded','banned'] and s['n_excluded']==1 and s['n_banned']==2 and s['top'][0]==("a>b ['n', 1, None, 16, 16]",2)
