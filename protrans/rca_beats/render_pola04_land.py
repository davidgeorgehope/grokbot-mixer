"""pola04 landing-fade clip for the listener (2026-11-20, dclash7 PLAN_LAND): renders one landing window with current rules + DRUMCLASH=1 +
PLAN_LAND=1, ~48 bars (~66 s), linear gain to -14 LUFS integrated on the final mp3, diag PNG, and the pro-vs-ours placement table.
usage: render_pola04_land.py OUT_BAR IN_BAR X"""
import json, os, subprocess, sys
sys.path[:0] = ['/workspace/mixes/protrans', '/workspace/mixes/src2']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True); os.environ['PLAN_LAND'] = '1'
import paths, recreate, score as S, cleanup, provsours
import run_admitted_tune as T
PID = 'pola_bryson_puzzlewood__04'
e, ib, X = map(int, sys.argv[1:4]); w = ['n', e, None, ib, X]
rec = {r['id']: r for r in T.load_recs()}[PID]; a, b = rec['a']['yt'], rec['b']['yt']
sa, sb = (os.path.join(paths.LIB, x + '.m4a') for x in (a, b))
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1; created = []
for x, p in ((a, sa), (b, sb)): recreate._prep_track(x, p, created)
env = recreate.apply_rules(rules); env['PLAN_LAND'] = '1'; os.environ.update(env); os.chdir(paths.SRC2)
import blend_bench as BB, blend_diag as BD
stem = f'rca_2026-11-20_pola04_land_{e}_{ib}_{X}'
c = dict(fam='land', win=w, env=dict(env)); dk, M = BB.render(c, a, b, 'pola04land')
h = M['trans'][0].get('drumclash') or {}; fin = h.get('after') or h.get('before') or {}
sc = S.score(rec['pro_clip'], c['mp3'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
BB.PRE = 48 - X - BB.POST; c2 = dict(fam='land', win=w, env=dict(env)); dk2, M2 = BB.render(c2, a, b, 'pola04landclip')
src = c2.get('master') or c2['mp3']; dst = f'/workspace/mixes/deliver/protrans/{stem}.mp3'
def integ(p):
    st = subprocess.run(['ffmpeg', '-hide_banner', '-i', p, '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(st[st.rindex('"input_i"'):].split('"')[3])
g = -14.0 - integ(src)
for _ in range(6):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-af', f'volume={g:.2f}dB', '-ar', '44100', '-b:a', '256k', dst], check=True)
    m = integ(dst)
    if abs(m + 14.0) <= 0.05: break
    g += -14.0 - m
dd = '/workspace/mixes/deliver/protrans/diagnostics'; png = f'{dd}/{stem}.png'
BD.figure(M2, 0, png, f'pola04 landing fade: A exits at its breakdown end (bar {e}), B cue {ib}, {X}-bar blend, B drop lands at A bar {e}',
          pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=c2['mp3'])
pv = provsours.make(PID, stem, {'ours_land': w}, dd)
dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', dst], capture_output=True, text=True).stdout)
out = dict(clip=dst, png=png, provsours=f'{dd}/{stem}_provsours.md', lufs=round(m, 2), dur_s=round(dur, 1), win=w, pro_match=sc['score'],
           level=h.get('level'), kind=h.get('kind'), lattice=(fin.get('lattice') or {}).get('confidence'), pulse=(fin.get('pulse') or {}).get('confidence'), rows=pv['rows'])
json.dump(out, open(f'/workspace/mixes/protrans/rca_beats/{stem}.json', 'w'), indent=1, default=str)
print('CLIP', json.dumps(out, default=str), flush=True)
cleanup.drop_our_src2(created)
