#!/usr/bin/env python3
"""Build per-transition timing.json segments for a full-mix turntable render.

usage: python3 build_segs.py META.json MIX.mp3 WORKDIR [--tracklist TL.md]

Cuts the mix at midpoints between transitions (same scheme as src2/full_viz.py),
writes WORKDIR/segNN.timing.json + WORKDIR/segs.json. Titles come from the
tracklist (youtu.be/<id> lines) when given, else deck id stubs.
"""
from __future__ import annotations
import argparse, copy, json, math, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck_state import assign_slots, segment_layout, fx_windows, walk_segments  # noqa: E402


def titles_from_tracklist(path):
    out = {}
    if not path or not os.path.exists(path):
        return out
    # "10. 23:10  Artist – Title  [5A]  (youtu.be/ID)" or with ft.
    pat = re.compile(
        r'^\s*\d+\.\s+\d+:\d+\s+(.+?)\s+[–-]\s+(.+?)\s+\[.*?\]\s+\(youtu\.be/([A-Za-z0-9_-]+)\)\s*$'
    )
    for line in open(path):
        m = pat.match(line.rstrip())
        if not m:
            continue
        artist, title, tid = m.group(1).strip(), m.group(2).strip(), m.group(3)
        feat = ''
        fm = re.match(r'(.*?)\s+(ft\..+)$', artist, re.I)
        if fm:
            artist, feat = fm.group(1), fm.group(2)
        # also "Title (ft. X)" form
        tm = re.match(r'^(.*?)\s+\((ft\..+)\)$', title, re.I)
        if tm:
            title, feat = tm.group(1), feat or tm.group(2)
        rec = dict(artist=artist, title=title)
        if feat:
            rec['feat'] = feat
        out[tid] = rec
    return out


def stub_title(tid):
    return dict(artist='DECK', title=tid[:11])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('meta')
    ap.add_argument('mix')
    ap.add_argument('workdir')
    ap.add_argument('--tracklist', default='')
    ap.add_argument('--fps', type=int, default=30)
    a = ap.parse_args()
    M = json.load(open(a.meta))
    BAR = float(M['bar_sec'])
    T, D = M['trans'], M['decks']
    titles = titles_from_tracklist(a.tracklist)
    os.makedirs(a.workdir, exist_ok=True)
    fa = lambda b: round(b * BAR * a.fps) / a.fps
    cut = [0.0] + [fa((T[i - 1]['end_bar'] + T[i]['start_bar']) / 2) for i in range(1, len(T))]
    cut.append(math.floor(float(M['len_sec']) * a.fps) / a.fps)
    segs = []
    slots = assign_slots(M)   # track k lives on deck k % 2 for its whole life (load on the idle deck)
    for i, t in enumerate(T):
        t0, t1 = cut[i], cut[i + 1]
        s0, s1 = t0 / BAR, t1 / BAR
        tag = f'seg{i:02d}'
        a_id, b_id = t['a'], t['b']
        lay = segment_layout(M, i, slots)
        t_out, t_in = titles.get(a_id) or stub_title(a_id), titles.get(b_id) or stub_title(b_id)
        tim = dict(
            sr=44100, bs=BAR * 44100, bar_sec=BAR,
            clip_start_bar=s0, clip_end_bar=s1,
            nudge='/nonexistent', trans_index=i, trans=t, decks=[],
            # decks[] is in PHYSICAL order: decks[0] is deck A (left), decks[1] deck B (right).
            # out_deck says which one holds the outgoing track of this transition.
            out_deck=lay['out_deck'],
            titles=dict(out=t_out, deck=[t_out, t_in] if lay['out_deck'] == 0 else [t_in, t_out]),
            fx=fx_windows(M, i, s0, s1, slots),
            source=f'{os.path.basename(a.meta)} trans {i} {a_id}->{b_id}',
        )
        tim['titles']['in'] = t_in
        for di in lay['phys']:
            d = D[di]
            j0 = max(0, int(math.floor(s0)) - d['start_bar'])
            j1 = min(len(d['full_map']), int(math.ceil(s1)) + 1 - d['start_bar'])
            dd = copy.deepcopy(d)
            dd['full_map'] = d['full_map'][j0:j1]
            dd['start_bar'] = d['start_bar'] + j0
            dd['exit_bar'] = d['start_bar'] + len(d['full_map'])
            dd.pop('echo_out', None)
            tim['decks'].append(dd)
        path = os.path.join(a.workdir, f'{tag}.timing.json')
        json.dump(tim, open(path, 'w'), default=float)
        segs.append(dict(tag=tag, t0=t0, t1=t1, dur=t1 - t0, timing=path))
        print(f'{tag}: bars {s0:.1f}-{s1:.1f} ({t1 - t0:.1f}s) {a_id} (deck {"AB"[lay["out_deck"]]}) -> {b_id} (deck {"AB"[1 - lay["out_deck"]]})')
    # gate: walk the whole plan; a record that changes decks (Mix 08 v2) or two consecutive tracks on one deck fails
    errs = walk_segments([json.load(open(s['timing'])) for s in segs])
    if errs:
        raise SystemExit('build_segs: deck rule broken:\n  ' + '\n  '.join(errs[:10]))
    print(f'deck check ok: {len(segs) + 1} records, decks alternate A/B, no record changes deck')
    json.dump(dict(meta=a.meta, mix=a.mix, bar_sec=BAR, fps=a.fps, cut=cut, segs=segs),
              open(os.path.join(a.workdir, 'segs.json'), 'w'), indent=1)
    print(f'{len(segs)} segments, total {cut[-1]:.1f}s -> {a.workdir}')


if __name__ == '__main__':
    main()
