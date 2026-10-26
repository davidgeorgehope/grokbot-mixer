#!/usr/bin/env python3
"""Audio-reactive visuals renderer (moderngl/EGL headless -> ffmpeg).
usage: render_visuals.py analysis.json mix.mp3 out.mp4 [--start S --dur D --w 1920 --h 1080 --tex DIR --scale 1.0]
Per track: palette + backdrop texture (tex/trackN.jpg). Scene crossfades across each transition overlap,
title card at each track change. Driven by kick/snare onsets, bass/mid/high energy and the 174 BPM grid."""
import json,argparse,subprocess,numpy as np,moderngl,os,time
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ap=argparse.ArgumentParser();ap.add_argument('analysis');ap.add_argument('mix');ap.add_argument('out')
ap.add_argument('--start',type=float,default=0);ap.add_argument('--dur',type=float,default=None)
ap.add_argument('--w',type=int,default=1920);ap.add_argument('--h',type=int,default=1080)
ap.add_argument('--scale',type=float,default=1.0,help='internal render scale (upscaled by ffmpeg)')
ap.add_argument('--tex',default=os.path.join(os.path.dirname(__file__),'..','tex'))
ap.add_argument('--crf',type=int,default=20);ap.add_argument('--abr',default='192k')
a=ap.parse_args(); A=json.load(open(a.analysis)); fps=A['fps']
N=len(A['bass']); dur=a.dur or (A['duration']-a.start); f0=int(a.start*fps); nf=min(int(dur*fps),N-f0)
W,H=int(a.w*a.scale)//2*2,int(a.h*a.scale)//2*2
tracks=A['tracks']; starts=[t['start'] for t in tracks]; OV=A['overlap']; spb=60/A['bpm']
# palettes: iq cosine palettes (a,b,c,d) + accent
PAL=[((.6,.45,.5),(.4,.3,.35),(1,1,1),(0,.1,.2),(1,.7,.6)),
     ((.6,.45,.35),(.45,.35,.3),(1,1,.8),(0,.15,.3),(1,.75,.4)),
     ((.3,.5,.5),(.3,.35,.3),(1,1,1),(.6,.5,.35),(.9,.8,.5)),
     ((.45,.3,.6),(.45,.3,.4),(1,1,1),(.7,.9,.1),(.9,.4,1)),
     ((.3,.55,.5),(.3,.4,.35),(1,1,1),(.4,.25,.65),(.4,1,.85)),
     ((.35,.4,.6),(.3,.3,.4),(1,1,1),(.55,.6,.7),(.75,.85,1)),
     ((.5,.25,.35),(.45,.25,.3),(1,1,1),(0,.2,.45),(1,.3,.45))]
ctx=moderngl.create_context(standalone=True,backend='egl')
VS="""#version 330
in vec2 p; out vec2 uv; void main(){uv=p*.5+.5; gl_Position=vec4(p,0,1);}"""
FS=open(os.path.join(os.path.dirname(__file__),os.environ.get('FRAG','liquid.frag'))).read()
prog=ctx.program(vertex_shader=VS,fragment_shader=FS)
vbo=ctx.buffer(np.array([-1,-1,1,-1,-1,1,1,1],'f4')); vao=ctx.simple_vertex_array(prog,vbo,'p')
fbo=ctx.simple_framebuffer((W,H)); fbo.use()
def load_tex(img):
    t=ctx.texture(img.size,4,img.convert('RGBA').transpose(Image.FLIP_TOP_BOTTOM).tobytes()); t.repeat_x=t.repeat_y=False
    t.filter=(moderngl.LINEAR,moderngl.LINEAR); return t
