"""BPM probe used by add*.sh / prep.

Searches 70-180 BPM (not just 170-177). Returns (bpm, meta) where meta explains the decision.
Rejects tracks whose true pulse is not DnB (~170-178) or honest half-time (~85-89 with a real
165-180 harmonic). That bug previously stamped Sub Focus & Wilkinson – Just Hold On (124 BPM
UK-breaks) as 170.5 and caused the Deeper->JHO car crash.
"""
import librosa, numpy as np, sys
from scipy.signal import find_peaks

DNB_LO, DNB_HI = 170.0, 178.0
HALF_LO, HALF_HI = 85.0, 89.0
SEARCH_LO, SEARCH_HI = 70.0, 180.0

def _onset_ac(y, sr, hop=512):
  oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
  oe = oe - oe.mean()
  ac = np.correlate(oe, oe, mode='full')
  ac = ac[len(ac)//2:]
  ac = ac / max(ac[0], 1e-12)
  fps = sr / hop
  return ac, fps

def _band_max(ac, fps, blo, bhi):
  lo = int(60 * fps / bhi); hi = int(60 * fps / blo)
  if hi <= lo: return 0.0, None
  seg = ac[lo:hi + 1]
  i = int(np.argmax(seg))
  lag = lo + i
  return float(seg[i]), 60.0 * fps / lag

def _comb_score(oe, ot, bpm, n_ph=24):
  """Mean onset energy on a bpm grid; used to refine within DnB band."""
  per = 60.0 / bpm
  n = int(ot[-1] / per)
  if n < 8: return -1.0, 0.0
  best = (-1.0, 0.0)
  for ph in np.arange(0, per, per / n_ph):
    s = float(np.interp(ph + np.arange(n) * per, ot, oe).sum() / n)
    if s > best[0]: best = (s, ph)
  return best

def analyze(path, sr=22050, hop=512):
  y, sr = librosa.load(path, sr=sr, mono=True)
  ac, fps = _onset_ac(y, sr, hop=hop)
  # top autocorr peaks in search range
  lo = int(60 * fps / SEARCH_HI); hi = int(60 * fps / SEARCH_LO)
  seg = ac[lo:hi]
  peaks, props = find_peaks(seg, height=0.12, distance=3)
  tops = []
  if len(peaks):
    for i in np.argsort(props['peak_heights'])[::-1][:10]:
      lag = peaks[i] + lo
      tops.append((float(60 * fps / lag), float(props['peak_heights'][i])))
  dnb_h, dnb_bpm = _band_max(ac, fps, DNB_LO, DNB_HI)
  half_h, half_bpm = _band_max(ac, fps, HALF_LO, HALF_HI)
  brk_h, brk_bpm = _band_max(ac, fps, 118, 132)
  best_h = tops[0][1] if tops else 0.0
  # Accept if DnB band is strong, or half-time with a real DnB harmonic
  ok = False
  reason = ''
  if dnb_h >= 0.22 and (best_h < 1e-9 or dnb_h >= 0.40 * best_h):
    ok = True
    reason = 'dnb'
  elif half_h >= 0.40 and dnb_h >= 0.30 and dnb_h >= 0.35 * best_h:
    ok = True
    reason = 'half-time-dnb'
  # Reject UK-breaks / house dominant over DnB
  if brk_h >= 0.50 and brk_h > dnb_h and dnb_h < 0.45:
    ok = False
    reason = f'reject-breaks({brk_bpm:.1f})'
  if not ok and not reason:
    reason = f"reject-no-dnb(best={tops[0][0]:.1f})" if tops else 'reject-no-dnb'
  # Refine bpm inside DnB band with comb fit (legacy precision)
  bpm = None
  if ok:
    oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=64)
    ot = np.arange(len(oe)) * 64 / sr
    best = (-1.0, 174.0, 0.0)
    for b in np.arange(DNB_LO, DNB_HI + 1e-9, 0.01):
      s, ph = _comb_score(oe, ot, b, n_ph=24)
      if s > best[0]: best = (s, b, ph)
    b0 = best[1]
    for b in np.arange(b0 - 0.02, b0 + 0.02, 0.001):
      s, ph = _comb_score(oe, ot, b, n_ph=96)
      if s > best[0]: best = (s, b, ph)
    bpm = float(best[1])
  meta = dict(ok=ok, reason=reason, bpm=bpm, dnb=(dnb_bpm, dnb_h), half=(half_bpm, half_h),
              breaks=(brk_bpm, brk_h), tops=tops[:6])
  return bpm, meta

def pbpm(path):
  """Back-compat: return bpm float, or raise SystemExit/ValueError if rejected."""
  bpm, meta = analyze(path)
  if not meta['ok'] or bpm is None:
    raise ValueError(f"not DnB: {meta['reason']} tops={meta['tops'][:3]} dnb={meta['dnb']} breaks={meta['breaks']}")
  return bpm

if __name__ == '__main__':
  reject = '--allow-reject' in sys.argv
  args = [a for a in sys.argv[1:] if not a.startswith('--')]
  rc = 0
  for p in args:
    try:
      bpm, meta = analyze(p)
      if meta['ok']:
        print(p, round(bpm, 3), meta['reason'], flush=True)
      else:
        print(p, 'REJECT', meta['reason'], 'tops', [(round(b,1), round(h,2)) for b,h in meta['tops'][:4]], flush=True)
        rc = 1
    except Exception as e:
      print(p, 'ERROR', e, flush=True); rc = 1
  sys.exit(rc)
