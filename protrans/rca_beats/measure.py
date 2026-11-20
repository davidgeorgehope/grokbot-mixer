"""RCA 2026-11-20 (beats off): consistent phase measurement for a protrans pair.
Per deck (rendered alone on the mix grid): beat-period circular phase of kick+snare onset flux, per bar (ms vs mix grid).
A-B of those = pattern-independent deck offset. Also the blend_diag xcorr offsets and the BLEND_LOCK report."""
import json, os, sys, copy
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.dirname(HERE)
sys.path.insert(0, PT)
import paths, recreate, cleanup
import run_admitted_tune as T
sys.path.insert(0, paths.SRC2)

def deck_phase(y, bars, bs, beat, sr=44100, hop=64):
    import blend_diag as D
    m = y.mean(1); e = D._flux(m, 30, 150) + D._flux(m, 150, 1500); fr = sr / hop
    t = np.arange(len(e)) / fr; out = []
    for k in bars:
        i0, i1 = int(k * bs / hop), int((k + 1) * bs / hop); w = e[i0:i1]
        if len(w) < 10 or w.sum() <= 0: out.append((np.nan, 0)); continue
        z = np.sum(w * np.exp(-2j * np.pi * t[i0:i1] / (beat))); r = abs(z) / w.sum()
        ph = -np.angle(z) / (2 * np.pi) * beat * 1000  # ms the hits sit after the grid beat
        out.append((float(ph), float(r)))
    return out

def wrap(x, beat_ms):
    return (x + beat_ms / 2) % beat_ms - beat_ms / 2

def analyse(M, i=0):
    import blend_diag as D, engine as E
    s0, A, B = D.crop_decks(M, i); t = M['trans'][i]; s, e = float(t['start_bar']), float(t['end_bar'])
    nb = int(round(len(A) / E.BS)); beat_ms = E.BEAT * 1000
    allA, allB = D.band_bar_db(A, nb, E.BS), D.band_bar_db(B, nb, E.BS)
    ref = max(np.median(allA[:D.PRE]), np.median(allB[-D.POST:]))
    bl = [k for k in range(int(s - s0), int(e - s0)) if allA[k] > ref - 20 and allB[k] > ref - 20]
    xc = D.bar_offsets(A, B, bl, E.BS, E.BEAT)
    allbars = list(range(nb))
    pa, pb = deck_phase(A, allbars, E.BS, E.BEAT), deck_phase(B, allbars, E.BS, E.BEAT)
    rows = []
    for k in allbars:
        rows.append(dict(bar=k + s0, dbA=round(float(allA[k]), 1), dbB=round(float(allB[k]), 1),
                         phA=round(pa[k][0], 1), rA=round(pa[k][1], 2), phB=round(pb[k][0], 1), rB=round(pb[k][1], 2),
                         dAB=round(float(wrap(pa[k][0] - pb[k][0], beat_ms)), 1) if np.isfinite(pa[k][0] + pb[k][0]) else None,
                         xcorr=(round(float(xc[bl.index(k)]), 1) if k in bl and np.isfinite(xc[bl.index(k)]) else None)))
    return dict(s0=s0, start=s, end=e, rows=rows, overlap=[k + s0 for k in bl],
                lock=t.get('blend_lock'), lock_ms=M['decks'][i + 1].get('blend_lock_ms'))

def run(pick_id, rules_over=None, tag='rcab'):
    recs = {r['id']: r for r in T.load_recs()}; rec = recs[pick_id]
    rules = json.load(open(paths.RULES)); rules.update(rules_over or {})
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb, hint_a_played_sec=rec['window'].get('hint_a_played_sec'), rules=rules, tag=f'{tag}{os.getpid()}')
    M = json.load(open(info['meta_path']))
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        out = analyse(M)
    finally:
        os.chdir(cwd)
    out.update(pick_id=pick_id, win=info['win'], fam=info['fam'], ours=info['ours'], meta=info['meta_path'], created=info.get('created'))
    return out

if __name__ == '__main__':
    pid = sys.argv[1]; over = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    o = run(pid, over)
    name = sys.argv[3] if len(sys.argv) > 3 else pid
    json.dump(o, open(os.path.join(HERE, f'{name}.json'), 'w'), indent=1, default=str)
    print('LOCK', o['lock_ms'], json.dumps(o['lock'], default=str))
    print('overlap', o['overlap'])
    for r in o['rows']:
        mark = '*' if r['bar'] in o['overlap'] else ' '
        print(mark, r)
    cleanup.drop_our_src2(o.get('created') or [])
