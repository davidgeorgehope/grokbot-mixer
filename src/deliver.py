#!/usr/bin/env python3
"""Auto-delivery after a passing build: 128k mp3, tracklist, iCloud (latest only), visuals render, YouTube public upload, backup, link files.
usage: deliver.py NN META MP3 "Mix NN title"   (Drive upload is done by the agent with the UploadFile tool from deliver/NN/)
Idempotent: each step writes a marker in deliver/NN/ and is skipped when present."""
import json,os,re,sys,subprocess,glob,time
NN,META,MP3,TITLE=sys.argv[1:5];R='/workspace/mixes';D=f'{R}/deliver/{NN}';os.makedirs(D,exist_ok=True)
P=f'{R}/PROGRESS_mix06.md'
def log(m):open(P,'a').write(f"- {time.strftime('%H:%M')} ET: [deliver {NN}] {m}\n")
def sh(c):
  r=subprocess.run(c,shell=True,capture_output=True,text=True);open(f'{D}/deliver.log','a').write(f'$ {c}\n{r.stdout[-3000:]}{r.stderr[-3000:]}\n');return r
def step(k):return os.path.exists(f'{D}/.{k}')
def done(k):open(f'{D}/.{k}','w').write(time.ctime())
M=json.load(open(META));BAR=M['bar_sec']
# titles: this mix's titles.json (string or [artist, title]), then mix06 fallback, then tracklists
T={}
def _ingest_titles(path, overwrite=False):
  if not os.path.exists(path): return
  raw=json.load(open(path))
  for k,v in raw.items():
    if isinstance(v,(list,tuple)) and len(v)>=2: s_=f'{v[0]} – {v[1]}'
    elif isinstance(v,str) and v: s_=v
    else: continue
    if overwrite or k not in T: T[k]=s_
num=''.join(c for c in NN if c.isdigit()) or NN
_ingest_titles(f'{R}/mix{num}/titles.json', overwrite=True)
_ingest_titles(f'{R}/mix06/titles.json', overwrite=False)
for f in glob.glob(f'{R}/*tracklist*.md')+glob.glob(f'{R}/mix{num}/*tracklist*.md'):
  for l in open(f):
    m=re.match(r'\s*\d+\.\s+[\d:]+\s+(.*?)(?:\s+\[\w+\])?\s+\(youtu\.be/([\w-]+)\)',l)
    if m and not m.group(1).startswith(m.group(2)): T.setdefault(m.group(2),m.group(1))
order=[(M['plan'][0]['id'],0.0)]+[(t['b'],t['start_bar']*BAR) for t in M['trans']]
fmt=lambda s:f"{int(s)//60}:{int(s)%60:02d}"
TL=f'{D}/dj-mix-{NN}-tracklist.md';K128=f'{D}/dj-mix-{NN}-128k.mp3'
if not step('tl'):
  open(TL,'w').write('\n'.join(f"{i}. {fmt(s)} {T.get(b,b)} (youtu.be/{b})" for i,(b,s) in enumerate(order,1))+'\n')
  sh(f"python3 {R}/src/gen_tracklist.py {META} {TL} 'DJ Grok Bot – {TITLE}'");done('tl')
if not step('k128'):sh(f'ffmpeg -loglevel error -y -i {MP3} -c:a libmp3lame -b:a 128k {K128}');done('k128');log(f'128k + tracklist in {D}')
if not step('icloud'):
  n=int(re.sub(r'\D','',NN[:2]) or 0)
  r=sh(f"cd {R}/src && bash sync_icloud.sh {K128} {TL} {n} 'DJ Grok Bot – {TITLE}'")
  if r.returncode==0:done('icloud');log('iCloud DJ Mixes synced')
  else:log('iCloud sync FAILED (deliver.log)')
# visuals
V=f'{R}/visuals';PY=f'{V}/venv/bin/python';KEY=f'd{NN}';OUT=f'{V}/dj-mix-{NN}-visuals-1080p30.mp4'
if not step('yt'):
  tr=[];ov=float(M['trans'][0]['end_bar']-M['trans'][0]['start_bar'])*BAR
  KM={}
  for tt in M['trans']:
    ka,kb=(tt.get('keys') or '->').split('->')
    if ka and ka!='None': KM.setdefault(tt['a'],ka)
    if kb and kb!='None': KM.setdefault(tt['b'],kb)
  for i,(b,st) in enumerate(order):
    a,_,t=T.get(b,b).partition(' – ');ft='';m=re.match(r'(.*?)\s+(ft\..*)',a)
    if m:a,ft=m.groups()
    e=dict(artist=a,title=t or b,feat=ft,start=round(st+(ov if i else 0),2),key=KM.get(b,''))
    if i:e['mix_in']=round(st,2)
    tr.append(e)
  json.dump(dict(overlap=round(ov,2),tracks=tr),open(f'{V}/code/{KEY}_tracks.json','w'),indent=1)
  desc=f"DJ Grok Bot – {TITLE}: {round(M['len_sec']/60)} minutes of liquid drum & bass at 174 BPM, mixed and visualised by Grok Bot. Audio-reactive visuals generated in code.\n\nTracklist:\n"+'\n'.join(f"{fmt(s)} {T.get(b,b)}" for b,s in order)
  open(f'{D}/yt_desc.txt','w').write(desc)
  log('visuals render start (Camelot Chladni Plate)')
  ok=sh(f"cd {V} && {PY} code/analyze_mix.py {K128} code/{KEY}_tracks.json code/{KEY}_analysis.json && {PY} code/render_chladni.py code/{KEY}_analysis.json {K128} {OUT}").returncode==0
  dur=sh(f'ffprobe -v error -show_entries format=duration -of csv=p=0 {OUT}').stdout.strip();ad=sh(f'ffprobe -v error -show_entries format=duration -of csv=p=0 {K128}').stdout.strip()
  if not ok or not dur or abs(float(dur)-float(ad))>2:log(f'visuals FAILED dur={dur} audio={ad}');sys.exit(1)
  r=sh(f"cd {R}/src && python3 yt_upload.py {OUT} --title 'DJ Grok Bot – {TITLE} | Liquid Drum & Bass' --description \"$(cat {D}/yt_desc.txt)\" --privacy public")
  m=re.search(r'https://youtu.be/[\w-]+',r.stdout+r.stderr)
  if not m:log('YouTube upload FAILED (deliver.log)');sys.exit(1)
  open(f'{D}/youtube.link','w').write(m.group(0));done('yt');log(f'YouTube public {m.group(0)}')
  sh(f'rm -rf {OUT} {V}/tex_{KEY}')
if not step('bk'):
  if sh('bash /workspace/backup_mixer_to_git.sh').returncode==0:done('bk');log('backup ok')
  else:log('backup FAILED')
open(f'{D}/READY_FOR_DRIVE','w').write(K128);log('ready for Drive upload (agent)')
