#!/usr/bin/env python3
"""On all-pass only: tracklist + MP3 to gdrive 'DJ Mixes Archive/mix10' (no public links)
and a box-local copy under /workspace/mixes/deliver/mix10_r6h."""
import json,os,sys,shutil,subprocess,time
from pathlib import Path

GAIN=sys.argv[1] if len(sys.argv)>1 else '?'
ROOT=Path('/workspace/mixes')
SRC2=ROOT/'src2'
DEST=ROOT/'deliver'/'mix10_r6h'
DEST.mkdir(parents=True,exist_ok=True)
META=SRC2/'mix10_r6h_meta.json'
MP3=SRC2/'mix10_r6h.mp3'
RCLONE=os.path.expanduser('~/bin/rclone')
REMOTE='gdrive:DJ Mixes Archive/mix10'
TITLE='DJ Grok Bot – Mix 10 r6h'

def sh(cmd,check=True):
  print('+',' '.join(cmd) if isinstance(cmd,list) else cmd,flush=True)
  r=subprocess.run(cmd,check=False,text=True,capture_output=True)
  if r.stdout: print(r.stdout,end='' if r.stdout.endswith('\n') else r.stdout+'\n',flush=True)
  if r.stderr: print(r.stderr,end='' if r.stderr.endswith('\n') else r.stderr+'\n',flush=True)
  if check and r.returncode!=0:
    raise SystemExit(f'command failed rc={r.returncode}: {cmd}')
  return r

# seed titles so gen_tracklist can fill names
titles={}
raw=json.load(open(ROOT/'mix10'/'titles.json'))
for k,v in raw.items():
  if isinstance(v,(list,tuple)) and len(v)>=2: titles[k]=f'{v[0]} – {v[1]}'
  elif isinstance(v,str) and v: titles[k]=v
M=json.load(open(META)); BAR=M['bar_sec']
order=[(M['plan'][0]['id'],0.0)]+[(t['b'],t['start_bar']*BAR) for t in M['trans']]
def fmt(s): return f"{int(s)//60}:{int(s)%60:02d}"
seed=DEST/'dj-mix-10-r6h-tracklist.md'
seed.write_text('\n'.join(
  f"{i}. {fmt(s)} {titles.get(b,b)} (youtu.be/{b})" for i,(b,s) in enumerate(order,1)
)+'\n')
sh(['python3',str(ROOT/'src'/'gen_tracklist.py'),str(META),str(seed),TITLE])

# 128k share copy + keep the render mp3
k128=DEST/'dj-mix-10-r6h-128k.mp3'
sh(['ffmpeg','-loglevel','error','-y','-i',str(MP3),'-c:a','libmp3lame','-b:a','128k',str(k128)])
shutil.copy2(MP3, DEST/'mix10_r6h.mp3')
# also keep meta + a short note
shutil.copy2(META, DEST/'mix10_r6h_meta.json')
(DEST/'GAIN.txt').write_text(f'gain={GAIN}\npassed {time.strftime("%Y-%m-%dT%H:%M:%S%z")}\n')

# Drive archive — copy only, never rclone link (no public links)
if not os.path.exists(RCLONE):
  raise SystemExit(f'missing rclone at {RCLONE}')
for local,name in ((k128,'dj-mix-10-r6h-128k.mp3'),
                   (DEST/'mix10_r6h.mp3','mix10_r6h.mp3'),
                   (seed,'dj-mix-10-r6h-tracklist.md')):
  remote=f'{REMOTE}/{name}'
  sh([RCLONE,'copyto',str(local),remote])
  ls=local.stat().st_size
  rs=sh([RCLONE,'lsjson',remote],check=True)
  import json as _j
  info=_j.loads(rs.stdout)
  rsize=info[0]['Size']
  print(f'verify {name} local={ls} remote={rsize}')
  if int(rsize)!=int(ls):
    raise SystemExit(f'Drive size mismatch for {name}')

print(f'DELIVERED gain={GAIN} tracks={len(order)} length={fmt(M["len_sec"])} to {REMOTE} and {DEST} (no public links)')
# report-friendly tracklist to stdout for the job log
print('--- tracklist ---')
print(seed.read_text())
