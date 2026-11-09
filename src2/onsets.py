"""Per-bar onset envelope cache (st/<id>.onset.npy).

mix_simple.onsets() used to create this lazily during a render. The planner's
pair_feats.build loaded the file with a raw np.load, so a newly prepped track
(wav and json only) crashed the search. Call ensure(id) from prep, the planner,
and the engine so the cache is created on first use.
"""
import os, numpy as np
from engine import track, SR, BAR

def ensure(b):
  f = f'st/{b}.onset.npy'
  if os.path.exists(f):
    return np.load(f)
  import librosa
  tr = track(b)
  x = tr['st']['mix']
  x = x.mean(1) if x.ndim > 1 else x
  L = int(BAR * SR)
  out = []
  for k in range(tr['nb']):
    j = int(round((tr['d0'] + k * BAR) * SR))
    seg = np.asarray(x[max(0, j):j + L], np.float32)
    if len(seg) < L:
      seg = np.pad(seg, (0, L - len(seg)))
    out.append(librosa.onset.onset_strength(y=seg, sr=SR, hop_length=512))
  n = min(len(o) for o in out)
  arr = np.array([o[:n] for o in out])
  np.save(f, arr)
  return arr
