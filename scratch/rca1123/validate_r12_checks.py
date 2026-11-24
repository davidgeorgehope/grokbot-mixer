#!/usr/bin/env python3
"""Replay the labelled Mix 07 r12 Daydreaming→Parallel trainwreck through checks.alignment_failures."""
import json, os, sys, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

SRC2 = '/workspace/mixes/src2'
MP3 = '/workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.mp3'
TIMING = '/workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.timing.json'
WAV = '/workspace/mixes/scratch/rca1123/r12_parallel.wav'
R17_MP3 = '/workspace/mixes/deliver/ab/mix07r17_grid_Parallel_24m49.mp3'
R17_TIMING = '/workspace/mixes/deliver/ab/mix07r17_grid_Parallel_24m49.timing.json'
R17_WAV = '/workspace/mixes/scratch/rca1123/r17_parallel.wav'
OUT = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride')

sys.path.insert(0, '/workspace/mixes/src/tests')
os.environ['MIX_SRC'] = SRC2
os.environ['NUDGE'] = 'nudge07.json'


def decode(mp3, wav):
    if not Path(wav).exists() or Path(wav).stat().st_size < 1000:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp3, '-ac', '2', '-ar', '44100', wav], check=True)
    return wav


def shift_deck(d, s0):
    d = json.loads(json.dumps(d))
    d['start_bar'] = int(d['start_bar']) - s0
    d['end_bar'] = int(d['end_bar']) - s0
    auto = d.get('auto') or {}
    for k, pts in list(auto.items()):
        if isinstance(pts, list) and pts and isinstance(pts[0], (list, tuple)):
            auto[k] = [[float(p[0]) - s0, p[1]] for p in pts]
    d['auto'] = auto
    return d


def run_clip(tag, mp3, timing, wav, expect_fail):
    import checks as C
    # reset caches / env
    C.SRC = SRC2
    C.WAV = decode(mp3, wav)
    C.NAME = 'r12tmp'
    for fn in ('audio', 'onset', 'bar_rms', 'ref_phase', 'src_onset', '_nudges', 'src_bars'):
        f = getattr(C, fn, None)
        if hasattr(f, 'cache_clear'):
            f.cache_clear()
    T = json.load(open(timing))
    s0 = int(T['clip_start_bar'])
    trans = T['trans'] if isinstance(T['trans'], dict) else T['trans'][0]
    A = shift_deck(T['decks'][0], s0)
    B = shift_deck(T['decks'][1], s0)
    # clip may end before deck end_bar
    clip_end = int(T['clip_end_bar']) - s0
    A['end_bar'] = min(int(A['end_bar']), clip_end)
    B['end_bar'] = min(int(B['end_bar']), clip_end)
    rows = C.bar_alignment_report(deck_pair=(A, B))
    fails = C.alignment_failures(rows)
    tail_mix = [r for r in fails if r.get('kind') == 'mix' and r.get('tail')]
    all_mix = [r for r in fails if r.get('kind') == 'mix']
    def brief(r):
        return dict(bar=r['bar'] + s0, deck=r['deck'], lag_0=r.get('lag_0'), corr_0=r.get('corr_0'),
                    tail=r.get('tail'), kind=r.get('kind'))
    print(f'\n==== {tag}')
    print('  rows', len(rows), 'failures', len(fails), 'tail mix fails', len(tail_mix), 'all mix fails', len(all_mix))
    for r in (tail_mix or all_mix)[:8]:
        print('  FAIL', brief(r))
    ok = bool(tail_mix or all_mix) if expect_fail else not bool(all_mix)
    # r17 should not have tail mix fails (heard OK). Body fails would be unexpected.
    return dict(tag=tag, expect_fail=expect_fail, n_rows=len(rows), n_fail=len(fails),
                n_tail_mix=len(tail_mix), n_mix=len(all_mix),
                fails=[brief(r) for r in fails if r.get('kind')=='mix'][:20],
                verdict_ok=ok)


def main():
    r12 = run_clip('mix07r12 Daydreaming→Parallel heard trainwreck', MP3, TIMING, WAV, True)
    r17 = run_clip('mix07r17 Daydreaming→Parallel heard OK', R17_MP3, R17_TIMING, R17_WAV, False)
    out = dict(r12=r12, r17=r17,
               note='Labelled regression is checks.alignment_failures (tail mix-vs-source |lag_0|>10 ms), not the 40 ms overlap-median.')
    json.dump(out, open(OUT / 'r12_checks_validation.json', 'w'), indent=2)
    print('\nR12_CHECKS_STILL_FAILS', r12['verdict_ok'], 'R17_CLEAN', r17['verdict_ok'])
    print('WROTE', OUT / 'r12_checks_validation.json')

if __name__ == '__main__':
    main()
