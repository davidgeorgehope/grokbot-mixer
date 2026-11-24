"""gain_step (RCA 2026-11-24 fix 2): steps the master gain down until the worst excerpt true peak is <= -1.0 dBTP (threshold unchanged)."""
import pathlib,sys,numpy as np,soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'src2'))
import gain_step as GS

def test_threshold_is_the_release_one():
  import checks;assert GS.TP_MAX==checks.TP_MAX==-1.0

def test_steps_down_until_under_the_ceiling(monkeypatch,tmp_path):
  w=tmp_path/'r.wav';sf.write(w,np.zeros((44100*60,2),np.float32),44100)
  monkeypatch.setattr(GS,'excerpt_tp',lambda raw,g,wins,sr,tmp:-1.0+0.4*(g-8.0))   # 9.0 -> -0.6, 8.5 -> -0.8, 8.0 -> -1.0
  R=GS.choose_gain(str(w),9.0,7.0,0.5,log=lambda *a,**k:None);assert R['gain']==8.0 and [g for g,_ in R['tried']]==[9.0,8.5,8.0]

def test_gives_up_at_the_floor(monkeypatch,tmp_path):
  w=tmp_path/'r.wav';sf.write(w,np.zeros((44100*30,2),np.float32),44100)
  monkeypatch.setattr(GS,'excerpt_tp',lambda *a:0.0)
  assert GS.choose_gain(str(w),8.0,7.0,0.5,log=lambda *a,**k:None)['gain'] is None

def test_windows_pick_loudest_and_peakiest(tmp_path):
  y=np.full((44100*200,2),0.01,np.float32);y[44100*45:44100*55]=0.5;y[44100*130]=0.99
  w=tmp_path/'r.wav';sf.write(w,y,44100);W,sr=GS.windows(str(w),k=1,sec=20.0)
  assert sr==44100 and (40.0,20.0) in W and (120.0,20.0) in W

def test_full_master_stepper_uses_the_whole_mix(monkeypatch,tmp_path):
  calls=[]
  def fake(raw,g,mp3,master):calls.append(g);return {9.0:-0.8,8.5:-0.95,8.0:-1.1}[g]
  monkeypatch.setattr(GS,'full_master',fake)
  R=GS.choose_gain_full('x.wav',9.0,7.0,0.5,log=lambda *a,**k:None)
  assert R['gain']==8.0 and calls==[9.0,8.5,8.0] and R['method']=='full'
