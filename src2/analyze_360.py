import numpy as np,soundfile as sf,json,librosa
from scipy.signal import butter,sosfiltfilt
SR=44100;T=174.0;BAR=4*60/T
y,_=sf.read('master.wav',dtype='float32');m=y.mean(1)
meta=json.load(open('mix360_meta.json'));K=json.load(open('keys_full.json')) if True else {}
dur=len(m)/SR;nb=int(dur/BAR)
# phase check: onset env vs 16th grid per 8-bar window
hop=256;o=librosa.onset.onset_strength(y=librosa.resample(m,orig_sr=SR,target_sr=22050),sr=22050,hop_length=hop)
fr=22050/hop;ph=[]
for w in range(0,nb-8,8):
  t0=w*BAR;seg=o[int(t0*fr):int((t0+8*BAR)*fr)];best=None
  sc=[seg[(np.round((np.arange(0,8*BAR,60/T/2)+off/1000)*fr)).astype(int).clip(0,len(seg)-1)].mean() for off in range(-40,41,2)]
  ph.append(int(range(-40,41,2)[int(np.argmax(sc))]))
lo=sosfiltfilt(butter(2,150,'low',fs=SR,output='sos'),m);hi=sosfiltfilt(butter(2,4000,'high',fs=SR,output='sos'),m)
db=lambda x:float(20*np.log10(np.sqrt(np.mean(x**2))+1e-9))
bars=[dict(i=i,t=round(i*BAR,3),rms=round(db(m[int(i*BAR*SR):int((i+1)*BAR*SR)]),2),low=round(db(lo[int(i*BAR*SR):int((i+1)*BAR*SR)]),2),high=round(db(hi[int(i*BAR*SR):int((i+1)*BAR*SR)]),2)) for i in range(nb)]
json.dump(dict(phase_ms_per_8bars=ph),open('phase_360.json','w'))
print('phase ms',ph)
A=dict(bpm=T,duration_sec=dur,beat_sec=60/T,bar_sec=BAR,beats=[round(i*60/T,4) for i in range(int(dur*T/60))],bars=[b['t'] for b in bars],phrases_16bar=[round(i*BAR,3) for i in range(0,nb,16)],energy_per_bar=bars,segments=[dict(id=d['id'],start_sec=d['start_bar']*BAR,end_sec=d['end_bar']*BAR,drop_sec=(d['drop_bar']*BAR if d['drop_bar'] is not None else None),acapella=d['acap']) for d in meta['decks']],transitions=[dict(t['tech'] and t,start_sec=t['start_bar']*BAR,swap_sec=t['swap_bar']*BAR,end_sec=t['end_bar']*BAR) for t in meta['trans']])
json.dump(A,open('../dj-mix-03-60-analysis.json','w'),default=float)
