import json,subprocess,sys
from drift import drift
for b in sys.argv[1:]:
  g=json.load(open(f'st/{b}.json'));d=drift(f'st/{b}.wav');new=g['orig_bpm']*(1-d)
  subprocess.run(['python3','prep.py',f'wav/{b}.wav',str(new)],capture_output=True)
  print(b,round(g['orig_bpm'],3),'->',round(new,3),'drift now',round(drift(f'st/{b}.wav')*1000,3),flush=True)
