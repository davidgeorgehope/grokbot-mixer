#!/usr/bin/env python3
"""No-FAL backdrops: domain-warped fBm nebula per track, palette-tinted. usage: procedural_backdrops.py N outdir"""
import sys,os,numpy as np
from PIL import Image,ImageFilter
n,out=int(sys.argv[1]),sys.argv[2]; os.makedirs(out,exist_ok=True)
W,H=960,540
def noise(rng,s):
    g=rng.random((s+1,s+1)); im=Image.fromarray((g*255).astype('uint8')).resize((W,H),Image.BICUBIC); return np.asarray(im,float)/255
for i in range(n):
    rng=np.random.default_rng(i*7+3); f=sum(noise(rng,4*2**o)/(2**o) for o in range(5))/1.94
    w=sum(noise(rng,3*2**o)/(2**o) for o in range(4))/1.9
    v=np.clip((f*0.6+w*0.6-0.35)*1.6,0,1)**1.6
    hue=np.array([0,.33,.67])+i*0.137
    c1=0.5+0.5*np.cos(6.283*(hue)); c2=0.5+0.5*np.cos(6.283*(hue+.25))
    img=(v[...,None]*(c1*w[...,None]+c2*(1-w[...,None]))+ (v**6)[...,None]*0.8)
    Image.fromarray((np.clip(img,0,1)*255).astype('uint8')).filter(ImageFilter.GaussianBlur(2)).save(f'{out}/track{i+1}.jpg',quality=92)
