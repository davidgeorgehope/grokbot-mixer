"""official_v2 (2026-11-24 RCA, ukf__10): v1 plus WHERE the blend sits in each track, measured from audio.

What was wrong with v1 (gain-events-v3-beatid): every term is a clip-relative shape comparison after a free
+-24 s kick-envelope shift. At 174 BPM the kick envelope repeats every bar, so the shift can slide whole
phrases, and the bass_swap / outgoing_cut / blend_length events are bar counts from the start of that
slid window. Nothing measured which part of each TRACK was playing. An outro-over-intro blend 111 bars away
from the pro's breakdown exit scored within 3 points of a near-exact copy (ukf__10: 36.67 vs 39.87).

v2 keeps v1's sound terms (stem_curves 0.28, deck_curves 0.22, beat_align 0.15) and REPLACES the three
clip-relative event terms with the same events measured in each track's own engine bars, same total weight:
  swap  0.13  (v1 bass_swap)     : A bar and B bar when B's bass takes over
  exit  0.12  (v1 outgoing_cut)  : A bar and B bar when A is gone
  entry 0.10  (v1 blend_length)  : A bar and B bar when B becomes audible
Each position: 75% closeness exp(-|bars|/8) + 25% same section (intro / drop N / breakdown / outro).
8 bars = half a 16-bar phrase, chosen before looking at any cohort numbers; nothing was fit.
Measurement is symmetric: the same code runs on the pro clip and on ours (no engine metadata is read),
so the only way to raise it is to actually play the same parts of the tracks the pro played.
Each source is located with the chunk RANSAC line (score._fit_chunks), not a single best chunk hit
(that put Optimist's outro at bar 81 and Secret Place's intro at bar 116 in ukf__10 renders).
"""
from __future__ import annotations
import hashlib, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, score

VERSION = 'official_v2-place8c'
W2 = dict(stem_curves=0.28, deck_curves=0.22, beat_align=0.15, place_swap=0.13, place_exit=0.12, place_entry=0.10)
POS_SCALE_BARS = 8.0
SECTION_SHARE = 0.25
PRESENT_DB = -12.0

def _cc():
    sys.path.insert(0, os.path.join(paths.MIXES, 'src', 'eval'))
    import control_curves as CC
    return CC

def _st(yt):
    st = os.path.join(paths.SRC2, 'st')
    return os.path.join(st, yt + '.wav'), json.load(open(os.path.join(st, yt + '.json'))), json.load(open(os.path.join(st, yt + '.sections.json')))

_FEAT = {}
def _src_feat(wav):
    if wav not in _FEAT:
        y = score._load(wav); _FEAT[wav] = (y, _cc().bandpow(y))
    return _FEAT[wav]

def _downs(grid):
    d = grid.get('downs')
    if isinstance(d, str): d = json.loads(d)
    return np.asarray(d, float)

def section_label(sec, bar):
    if bar is None: return None
    dr = sec.get('drops') or []
    if not dr or bar < dr[0][0]: return 'intro'
    for i, (x, y) in enumerate(dr):
        if x <= bar < y: return f'drop{i + 1}'
    return 'outro' if bar >= dr[-1][1] else 'breakdown'

def _locate_line(y, Fm, wav):
    """mix_t = a + s * st_t, from all chunk hits (RANSAC); None if the source isn't in the clip."""
    CC = _cc(); ys, Ft = _src_feat(wav)
    h, _ = CC.locate(Fm, Ft, chunk_s=6.0, hop_s=2.0)
    line = score._fit_chunks(h)
    if line: return dict(a=line['a'], s=line['s'], n=line['n'], how='ransac')
    if h is None or len(h) == 0: return None
    i = int(np.argmax(h[:, 3]))
    if h[i, 2] < 0.45: return None
    return dict(a=float(h[i, 1] - h[i, 0]), s=1.0, n=1, how='single')

