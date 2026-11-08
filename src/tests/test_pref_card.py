"""preference model (advisory) + per-stem blend card plumbing"""
import os,sys,json,glob,importlib
import numpy as np,pytest
S2=os.path.join(os.path.dirname(__file__),'..','..','src2');sys.path.insert(0,os.path.abspath(S2))
R=os.path.abspath(os.path.join(S2,'..'))

def _bl():
    cwd=os.getcwd();os.chdir(S2)
    try:return importlib.import_module('blend_loop')
    finally:os.chdir(cwd)

def C(cost,mp3):return dict(cost=cost,mp3=mp3,passes=True)

def test_tiebreak_off_by_default():
    bl=_bl();P=[C(1.0,'a'),C(1.001,'b')]
    assert bl.pref_tiebreak(P,w=0,scorer=lambda m:{'a':-9,'b':9})==P

def test_tiebreak_reorders_only_near_ties():
    bl=_bl();P=[C(1.0,'a'),C(1.01,'b'),C(1.5,'c')]
    out=bl.pref_tiebreak(P,w=1,eps=0.02,scorer=lambda m:{'a':-1,'b':1,'c':99})
    assert [c['mp3'] for c in out]==['b','a','c']  # c is far costlier: never promoted
    out=bl.pref_tiebreak(P,w=1,eps=0.001,scorer=lambda m:{'a':-1,'b':1})
    assert [c['mp3'] for c in out]==['a','b','c']

def test_tiebreak_never_sees_strict_failures():
    # it is applied to P (strict passers) only; a failed candidate can't enter
    src=open(os.path.join(S2,'blend_loop.py')).read()
    assert "P=[c for c in ok if c['passes']]\n    P=pref_tiebreak(P)" in src

def test_scorer_failure_is_neutral():
    bl=_bl();P=[C(1.0,'a'),C(1.0,'b')]
    out=bl.pref_tiebreak(P,w=1,scorer=lambda m:{})
    assert [c['mp3'] for c in out]==['a','b']

def test_david_pairs_resolve():
    pm=pytest.importorskip('pref_model')
    D=pm.david_pairs();assert len(D)>=5
    for g,a,b,w in D:assert os.path.exists(a) and os.path.exists(b) and w>0 and a!=b

def test_score_without_model_is_zero(tmp_path,monkeypatch):
    pm=pytest.importorskip('pref_model');monkeypatch.setattr(pm,'MODEL',str(tmp_path/'none.npz'))
    assert pm.score(['x.mp3'])=={'x.mp3':0.0}

def test_publish_writes_sidecars(audio_workspace, synthetic_meta, tmp_path):
    import subprocess
    BC=importlib.import_module('blend_card')
    import engine as E
    source=tmp_path/'clip.mp3'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(audio_workspace/'st/fixture_out.wav'),
                    '-t','5','-c:a','libmp3lame',str(source)],check=True)
    decks=synthetic_meta['decks']
    for d in decks:d['full_map']=d['full_map'][:4];d['end_bar']=4
    tim=dict(source_dir=str(audio_workspace),sr=E.SR,bs=E.BS,bar_sec=E.BAR,
             clip_start_bar=0,clip_end_bar=3,trans=synthetic_meta['trans'][0],decks=decks)
    dst=str(tmp_path/'x.mp3')
    card=BC.publish(str(source),dst,tim)
    assert card is not None, 'real card rendering failed (publish intentionally catches errors)'
    assert os.path.getsize(dst)>0 and json.load(open(dst.replace('.mp3','.timing.json')))['clip_start_bar']==0
    assert os.path.getsize(dst.replace('.mp3','.card.png'))>10000

def test_publish_never_raises(tmp_path):
    BC=importlib.import_module('blend_card')
    src=tmp_path/'a.mp3';src.write_bytes(b'not audio');dst=str(tmp_path/'b.mp3')
    BC.publish(str(src),dst,{'bogus':1});BC.publish(str(src),str(tmp_path/'c.mp3'),None)
    assert os.path.exists(dst)