texs=[load_tex(Image.open(f"{a.tex}/track{i+1}.jpg").resize((960,540))) for i in range(len(tracks))]
def font(sz,bold=False):
    for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf'%('-Bold' if bold else ''),'/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf']:
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return ImageFont.load_default()
def card(i,t):
    w,h=1920,1080; im=Image.new('RGBA',(w,h),(0,0,0,0)); d=ImageDraw.Draw(im)
    x,y=120,h-300; acc=tuple(int(255*c) for c in PAL[i%7][4])
    d.text((x,y),f"{i+1:02d}  ·  {t['artist'].upper()}",font=font(34),fill=(255,255,255,200))
    d.text((x-4,y+48),t['title'],font=font(104,True),fill=(255,255,255,255))
    if t.get('feat'): d.text((x,y+176),t['feat'],font=font(34),fill=acc+(230,))
    d.rectangle((x,y-26,x+90,y-21),fill=acc+(255,))
    sh=im.filter(ImageFilter.GaussianBlur(14)); sh2=Image.new('RGBA',im.size,(0,0,0,0)); sh2.paste((0,0,0,150),mask=sh.split()[3])
    return load_tex(Image.alpha_composite(sh2,im))
cards=[card(i,t) for i,t in enumerate(tracks)]
for k,u in [('texA',0),('texB',1),('card',2)]: prog[k]=u
prog['res']=(W,H)
def U(k,v):
    if k in prog: prog[k].value=v
ff=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(fps),'-i','-',
  '-ss',str(a.start),'-t',str(nf/fps),'-i',a.mix,'-map','0:v','-map','1:a','-vf',f'vflip,scale={a.w}:{a.h}:flags=lanczos' if a.scale!=1 else 'vflip',
  '-c:v','libx264','-preset','medium','-crf',str(a.crf),'-pix_fmt','yuv420p','-c:a','aac','-b:a',a.abr,'-shortest','-movflags','+faststart',a.out],stdin=subprocess.PIPE)
def trk(t):
    i=max(j for j,s in enumerate(starts) if s<=t+1e-6); return i
def sm(x): x=min(max(x,0),1); return x*x*(3-2*x)
g=lambda k,i: A[k][min(i,N-1)]
# accumulated "flow time": advances faster with energy
flow=0.0; kickacc=0.0
for i in range(f0): flow+= (0.35+0.9*g('bass',i)+0.4*g('high',i))/fps
T0=time.time()
for n in range(nf):
    i=f0+n; t=i/fps
    flow+=(0.35+0.9*g('bass',i)+0.4*g('high',i))/fps; kickacc+=g('kick',i)/fps
    ti=trk(t); nxt=ti+1 if ti+1<len(starts) else None
    # transition: incoming = ti while within OV of its start; blend from previous
    if ti>0 and t-starts[ti]<OV: ia,ib,m=ti-1,ti,sm((t-starts[ti])/OV)
    else: ia,ib,m=ti,ti,0.0
    texs[ia].use(0); texs[ib].use(1)
    pa,pb=PAL[ia%7],PAL[ib%7]
    for j,nm in enumerate(['pa','pb','pc','pd','acc']):
        U(nm+'A',pa[j]); U(nm+'B',pb[j])
    # title card: appears at bass swap (half overlap) for incoming track, or at t=2 for track 1
    ct=t-(starts[ti]+(OV/2 if ti>0 else 0)-1.0)
    if ti>0 and t-starts[ti]<OV/2-1.0: ci,ct=ti-1, t-(starts[ti-1]+(OV/2 if ti>1 else 0)-1.0)
    else: ci=ti
    ca=sm(ct/1.2)*(1-sm((ct-7)/1.5)) if ct>=0 else 0
    cards[ci].use(2); U('cardA',ca); U('cardT',max(ct,0))
    bp=((t-A['beat_offset'])/spb)
    for k,v in [('time',t),('flow',flow),('kacc',kickacc),('mixAB',m),('bass',g('bass',i)),('mid',g('mid',i)),('high',g('high',i)),
                ('kick',g('kick',i)),('snare',g('snare',i)),('rms',g('rms',i)),('beat',bp),('seedA',float(ia)),('seedB',float(ib))]:
        U(k,v)
    vao.render(moderngl.TRIANGLE_STRIP)
    ff.stdin.write(fbo.read(components=3))
    if n%300==0: print(f'{n}/{nf} {n/max(time.time()-T0,1e-3):.2f} fps',flush=True)
ff.stdin.close(); ff.wait(); el=time.time()-T0
print(f'done {nf} frames in {el:.0f}s = {nf/el:.2f} fps')
