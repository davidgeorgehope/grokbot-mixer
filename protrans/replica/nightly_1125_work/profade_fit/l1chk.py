import json, os, sys, numpy as np
SRC2='/workspace/mixes/src2_pin_n1121'; os.environ['PROTRANS_SRC2']=SRC2
sys.path.insert(0, SRC2); sys.path.insert(0,'/workspace/mixes/protrans'); os.chdir(SRC2)
import blend_diag as BD
from engine import BS
for p in sys.argv[1:]:
    M=json.load(open(p)); t=M['trans'][0]
    s0,A,B=BD.crop_decks(M,0); n=int(round(len(A)/BS))
    s,e=max(0,int(float(t['start_bar'])-s0)),min(n,int(float(t['end_bar'])-s0))
    loA,loB=BD.band_bar_db(A,n,BS,'low',120),BD.band_bar_db(B,n,BS,'low',120); sumlo=BD.band_bar_db(A+B,n,BS,'low',120)
    ex=sumlo[s:e]-np.maximum(loA[s:e],loB[s:e]); l1=float(ex.max())
    refA=float(np.median(loA[:max(1,s)])) if s>=2 else float(np.percentile(loA,80)); refB=float(np.median(loB[e:])) if n-e>=2 else float(np.percentile(loB,80))
    aud=sumlo[s:e]>=max(refA,refB)-12.0; l1a=float(ex[aud].max()) if aud.any() else 0.0
    print(os.path.basename(p), json.dumps(dict(l1=round(l1,2), l1_fail=l1>3.0, l1a=round(l1a,2), l1a_fail=l1a>3.0, argmax_bar=int(s0+s+int(ex.argmax())), loA=round(float(loA[s+int(ex.argmax())]),1), loB=round(float(loB[s+int(ex.argmax())]),1), refA=round(refA,1), refB=round(refB,1))))
