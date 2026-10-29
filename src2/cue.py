"""Pro cue-point model (Raveform, Kim et al. TISMIR 2026, CC-BY-4.0): logistic score for where pros end a track
(the mix-out point; the mix-in model lost to a plain position rule and is not shipped), from per-bar dB features (all, low <150 Hz, hat 6+ kHz). Trained by /workspace/raveform/cue/train.py;
weights in cue_model.json. Used by mix_simple (CUEW>0, default off) and by the pro-likeness report (cue_report.py)."""
import json,os,numpy as np
STEP=4  # candidate grid (bars)
NAMES=['pos','bars_from_start','bars_to_end','e_next','e_prev','e_delta','low_next','hat_next','hat_prev','to_drop','from_last_loud','phrase']
def track_feats(al,lo,hat):
  """per-bar feature matrix (nb x len(NAMES)); levels relative to the record's body (75th pct)."""
  al,lo,hat=(np.asarray(x,float) for x in (al,lo,hat));nb=len(al)
  r=lambda x:x-np.percentile(x,75)
  A,L,H=r(al),r(lo),r(hat)
  def win(x,k,n):s=x[max(0,k):max(0,min(nb,k+n))];return float(s.mean()) if len(s) else -30.0
  sm=np.array([win(A,k,16) for k in range(nb)]);loud=np.where(sm>-2)[0]
  fd=int(loud[0]) if len(loud) else nb//3;ll=int(loud[-1]+16) if len(loud) else 2*nb//3
  X=[]
  for k in range(nb):
    X.append([k/nb,min(k,128)/128,min(nb-k,128)/128,win(A,k,16),win(A,k-16,16),win(A,k,16)-win(A,k-16,16),win(L,k,16),win(H,k,16),win(H,k-16,16),
              np.clip((fd-k)/64,-2,2),np.clip((k-ll)/64,-2,2),float(k%16==0)])
  return np.maximum(np.array(X),-30)
def load(path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'cue_model.json')):return json.load(open(path))
def logits(M,kind,X):
  m=M[kind];Z=(X-np.array(m['mu']))/np.array(m['sd']);return Z@np.array(m['w'])+m['b']
def pctl(M,kind,X,k):
  """0-1: share of this record's candidate bars (STEP grid) that the model scores below bar k (1 = most pro-like spot)."""
  s=logits(M,kind,X);c=s[::STEP];return float((c<s[min(k,len(s)-1)]).mean())
