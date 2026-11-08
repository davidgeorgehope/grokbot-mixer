"""Event controls must survive mastering level and a clean gain-curve render."""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import score


def frames(bars):
    t = np.arange(int(len(bars)*score.BAR_SEC*score.SR/score.HOP))
    return np.asarray(bars)[np.minimum((t*score.HOP/score.SR/score.BAR_SEC).astype(int),len(bars)-1)]


def test_events_relative_level_and_no_bar_zero_swap():
    out = frames([0]*12 + [-80]*12)
    inc = frames([-80]*4 + [-8]*4 + [0]*16)
    ref = score.events_from_pair(out, inc)
    assert ref['bass_swap'] in (8,9), ref
    assert ref['outgoing_cut'] in (12,13), ref
    assert 8 <= ref['blend_length'] <= 9, ref
    assert score.events_from_pair(out-35, inc-35) == ref
    assert score.events_from_pair([],[])['blend_length'] == 0
    silent=frames([-120]*24)
    assert score.events_from_pair(silent,silent) == dict(bass_swap=None,outgoing_cut=None,blend_length=0)


def test_clean_oracle_gain_render(tmp_path, monkeypatch):
    import soundfile as sf
    import diagnose_gap as D
    sr = score.SR
    n = int(24*score.BAR_SEC*sr)
    t = np.arange(n)/sr
    # Separate frequency fingerprints make the two-deck gain fit identifiable.
    a = (.2*np.sin(2*np.pi*70*t)+.1*np.sin(2*np.pi*800*t)).astype('float32')
    b = (.2*np.sin(2*np.pi*110*t)+.1*np.sin(2*np.pi*1600*t)).astype('float32')
    bars = t/score.BAR_SEC
    ga = (bars < 16).astype(float)
    gb = np.where(bars < 4, 0, np.where(bars < 12,.4,1))
    pro = (ga*a+gb*b).astype('float32')
    paths=[]
    for name,y in [('a',a),('b',b)]:
        p=tmp_path/(name+'.wav');sf.write(p,y,sr,subtype='FLOAT');paths.append(str(p))
    # Known alignment isolates event calibration from the separate locator.
    monkeypatch.setattr(D.version_match,'locate_in',lambda *a,**k:dict(track_t=0,mix_t=0))
    monkeypatch.setattr(D,'refine_lag',lambda p,s,**k:(s,0))
    gains,oracle,_,_=D.band_gains(pro,a,b)
    p = score.source_gain_events(pro,*paths)
    o = score.source_gain_events(oracle,*paths)
    assert p == o, (p,o)
    assert 12 <= p['bass_swap'] <= 13,p
    assert 16 <= p['outgoing_cut'] <= 17,p
    assert 12 <= p['blend_length'] <= 13,p


def test_real_clean_pro_oracle_events():
    import json
    import pytest
    import diagnose_gap as D
    if not os.path.isfile(D.ADMITTED):
        pytest.skip('optional local pro corpus absent')
    row=next(r for r in json.load(open(D.ADMITTED)) if r['id']=='joe_syntax_hospital__18')
    paths=[D._src_path(row[k]['yt']) for k in ('a','b')]
    if not all(os.path.isfile(p) for p in paths+[row['pro_clip']]):
        pytest.skip('optional studio/pro audio absent')
    pro=D._load(row['pro_clip']);aligned=[]
    for side,path in zip(('a','b'),paths):
        loc=row['gate'][side]['locate']
        a=D.place_source(path,loc['track_t'],loc['mix_t'],len(pro))
        a,_=D.refine_lag(pro,a);aligned.append(a)
    _,oracle,_,_=D.band_gains(pro,*aligned)
    p=score.source_gain_events(pro,*paths)
    o=score.source_gain_events(oracle,*paths)
    # Quantisation is one bar; a real gain-fit render must not invent a new event.
    for key in ('bass_swap','outgoing_cut','blend_length'):
        assert p[key] is not None and o[key] is not None,(p,o)
        assert abs(p[key]-o[key]) <= 1,(p,o)


def test_long_fade_is_not_collapsed_to_one_bar():
    n=int(48*score.BAR_SEC*score.SR/score.HOP)
    bars=np.arange(n)*score.HOP/score.SR/score.BAR_SEC
    gain=np.clip((bars-8)/32,0,1)
    events=score.events_from_pair(score._db(1-gain)-40,score._db(gain)-40)
    # Both lanes above quarter-level span the central 16 bars of a 32-bar fade.
    assert 16 <= events['blend_length'] <= 17,events
    assert 23 <= events['bass_swap'] <= 24,events
    assert 32 <= events['outgoing_cut'] <= 33,events
