"""Pro decision extraction from corpus_v2 features (REPLICA v0, 2026-11-18). JSON only, read-only on the corpus."""
import json, glob, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(os.path.dirname(HERE), 'corpus_v2', 'features')

def decisions(f):
    cue = f.get('cue') or {}; sa = (f.get('track_a') or {}).get('sections') or {}; sb = (f.get('track_b') or {}).get('sections') or {}
    rt = f.get('rise_tail') or {}
    ib, ob = cue.get('incoming_bar'), cue.get('outgoing_bar')
    if ib is None or ob is None or not sa.get('music_end') or sb.get('drop1') is None: return None
    d = dict(id=f['id'], mix=f['mix_id'], dj=f['dj'],
             in_bar=ib, out_bar=ob, in_sec=cue.get('incoming_section'), out_sec=cue.get('outgoing_section'),
             in_rel_drop1=ib - sb['drop1'],               # <0: incoming enters before its first drop
             out_left=sa['music_end'] - ob,                # bars of outgoing music left at the cue
             overlap=f.get('overlap_bars'),
             tail_all=(rt.get('all') or {}).get('tail_bars'), rise_bass=(rt.get('bass') or {}).get('rise_db_per_beat'),
             rise_all=(rt.get('all') or {}).get('rise_db_per_beat'))
    # coarse technique class
    d['out_style'] = 'outro' if d['out_left'] <= 40 else 'mid'
    d['in_style'] = 'intro' if d['in_rel_drop1'] < -4 else ('on_drop' if abs(d['in_rel_drop1']) <= 4 else 'post_drop')
    return d

def track_feats(f):
    sa = (f.get('track_a') or {}).get('sections') or {}; sb = (f.get('track_b') or {}).get('sections') or {}
    def g(s, k, dflt=0): v = s.get(k); return dflt if v is None else v
    bb = sb.get('bass_by_section') or {}; ba = sa.get('bass_by_section') or {}
    intro_b = (bb.get('intro') or {}).get('bass'); drop_b = (bb.get('drop') or bb.get('drop1') or {}).get('bass')
    outro_a = (ba.get('outro') or {}).get('bass'); drop_a = (ba.get('drop') or ba.get('drop1') or {}).get('bass')
    return dict(a_n=g(sa,'n_bars'), a_outro=g(sa,'music_end') - (sa.get('outro_start') or g(sa,'music_end')), a_ndrops=g(sa,'n_drops'),
                a_drop2=g(sa,'drop2', g(sa,'n_bars')), b_n=g(sb,'n_bars'), b_intro=g(sb,'intro_len'), b_ndrops=g(sb,'n_drops'),
                b_drop2=g(sb,'drop2', g(sb,'n_bars')),
                b_intro_bass_gap=(drop_b - intro_b) if (drop_b is not None and intro_b is not None) else 0.0,
                a_outro_bass_gap=(drop_a - outro_a) if (drop_a is not None and outro_a is not None) else 0.0)

def load():
    rows = []
    for p in sorted(glob.glob(os.path.join(FEAT, '*.json'))):
        f = json.load(open(p))
        if f.get('error'): continue
        d = decisions(f)
        if d: d['x'] = track_feats(f); d['sec_a'] = f['track_a']['sections']; d['sec_b'] = f['track_b']['sections']; rows.append(d)
    return rows

if __name__ == '__main__':
    R = load(); print('usable', len(R), 'mixes', len({r['mix'] for r in R}))
    for k in ('in_rel_drop1', 'out_left', 'overlap', 'tail_all', 'rise_bass'):
        v = [r[k] for r in R if r[k] is not None]
        q = st.quantiles(v, n=4)
        print(f'{k:14s} n={len(v)} p25={q[0]:.1f} median={q[1]:.1f} p75={q[2]:.1f}')
    from collections import Counter
    print('out_style', Counter(r['out_style'] for r in R)); print('in_style', Counter(r['in_style'] for r in R))
    print('combo', Counter((r['out_style'], r['in_style']) for r in R))
    print('in_sec', Counter(r['in_sec'] for r in R)); print('out_sec', Counter(r['out_sec'] for r in R))
