#!/usr/bin/env python3
"""Cleaner no-FAL backdrops: deep near-black base, smooth 2-tone saturated nebula, soft glow core, star field.
usage: procedural_backdrops2.py N outdir"""
import sys,os,numpy as np,colorsys
from PIL import Image,ImageFilter
n,out=int(sys.argv[1]),sys.argv[2]; os.makedirs(out,exist_ok=True)
W,H=960,540; yy,xx=np.mgrid[0:H,0:W]/H; xx=xx-W/H/2; yy=yy-.5
def noise(rng,s):
    g=rng.random((s+1,int(s*W/H)+1)); return np.asarray(Image.fromarray((g*255).astype('uint8')).resize((W,H),Image.BICUBIC),float)/255
HUES=[.93,.08,.50,.78,.45,.62,.98,.55,.83,.58,.12,.88,.03]  # per-track hue, distinct neighbours
for i in range(n):
    rng=np.random.default_rng(i*11+5)
    f=sum(noise(rng,2*2**o)/(1.7**o) for o in range(4)); f=(f-f.min())/(f.max()-f.min())
    g=sum(noise(rng,2*2**o)/(1.7**o) for o in range(3)); g=(g-g.min())/(g.max()-g.min())
    h=HUES[i%len(HUES)]
    c1=np.array(colorsys.hsv_to_rgb(h,.85,1.)); c2=np.array(colorsys.hsv_to_rgb((h+.12)%1,.75,1.))
    cx,cy=rng.uniform(-.3,.3),rng.uniform(-.15,.15)
    core=np.exp(-((xx-cx)**2+(yy-cy)**2)/.18)
    neb=np.clip((f-.35)/.65,0,1)**1.8*(.35+.9*core)
    img=np.full((H,W,3),[.01,.01,.025])+neb[...,None]*(c1*g[...,None]+c2*(1-g[...,None]))*.85
    img+=(core**3)[...,None]*c1*.25
    stars=(rng.random((H,W))>.9993).astype(float)*rng.uniform(.4,1,(H,W))
    st=np.asarray(Image.fromarray((stars*255).astype('uint8')).filter(ImageFilter.GaussianBlur(.8)),float)/255*3
    img+=st[...,None]
    Image.fromarray((np.clip(img,0,1)**1.05*255).astype('uint8')).filter(ImageFilter.GaussianBlur(1.2)).save(f'{out}/track{i+1}.jpg',quality=94)
