"""Admit a transition only if both studio sources match the pro mix.

Locates each studio track in the pro clip with the same sub-band-power
cross-correlation used by control_curves (not a key-only chroma hash, which
cannot tell two liquid tracks apart). A pair is admitted only if:

- each source scores a strong locate hit (peak z and normalised cc)
- outgoing hits the first half of the clip, incoming the later half
- native tempo is close to 174 (no large stretch)
"""
from __future__ import annotations
import json, os, subprocess, sys
import numpy as np

SR = 22050
Z_MIN = 6.0
CC_MIN = 0.28
BPM_LO, BPM_HI = 169.0, 179.0  # ~3% of 174

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'eval'))
import control_curves as CC

def _load(path, sr=SR, t0=None, dur=None):
    cmd = ['ffmpeg', '-v', 'error']
    if t0 is not None: cmd += ['-ss', f'{float(t0):.3f}']
    cmd += ['-i', path]
    if dur is not None: cmd += ['-t', f'{float(dur):.3f}']
    cmd += ['-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

def locate_in(mix_y, src_y, chunk_s=6.0, hop_s=3.0):
    Fm, Ft = CC.bandpow(mix_y), CC.bandpow(src_y)
    hits, _ = CC.locate(Fm, Ft, chunk_s=chunk_s, hop_s=hop_s)
    if hits is None or len(hits) == 0:
        return dict(z=0.0, cc=0.0, mix_t=None, track_t=None, n=0)
    i = int(np.argmax(hits[:, 3]))
    return dict(z=round(float(hits[i, 3]), 3), cc=round(float(hits[i, 2]), 4),
                mix_t=round(float(hits[i, 1]), 3), track_t=round(float(hits[i, 0]), 3),
                n=int(len(hits)))

def native_bpm(path):
    """Detector BPM from a short decode. None if analysis fails."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src2'))
    try:
        import pbpm
        # analyze wants a readable file; m4a may fail soundfile — decode a 45s mid slice
        tmp = path + '.__vm.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-ss','20','-i',path,'-t','90','-ac','1','-ar','44100',tmp], check=True)
        _bpm, meta = pbpm.analyze(tmp)
        try: os.remove(tmp)
        except OSError: pass
        return dict(bpm=None if meta.get('bpm') is None else round(float(meta['bpm']), 3),
                    ok=bool(meta.get('ok')), reason=meta.get('reason'))
    except Exception as e:
        try: os.remove(path + '.__vm.wav')
        except OSError: pass
        return dict(bpm=None, ok=False, reason=str(e)[-160:])

def match_pair(pro_clip, src_a, src_b, incoming_off=24.0, check_bpm=True):
    out = dict(a={}, b={}, passed=False, thresh=dict(z=Z_MIN, cc=CC_MIN, bpm=(BPM_LO, BPM_HI)))
    if not (os.path.exists(pro_clip) and os.path.exists(src_a) and os.path.exists(src_b)):
        out['error'] = 'missing file'; return out
    mix = _load(pro_clip)
    dur = len(mix) / SR
    ya, yb = _load(src_a), _load(src_b)
    out['a']['locate'] = locate_in(mix, ya)
    out['b']['locate'] = locate_in(mix, yb)
    reasons = []
    def ok_side(side, want_early):
        loc = out[side]['locate']
        if loc['z'] < Z_MIN or loc['cc'] < CC_MIN:
            reasons.append(f'{side}: weak locate z={loc["z"]} cc={loc["cc"]}')
            return False
        mt = loc['mix_t']
        if mt is None:
            reasons.append(f'{side}: no mix time'); return False
        if want_early and mt > incoming_off + 10:
            reasons.append(f'{side}: locate at {mt:.1f}s is after the blend, expected outgoing')
            return False
        if (not want_early) and mt < incoming_off - 6:
            reasons.append(f'{side}: locate at {mt:.1f}s is before the blend, expected incoming')
            return False
        return True
    a_ok = ok_side('a', True)
    b_ok = ok_side('b', False)
    if check_bpm:
        for side, path in (('a', src_a), ('b', src_b)):
            info = native_bpm(path)
            out[side]['bpm'] = info
            bpm = info.get('bpm')
            if bpm is None or not (BPM_LO <= bpm <= BPM_HI):
                reasons.append(f'{side}: native BPM {bpm} outside {BPM_LO}-{BPM_HI} ({info.get("reason")})')
                if side == 'a': a_ok = False
                else: b_ok = False
    out['reasons'] = reasons
    out['passed'] = bool(a_ok and b_ok)
    return out

if __name__ == '__main__':
    print(json.dumps(match_pair(*sys.argv[1:]), indent=2))
