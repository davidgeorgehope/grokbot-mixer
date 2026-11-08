"""Small-source regression coverage for processing also measured by live QA."""
import copy
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

def test_echo_appends_filtered_decaying_tail_without_changing_dry(synthetic_meta):
    import engine as E
    deck=copy.deepcopy(synthetic_meta['decks'][0]);deck['full_map']=deck['full_map'][:4]
    deck['end_bar']=4;deck['auto']={}
    dry=E.render_deck(deck)
    deck['echo_out']=dict(bars=1,tail_bars=4,lo=400,hi=4000,
                          delay_beats=1,wet_db=-12,fb=.25)
    wet=E.render_deck(deck)
    assert np.array_equal(wet[:len(dry)],dry)
    tail=wet[len(dry):]
    assert len(tail)==round(4*E.BS) and np.max(np.abs(tail))>1e-6
    quarter=round(E.BS/4)
    db=lambda y:10*np.log10(np.mean(y*y)+1e-15)
    assert db(tail[-quarter:])<db(tail[:quarter])-40
    low=sosfiltfilt(butter(4,150,'low',fs=E.SR,output='sos'),tail,axis=0)
    assert db(low)<db(tail)-24

def test_low_lane_removes_bass_but_preserves_melody(synthetic_meta):
    import engine as E
    deck=copy.deepcopy(synthetic_meta['decks'][0]);deck['full_map']=deck['full_map'][:4]
    deck['auto']={};dry=E.render_deck(deck)
    deck['auto']={'low':[[0,0],[4,0]]};cut=E.render_deck(deck)
    # Avoid filter-edge transients when comparing steady-state bands.
    low=butter(4,100,'low',fs=E.SR,output='sos')
    high=butter(4,300,'high',fs=E.SR,output='sos')
    rms=lambda y:np.sqrt(np.mean(y[E.SR:-E.SR]**2))
    assert rms(sosfiltfilt(low,cut,axis=0))<rms(sosfiltfilt(low,dry,axis=0))*.15
    assert rms(sosfiltfilt(high,cut,axis=0))>rms(sosfiltfilt(high,dry,axis=0))*.8

def test_bass_gap_detects_holes_not_source_breakdowns(synthetic_meta,audio_workspace):
    import engine as E, bassgap as G
    M=synthetic_meta;M['trans'][0].update(start_bar=4,end_bar=20)
    y,sr=sf.read(audio_workspace/'st/fixture_out.wav',always_2d=True)
    master=audio_workspace/'master.flac';sf.write(master,y,sr)
    assert not G.check(M,str(master),src_db=lambda *args:False)
    y[round(8*E.BS):round(10*E.BS)]=0;sf.write(master,y,sr)
    bad=G.check(M,str(master),src_db=lambda *args:False)
    assert any(i==0 and s==8 and length==2 for i,s,length in bad),bad
    assert not G.check(M,str(master),src_db=lambda *args:True)

def test_all_release_entrypoints_keep_acceptance_gates():
    root=Path(__file__).resolve().parents[2]
    callers=[root/'src/render_and_test.sh', *root.glob('src2/autoloop*.py'),
             *root.glob('mix05v2/run_v*.sh')]
    for path in callers:
        for line in path.read_text().splitlines():
            if 'python3 -m pytest' in line:
                assert '../src/tests ../src/build_qa' in line,path
    planner=(root/'src2/plan_search.py').read_text()
    assert 'import test_release_mix02_traits as T2,test_release_mix as TM' in planner
    assert 'test_release_structure_tail as TS,test_release_variety as TV' in planner
