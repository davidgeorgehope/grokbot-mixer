import json, os, sys, numpy as np
SRC2='/workspace/mixes/src2_pin_n1121'; os.environ['PROTRANS_SRC2']=SRC2
sys.path.insert(0, SRC2); sys.path.insert(0,'/workspace/mixes/protrans'); sys.path.insert(0,'/workspace/mixes/protrans/replica'); os.chdir(SRC2)
import blend_diag as BD
from engine import BS
from pro_fade_fit import _eval_lane
for p in sys.argv[1:]:
    M=json.load(open(p)); t=M['trans'][0]
    s0,A,B=BD.crop_decks(M,0); n=int(round(len(A)/BS)); s,e=int(float(t['start_bar'])-s0),int(float(t['end_bar'])-s0)
    alA,alB=BD.band_bar_db(A,n,BS),BD.band_bar_db(B,n,BS)
    dB=M['decks'][1]['auto']; dA=M['decks'][0]['auto']
    print(os.path.basename(p), 's0',s0,'s',s,'e',e, 'B lanes', {k:len(v) for k,v in dB.items() if isinstance(v,list)})
    for k in range(s,e):
        bar=s0+k; ts=np.array([bar+0.5])
        print(f"  bar {bar:4d} A {alA[k]:6.1f} B {alB[k]:6.1f} B-A {alB[k]-alA[k]:6.1f}  Bgain {20*np.log10(_eval_lane(dB.get('gain'),ts)[0]+1e-9):6.1f} Again {20*np.log10(_eval_lane(dA.get('gain'),ts)[0]+1e-9):6.1f}")
