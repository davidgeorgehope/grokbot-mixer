"""Cut pro transition clips and record the two source ids + tracklist hint window.

The recreation engine is allowed the hint (how long A had been playing when B
was listed) but must never load the pro clip.
"""
from __future__ import annotations
import json, os, subprocess, hashlib
import paths

PRE, POST = 24.0, 40.0  # seconds around the incoming's listed start

def _cut(src, dest, t0, dur):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{max(0,t0):.3f}','-i',src,'-t',f'{dur:.3f}',
                    '-ac','2','-ar','44100', dest], check=True)
    return dest

def transitions_from_mix(mix):
    """Build transition records from corpus mix.tracks (each with t and optional source_yt)."""
    tracks = list(mix.get('tracks') or [])
    tracks = [t for t in tracks if t.get('t') is not None]
    tracks.sort(key=lambda t: t['t'])
    out = []
    for i in range(len(tracks)-1):
        a, b = tracks[i], tracks[i+1]
        t_in = float(b['t'])
        t_out = float(a['t'])
        # skip pairs with a large hole: our catalog omitted in-between tracks (not a real blend)
        if t_in - t_out > 360:
            continue
        if not a.get('source_yt') or not b.get('source_yt'):
            continue
        nxt = tracks[i+2]['t'] if i+2 < len(tracks) else t_in + 90
        window = dict(mix_t_a=t_out, mix_t_b=t_in, mix_t_next=float(nxt),
                      hint_a_played_sec=t_in - t_out)
        out.append(dict(
            id=f"{mix['id']}__{i:02d}",
            mix_id=mix['id'], dj=mix.get('dj'), split=mix.get('split'),
            a=dict(title=a.get('title'), yt=a.get('source_yt'), t=t_out),
            b=dict(title=b.get('title'), yt=b.get('source_yt'), t=t_in),
            window=window,
        ))
    return out

def extract_one(rec, mix_audio, dest_dir=None):
    dest_dir = dest_dir or os.path.join(paths.CLIPS, rec['split'], rec['id'])
    os.makedirs(dest_dir, exist_ok=True)
    t_in = rec['window']['mix_t_b']
    t0 = max(0.0, t_in - PRE)
    dur = PRE + POST
    pro = os.path.join(dest_dir, 'pro.wav')
    if not os.path.exists(pro) or os.path.getsize(pro) < 1000:
        _cut(mix_audio, pro, t0, dur)
    rec = dict(rec)
    rec['pro_clip'] = pro
    rec['pro_clip_start'] = t0
    rec['pro_clip_dur'] = dur
    rec['dir'] = dest_dir
    json.dump(rec, open(os.path.join(dest_dir, 'meta.json'),'w'), indent=2)
    return rec

def load_corpus():
    return json.load(open(paths.CORPUS))

if __name__ == '__main__':
    C = load_corpus()
    n=0
    for m in C['mixes']:
        audio = m.get('local_mix')
        if audio and not os.path.isabs(audio):
            audio = os.path.join(paths.MIXES, audio)
        if not audio or not os.path.exists(audio):
            print('skip (no mix audio)', m['id']); continue
        for rec in transitions_from_mix(m):
            extract_one(rec, audio); n += 1
            print('extracted', rec['id'], rec['a']['title'], '->', rec['b']['title'])
    print('done', n)
