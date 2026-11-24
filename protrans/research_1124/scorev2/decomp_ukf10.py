import os, sys, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PT)
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score, run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__10']
sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
orig = score.align_ours_to_pro
def forced(lag_s):
    def f(y_p, y_o, sr=score.SR, max_shift_s=None):
        lag = int(round(lag_s * sr))
        yp, yo = (y_p[lag:], y_o) if lag >= 0 else (y_p, y_o[-lag:])
        n = min(len(yp), len(yo)); return yp[:n], yo[:n], lag, 0.0
    return f
B = score.BAR_SEC
pro_entry_s = 7 * B  # pro decisions in_entry_clip_bar (audio, -12 dB)
res = {}
for n, entry_bar in (('default', 9), ('replica_on', 12), ('replica_x16', 10), ('dropcand_exit', 10)):
    o = os.path.join(HERE, 'renders', f'ukf10_{n}.mp3')
    score.align_ours_to_pro = orig
    s1 = score.score(rec['pro_clip'], o, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    lag_anchor = pro_entry_s - entry_bar * B  # ours[0] at pro[lag]
    score.align_ours_to_pro = forced(lag_anchor)
    s2 = score.score(rec['pro_clip'], o, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    K = ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length')
    for tagn, s in (('free', s1), ('anchored', s2)):
        b = s['breakdown']
        print(f"{n:14} {tagn:8} lag={b['align']['lag_ms']/1000:6.2f}s win={b['align']['win_sec']:5.1f} score={s['score']:6.2f}", {k: b[k] for k in K}, 'stems', b['stems'], 'ev_p', b['events_pro'], 'ev_o', b['events_ours'], flush=True)
    res[n] = dict(free=s1, anchored=s2)
json.dump(res, open(os.path.join(HERE, 'decomp_ukf10.json'), 'w'), indent=1, default=str)
