"""Regenerate the big audio caches from the sources, never touching the (hand-fixed) grids st/<id>.json.
wav/<id>.wav : 16-bit decode of <id>.m4a (or <id>.flac)
st/<id>.wav  : from wav/<id>.wav, same steps as prep.py (bit-exact vs the cached stems) (-9 dB, f32, rubberband -3 to 174 at the json's orig_bpm)
usage: python3 restore_audio.py [ids...]   (default: every st/<id>.json); idempotent, skips files that exist."""
import os,sys,json,subprocess
T=174.0;os.chdir(os.path.dirname(os.path.abspath(__file__)))
def src(b):
  for e in('m4a','flac'):
    if os.path.exists(f'{b}.{e}'):return f'{b}.{e}'
def restore(b):
  s=src(b)
  if not s:raise SystemExit(f'no source for {b} (need {b}.m4a or {b}.flac)')
  os.makedirs('wav',exist_ok=True)
  if not os.path.exists(f'wav/{b}.wav'):subprocess.run(['ffmpeg','-loglevel','error','-y','-i',s,'-ar','44100','-c:a','pcm_s16le',f'wav/{b}.wav'],check=True)
  out=f'st/{b}.wav'
  if os.path.exists(out) or not os.path.exists(f'st/{b}.json'):return
  bpm=float(json.load(open(f'st/{b}.json'))['orig_bpm']);tmp=f'st/{b}_in.wav'
  subprocess.run(['ffmpeg','-loglevel','error','-y','-i',f'wav/{b}.wav','-af','volume=-9dB','-c:a','pcm_f32le',tmp],check=True)
  if abs(T/bpm-1)<2e-4:os.replace(tmp,out)
  else:subprocess.run(['rubberband','-3','-F','-T',str(T/bpm),'-q',tmp,out],check=True);os.remove(tmp)
def ids():return sorted(f[:-5] for f in os.listdir('st') if f.endswith('.json'))
if __name__=='__main__':
  for b in sys.argv[1:] or ids():
    if src(b):restore(b)