def placement_events(clip_path, yt_a, yt_b, cache=None):
    """Blend events of a two-deck clip, as clip bars and as each track's own engine bars."""
    import diagnose_gap as D
    cache = cache or os.path.join(paths.CACHE, 'place_v2')
    key = hashlib.md5(f'{VERSION}|{os.path.abspath(clip_path)}|{os.path.getmtime(clip_path)}|{yt_a}|{yt_b}|{paths.SRC2}'.encode()).hexdigest()[:20]
    cp = os.path.join(cache, key + '.json')
    if os.path.exists(cp):
        return json.load(open(cp))
    y = score._load(clip_path); Fm = _cc().bandpow(y); B = score.BAR_SEC
    out = dict(clip=os.path.basename(clip_path), dur=round(len(y) / score.SR, 2))
    maps, placed = {}, []
    for side, yt in (('a', yt_a), ('b', yt_b)):
        wav, grid, sec = _st(yt)
        L = _locate_line(y, Fm, wav)
        if not L:
            out['error'] = f'{side} not located'; break
        rate = 1.0 / L['s']; t0 = -L['a'] / L['s']   # st time at clip t=0
        z = D.place_source(wav, t0, 0.0, len(y), rate=rate)
        z, lag = D.refine_lag(y, z)
        dn = _downs(grid)
        maps[side] = (t0, rate, lag / score.SR, dn, sec)
        out[f'loc_{side}'] = dict(n=L['n'], how=L['how'], s=round(L['s'], 4), bar_at_clip0=round(float(np.interp(t0, dn, np.arange(len(dn)))), 2))
        placed.append(z)
    if 'error' not in out:
        hop_s = 0.25
        gains, _, _, _ = D.band_gains(y, placed[0], placed[1], hop_s=hop_s)
        def per_bar(g):
            n = int(len(g) * hop_s / B)
            return np.array([np.mean(g[int(k * B / hop_s):int((k + 1) * B / hop_s)] ** 2) for k in range(n)])
        ev = {}
        for band in ('all', 'bass'):
            ga, gb = per_bar(gains[band]['a']), per_bar(gains[band]['b'])
            n = min(len(ga), len(gb)); ga, gb = ga[:n], gb[:n]
            # presence is relative to each deck's own normal fader level (as replica/extract_protrans.py), since
            # NNLS gains also carry each source's mastering level; the floor stops a deck that is barely in the
            # clip from setting a near-zero reference of its own
            top = max(np.percentile(ga, 90), np.percentile(gb, 90))
            ra = max(np.percentile(ga, 90), 0.01 * top) + 1e-12; rb = max(np.percentile(gb, 90), 0.01 * top) + 1e-12
            da = 10 * np.log10(ga / ra + 1e-12); db = 10 * np.log10(gb / rb + 1e-12)
            on_a, on_b = da > PRESENT_DB, db > PRESENT_DB
            b_in = next((k for k in range(n - 1) if on_b[k] and on_b[k + 1]), None)
            act = np.flatnonzero(on_a)
            a_gone = (int(act[-1]) + 1) if len(act) and int(act[-1]) + 1 < n else None   # None = still there at clip end
            if len(act) == 0: a_gone = 0
            swap = None if b_in is None else next((k for k in range(b_in, n - 1) if db[k] >= da[k] and db[k + 1] >= da[k + 1]), None)
            ev[band] = dict(b_in=b_in, a_gone=a_gone, swap=swap, n=n)
        def tbar(side, k):
            if k is None: return None
            t0, rate, lag_s, dn, _ = maps[side]
            t_st = t0 + rate * (k * B - lag_s)
            return round(float(np.interp(t_st, dn, np.arange(len(dn)), left=-1, right=len(dn))), 1)
        e, eb = ev['all'], ev['bass']
        out['clip_bars'] = dict(entry=e['b_in'], gone=e['a_gone'], swap=eb['swap'], n=e['n'])
        for name, k in (('entry', e['b_in']), ('gone', e['a_gone']), ('swap', eb['swap'])):
            out[name] = dict(a=tbar('a', k), b=tbar('b', k))
            out[name]['sec_a'] = section_label(maps['a'][4], out[name]['a'])
            out[name]['sec_b'] = section_label(maps['b'][4], out[name]['b'])
    os.makedirs(cache, exist_ok=True); json.dump(out, open(cp, 'w'))
    return out

def _pos_sim(o, p, sec_o, sec_p):
    if o is None and p is None: return 100.0
    if o is None or p is None: return 20.0
    close = float(np.exp(-abs(o - p) / POS_SCALE_BARS))
    same = 1.0 if (sec_o is not None and sec_o == sec_p) else 0.0
    return 100.0 * ((1 - SECTION_SHARE) * close + SECTION_SHARE * same)

def _incomplete(ev_o, ev_p):
    """ours never finishes the handoff (B never comes in, or A is still up at the end of our clip) while the pro does.
    Without this a clip with both decks up the whole time collected entry/swap credit (2026-11-24 gaming test)."""
    if ev_o['entry']['a'] is None and ev_p['entry']['a'] is not None: return True
    return ev_o['gone']['a'] is None and ev_p['gone']['a'] is not None

def placement_score(ev_o, ev_p):
    if ev_p.get('error'): return None
    parts = {}
    for name in ('entry', 'gone', 'swap'):
        if ev_o.get('error'):
            parts[name] = 0.0; continue
        if _incomplete(ev_o, ev_p):
            parts[name] = 20.0; continue
        o, p = ev_o[name], ev_p[name]
        parts[name] = round(0.5 * _pos_sim(o['a'], p['a'], o['sec_a'], p['sec_a']) + 0.5 * _pos_sim(o['b'], p['b'], o['sec_b'], p['sec_b']), 2)
    return parts

def combine(v1_score, b, pl):
    """official_v2 from v1's breakdown and the placement parts (v1 score when the pro placement is unmeasurable)"""
    if pl is None: return float(v1_score)
    return float(W2['stem_curves'] * b['stem_curves'] + W2['deck_curves'] * b['deck_curves'] + W2['beat_align'] * b['beat_align']
                 + W2['place_swap'] * pl['swap'] + W2['place_exit'] * pl['gone'] + W2['place_entry'] * pl['entry'])

def yt_of(path):
    return os.path.splitext(os.path.basename(path))[0]

def score_v2(pro_path, ours_path, src_a, src_b, v1=None, use_demucs=False, cache=None):
    """Returns the v1 result dict plus official_v2 fields. v1 is recomputed unless passed in."""
    v1 = v1 or score.score(pro_path, ours_path, src_a=src_a, src_b=src_b, use_demucs=use_demucs, cache=cache or paths.CACHE)
    b = v1['breakdown']; ya, yb = yt_of(src_a), yt_of(src_b)
    ev_p = placement_events(pro_path, ya, yb); ev_o = placement_events(ours_path, ya, yb)
    pl = placement_score(ev_o, ev_p)
    total = combine(v1['score'], b, pl)
    why = 'pro placement not measurable: v1 score' if pl is None else None
    out = dict(v1)
    out.update(official_v2=round(float(total), 2), official_v2_version=VERSION, official_v2_weights=W2,
               placement=dict(parts=pl, pro=ev_p, ours=ev_o, why=why))
    return out

if __name__ == '__main__':
    r = score_v2(*sys.argv[1:5])
    print(json.dumps({k: r[k] for k in ('score', 'official_v2', 'placement')}, indent=1))
