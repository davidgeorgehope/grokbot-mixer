"""Extract the pro's decisions from each protrans pro clip (33 pairs) in track bars. Read-only on corpus/rules.
Per pair: where each source sits in the clip (locate), per-deck per-band NNLS gains (diagnose_gap.band_gains),
then: incoming entry, outgoing gone, bass swap, overlap length; mapped to track bars and track sections."""
import json, os, sys, time, traceback, numpy as np
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, P)
import paths, score, diagnose_gap as D, corpus_v2_pipeline as CP
import run_admitted_tune as T
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'protrans_decisions.json')

def bars_curve(g, hop_s, bar):
    n = int(len(g) * hop_s / bar)
    return np.array([np.mean(g[int(k*bar/hop_s):int((k+1)*bar/hop_s)] ** 2) for k in range(n)])

def run_one(rec):
    pro = score._load(rec['pro_clip'])
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    locs, al = [], []
    for s in (sa, sb):
        y = score._load(s); loc = D.version_match.locate_in(pro, y)
        if loc.get('track_t') is None: return dict(id=rec['id'], error='locate failed')
        z = D.place_source(s, loc['track_t'], loc['mix_t'], len(pro)); z, lag = D.refine_lag(pro, z)
        locs.append(loc); al.append(z)
    hop_s = 0.25
    gains, _, times, _ = D.band_gains(pro, *al, hop_s=hop_s)
    bar = score.BAR_SEC
    ev = {}
    for band in ('all', 'bass'):
        ga, gb = bars_curve(gains[band]['a'], hop_s, bar), bars_curve(gains[band]['b'], hop_s, bar)
        n = min(len(ga), len(gb)); ga, gb = ga[:n], gb[:n]
        da = 10*np.log10(ga/ (np.percentile(ga, 90)+1e-12) + 1e-12); db = 10*np.log10(gb/(np.percentile(gb, 90)+1e-12) + 1e-12)
        on_a, on_b = da > -12, db > -12
        sus = lambda m: next((k for k in range(len(m)-1) if m[k] and m[k+1]), None)
        b_in = sus(on_b); act = np.flatnonzero(on_a); a_gone = int(act[-1]) + 1 if len(act) else None
        swap = None
        if b_in is not None:
            swap = next((k for k in range(b_in, n-1) if db[k] >= da[k] and db[k+1] >= da[k+1]), None)
        ev[band] = dict(b_in=b_in, a_gone=a_gone, swap=swap, n=n, da=da.round(1).tolist(), db=db.round(1).tolist())
    # clip bar k -> track bars: track_t + (k*bar - mix_t)
    def tb(loc, k): return None if k is None else round((loc['track_t'] + k*bar - loc['mix_t']) / bar, 1)
    e = ev['all']; eb = ev['bass']
    secs = {}
    for side, s in (('a', sa), ('b', sb)):
        try: secs[side] = CP.sections_from_bar(CP.bar_from_audio(s))
        except Exception as ex: secs[side] = dict(error=str(ex)[-200:])
    dec = dict(id=rec['id'], dj=rec['dj'], pair=rec['pair'], split=rec['split'],
               in_entry_clip_bar=e['b_in'], out_gone_clip_bar=e['a_gone'], bass_swap_clip_bar=eb['swap'],
               in_bar_at_entry=tb(locs[1], e['b_in']), out_bar_at_entry=tb(locs[0], e['b_in']),
               out_bar_at_gone=tb(locs[0], e['a_gone']), in_bar_at_gone=tb(locs[1], e['a_gone']),
               in_bar_at_swap=tb(locs[1], eb['swap']), out_bar_at_swap=tb(locs[0], eb['swap']),
               overlap_bars=None if (e['b_in'] is None or e['a_gone'] is None) else e['a_gone'] - e['b_in'],
               swap_after_entry=None if (e['b_in'] is None or eb['swap'] is None) else eb['swap'] - e['b_in'],
               curves=dict(all_a=e['da'], all_b=e['db'], bass_a=eb['da'], bass_b=eb['db']),
               sec_a=secs['a'], sec_b=secs['b'], loc=dict(a=locs[0], b=locs[1]))
    sA, sB = secs['a'], secs['b']
    if sA.get('music_end') and dec['out_bar_at_entry'] is not None: dec['out_left_at_entry'] = round(sA['music_end'] - dec['out_bar_at_entry'], 1)
    if sB.get('drop1') is not None and dec['in_bar_at_entry'] is not None: dec['in_rel_drop1'] = round(dec['in_bar_at_entry'] - sB['drop1'], 1)
    if sB.get('drop1') is not None and dec['in_bar_at_swap'] is not None: dec['swap_rel_in_drop1'] = round(dec['in_bar_at_swap'] - sB['drop1'], 1)
    return dec

if __name__ == '__main__':
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for rec in T.load_recs():
        if rec['id'] in done: continue
        t = time.time()
        try: d = run_one(rec)
        except Exception: d = dict(id=rec['id'], error=traceback.format_exc()[-400:])
        done[rec['id']] = d; json.dump(done, open(OUT, 'w'), default=str)
        print(rec['id'], {k: d.get(k) for k in ('in_bar_at_entry', 'out_left_at_entry', 'in_rel_drop1', 'overlap_bars', 'swap_after_entry', 'error')}, f'{time.time()-t:.0f}s', flush=True)
