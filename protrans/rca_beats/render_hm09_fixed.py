"""RCA 2026-11-20 clip for listener: hybrid_minds_ukf__09 with A leaving over its own breakdown (A bars 128-143, no A drop drums)
while B's intro build (48-63) plays, so B's drop lands as A's breakdown ends (window ['n',144,None,48,16]; engine window, current
rules + DRUMCLASH=1). Writes deliver/protrans/rca_2026-11-20_hm09_fixed.mp3 (-14 LUFS) + diagnostics PNG/JSON, and the same
measurements for the default pick for comparison."""
import json, os, sys, subprocess
sys.path[:0] = ['/workspace/mixes/protrans', '/workspace/mixes/src2', '/workspace/mixes/protrans/rca_beats']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
import paths, recreate, score as S, cleanup
import run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__09']; a, b = rec['a']['yt'], rec['b']['yt']
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1
created = []
for x in (a, b): recreate._prep_track(x, os.path.join(paths.LIB, x + '.m4a'), created)
env = recreate.apply_rules(rules); old = {k: os.environ.get(k) for k in env}; os.environ.update(env); os.chdir(paths.SRC2)
import blend_bench as BB, blend_diag as BD, drumclash as DC
OUT = '/workspace/mixes/deliver/protrans'; DG = OUT + '/diagnostics'; res = {}
for name, win in (('default', ['n', 208, None, 48, 16]), ('fixed', ['n', 144, None, 48, 16])):
    c = dict(fam='rca_' + name, win=win, env=dict(env)); dk, M = BB.render(c, a, b, f'rcahm09{name}')
    s0, yA, yB = BD.crop_decks(M, 0); t = M['trans'][0]
    v = DC.rendered_eval(yA, yB, s0, float(t['start_bar']), float(t['end_bar'])); v.pop('rows')
    sc = S.score(rec['pro_clip'], c['mp3'], src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), use_demucs=False, cache=paths.CACHE)
    png = f'{DG}/rca_2026-11-20_hm09_{name}.png'
    summ = BD.figure(M, 0, png, f"hybrid_minds_ukf__09 RCA {name} win={win} score {sc['score']} | drumclash {v['score']} flagged={v['flagged']}",
                     pro=rec['pro_clip'], src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), ours=c['mp3'])
    import progrid; pg = progrid.grid_phase(S._load(c['mp3']), a, b)
    res[name] = dict(win=win, score=sc['score'], drumclash=v, lock=t.get('blend_lock'), progrid=pg, mp3=c['mp3'], png=png,
                     blend_bars=[t['start_bar'], t['end_bar']], bass_swap=t.get('bass_swap'), xcorr_med=summ.get('offset_ms_median'))
    if name == 'fixed':
        dst = f'{OUT}/rca_2026-11-20_hm09_fixed.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', c['master'] if c.get('master') else c['mp3'], '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', '44100', '-b:a', '256k', dst], check=True)
        res[name]['clip'] = dst
    print(name, json.dumps({k: v2 for k, v2 in res[name].items() if k != 'lock'}, default=str), flush=True)
json.dump(res, open('/workspace/mixes/protrans/rca_beats/hm09_fixed.json', 'w'), indent=1, default=str)
cleanup.drop_our_src2(created)
