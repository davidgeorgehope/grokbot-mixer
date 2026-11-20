"""Blind A/B for the listener (2026-11-20): hybrid_minds_ukf__09 current default pick (nat_short ['n',208,None,48,16], render verdict
pulse clash 0.6) vs the DRUMCLASH v3 clash-free re-ranked pick (dclash3_1120: clash_alt ['n',176,None,64,32]). Current rules,
-14 LUFS, one diagnostics PNG each. A/B order is random; the key goes to /workspace/private only (never under /workspace/mixes)."""
import json, os, sys, subprocess, random, time
sys.path[:0] = ['/workspace/mixes/protrans', '/workspace/mixes/src2', '/workspace/mixes/protrans/rca_beats']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True)
import paths, recreate, score as S, cleanup
import run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__09']; a, b = rec['a']['yt'], rec['b']['yt']
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1
created = []
for x in (a, b): recreate._prep_track(x, os.path.join(paths.LIB, x + '.m4a'), created)
env = recreate.apply_rules(rules); os.environ.update(env); os.chdir(paths.SRC2)
import blend_bench as BB, blend_diag as BD, drumclash as DC
OUT = '/workspace/mixes/deliver/protrans'; DGD = OUT + '/diagnostics'
arms = [('default', ['n', 208, None, 48, 16]), ('clashfree', ['n', 176, None, 64, 32])]
labels = ['A', 'B']; random.SystemRandom().shuffle(labels); key = {}; public = {}
for (name, win), lab in zip(arms, labels):
    c = dict(fam='ab_' + name, win=win, env=dict(env)); dk, M = BB.render(c, a, b, f'abhm09{lab}')
    s0, yA, yB = BD.crop_decks(M, 0); t = M['trans'][0]
    v = DC.rendered_combined(yA, yB, s0, float(t['start_bar']), float(t['end_bar']))
    sc = S.score(rec['pro_clip'], c['mp3'], src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), use_demucs=False, cache=paths.CACHE)
    png = f'{DGD}/ab_2026-11-20_hm09_{lab}.png'
    BD.figure(M, 0, png, f"hm09 blind {lab} | blend bars {t['start_bar']}-{t['end_bar']}", pro=rec['pro_clip'],
              src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), ours=c['mp3'])
    dst = f'{OUT}/ab_2026-11-20_hm09_{lab}.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', c['master'] if c.get('master') else c['mp3'], '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', '44100', '-b:a', '256k', dst], check=True)
    st = subprocess.run(['ffmpeg', '-hide_banner', '-i', dst, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    lufs = [l for l in st.splitlines() if l.strip().startswith('I:')][-1].strip()
    key[lab] = dict(arm=name, win=win, pro_match=sc['score'], verdict=dict(level=v['level'], kind=v.get('kind'), confidence=v['confidence'],
                    lattice=v['lattice'].get('confidence'), pulse=v['pulse'].get('confidence')))
    public[lab] = dict(clip=dst, png=png, lufs=lufs, dur_s=round(float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', dst], capture_output=True, text=True).stdout), 1))
    print(lab, json.dumps(public[lab]), flush=True)
os.makedirs('/workspace/private', exist_ok=True)
json.dump(dict(pair='hybrid_minds_ukf__09', made=time.strftime('%Y-%m-%d %H:%M %Z'), key=key), open('/workspace/private/ab_2026-11-20_hm09_key.json', 'w'), indent=1, default=str)
json.dump(public, open('/workspace/mixes/protrans/rca_beats/ab_hm09_public.json', 'w'), indent=1)
print('KEY written to /workspace/private/ab_2026-11-20_hm09_key.json')
cleanup.drop_our_src2(created)
