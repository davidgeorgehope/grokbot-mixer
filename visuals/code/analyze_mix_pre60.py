#!/usr/bin/env python3
"""Analyse a mix for visuals: per-video-frame bass/mid/high/rms, kick+snare onsets, beat grid.
usage: analyze_mix.py mix.mp3 meta.json(or tracklist json) out.json [--fps 30] [--bpm 174]
Tracklist JSON: {"tracks":[{"title":..,"artist":..,"start":sec}], "overlap":sec}"""
import sys, json, subprocess, numpy as np, argparse
from scipy.signal import stft
ap=argparse.ArgumentParser(); ap.add_argument('mix'); ap.add_argument('tracks'); ap.add_argument('out')
ap.add_argument('--fps',type=float,default=30); ap.add_argument('--bpm',type=float,default=174); ap.add_argument('--lag',type=float,default=0.0,help='delay envelopes (s) to correct STFT lead')
a=ap.parse_args(); SR=22050
pcm=subprocess.run(['ffmpeg','-v','error','-i',a.mix,'-ac','1','-ar',str(SR),'-f','f32le','-'],capture_output=True).stdout
x=np.frombuffer(pcm,np.float32); dur=len(x)/SR
hop=256; f,t,Z=stft(x,SR,nperseg=2048,noverlap=2048-hop,boundary=None); S=np.abs(Z)
def band(lo,hi): return S[(f>=lo)&(f<hi)].sum(0)
bands={'bass':band(25,150),'kick':band(40,110),'snare':band(1500,5000),'mid':band(150,2000),'high':band(5000,11000)}
def flux(b):
    l=np.log1p(b*10); d=np.maximum(0,np.diff(l,prepend=l[0])); return d
def norm(v,p=98):
    return np.clip(v/(np.percentile(v,p)+1e-9),0,1.5)
fr=SR/hop
def to_frames(v):
    n=int(dur*a.fps); tt=np.arange(n)/a.fps; return np.interp(tt,t+a.lag,v)
def env(v,att,rel):  # smooth with attack/release in seconds at stft rate
    o=np.zeros_like(v); ka=1-np.exp(-1/(att*fr)); kr=1-np.exp(-1/(rel*fr)); s=0
    for i,x_ in enumerate(v): s+= (x_-s)*(ka if x_>s else kr); o[i]=s
    return o
out={'fps':a.fps,'duration':dur,'bpm':a.bpm}
for k in ['bass','mid','high']:
    out[k]=np.round(to_frames(norm(env(bands[k],0.02,0.25))),3).tolist()
out['rms']=np.round(to_frames(norm(env(S.sum(0),0.05,0.5))),3).tolist()
kf=flux(bands['kick']); sf=flux(bands['snare'])
# beat grid: fold kick flux on 174bpm period, find phase
per=60/a.bpm; ph=np.linspace(0,per,200,endpoint=False)
score=[np.interp((np.arange(0,dur-per,per)+p)*fr,np.arange(len(kf)),kf).sum() for p in ph]
p0=(ph[int(np.argmax(score))]+a.lag)%per; out['beat_offset']=float(p0)
# onset envelopes: peaky, fast release (decays drawn in shader)
for name,v,rel in [('kick',kf,0.12),('snare',sf,0.15)]:
    v=norm(v,99.5); v=np.where(v>0.35,v,0); out[name]=np.round(to_frames(env(v,0.005,rel)),3).tolist()
tr=json.load(open(a.tracks)); out['tracks']=tr['tracks']; out['overlap']=tr.get('overlap',per*4*16)
json.dump(out,open(a.out,'w')); print('dur',dur,'beat_offset',p0,'frames',len(out['bass']))
