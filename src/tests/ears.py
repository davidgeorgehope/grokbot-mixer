"""'Ears' checks (the listener 2026-10-28, after Bad To Me -> Blame You 34:05 rated 1/5: 'the melodies clash and the beats clash').
Per beat / per bar, decks rendered alone, over the whole blend (never averaged away):
  dissonance(beat): pitch-class clash between the two decks' chroma (semitone/tritone/whole-tone weighted), 0..1
  beat_off(bar):    how much better deck B's 16-step kick+snare pattern lines up with deck A when shifted by a beat or
                    half-bar than at zero shift (>0 = the backbeats are on different beats: 'beats clash')."""
import numpy as np,librosa
from scipy.signal import butter,sosfiltfilt
SR=44100;BAR=4*60/174;BEAT=BAR/4;S16=BAR/16
HP=butter(4,[150,4000],'band',fs=SR,output='sos');LP=butter(4,120,'low',fs=SR,output='sos')
DW=np.zeros(12);DW[[1,11]]=1.0;DW[6]=0.5;DW[[2,10]]=0.25
def _mono(y):return y.mean(1) if y.ndim>1 else y
def chroma_beats(y):
  c=librosa.feature.chroma_stft(y=librosa.resample(sosfiltfilt(HP,_mono(y)),orig_sr=SR,target_sr=22050),sr=22050,hop_length=512,norm=None)
  fr=22050/512;nb=int(len(y)/SR/BEAT);return np.array([c[:,int(k*BEAT*fr):max(int(k*BEAT*fr)+1,int((k+1)*BEAT*fr))].mean(1) for k in range(nb)])
def dissonance(ca,cb):
  a=np.maximum(ca-np.median(ca),0)**2;b=np.maximum(cb-np.median(cb),0)**2  # keep each deck's dominant notes only
  a=a/(a.sum()+1e-9);b=b/(b.sum()+1e-9);return float(sum(a[i]*b[j]*DW[(i-j)%12] for i in range(12) for j in range(12)))
def pattern(y):
  """per bar: 16-step onset pattern (kick lowband + snare midband), z-scored"""
  out=[]
  for f,band in ((LP,'k'),(HP,'s')):
    o=librosa.onset.onset_strength(y=librosa.resample(sosfiltfilt(f,_mono(y)),orig_sr=SR,target_sr=22050),sr=22050,hop_length=64);out.append(o)
  fr=22050/64;nb=int(len(y)/SR/BAR);P=[]
  for b in range(nb):
    v=[]
    for o in out:
      st=[o[int((b*BAR+k*S16)*fr):int((b*BAR+(k+1)*S16)*fr)+1].max() for k in range(16)];st=np.array(st);v.append((st-st.mean())/(st.std()+1e-9))
    P.append(np.concatenate(v))
  return np.array(P)
def beat_off(pa,pb):
  def c(sh):return float(np.mean(pa*np.concatenate([np.roll(pb[:16],sh),np.roll(pb[16:],sh)])))
  return max(c(4),c(-4),c(8))-c(0)
