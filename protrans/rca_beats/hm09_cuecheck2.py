"""Light check (the listener 3:18 PM follow-up): does a cue nearer the pro's (B in at ~52, A out around 136-152) close the gap?
Renders a handful of natural windows with current rules + DRUMCLASH=1; reports pro-match + rendered verdict. No sweep."""
import json, os, sys
sys.path[:0] = ['/workspace/mixes/protrans', '/workspace/mixes/src2', '/workspace/mixes/protrans/rca_beats']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True)
import paths, recreate, score as S, cleanup
import run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__09']; a, b = rec['a']['yt'], rec['b']['yt']
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1; created = []
for x in (a, b): recreate._prep_track(x, os.path.join(paths.LIB, x + '.m4a'), created)
env = recreate.apply_rules(rules); os.environ.update(env); os.chdir(paths.SRC2)
import blend_bench as BB
WINS = [['n', 160, None, 48, 32], ['n', 144, None, 48, 32], ['n', 160, None, 64, 16], ['n', 160, None, 48, 16]]  # allowed grid (mix_simple DUMP_CANDS): exits /16, cues /16, X 16|32
out = []
for i, w in enumerate(WINS):
    try:
        c = dict(fam='cue', win=w, env=dict(env)); dk, M = BB.render(c, a, b, f'cuechk2_{i}')
        h = M['trans'][0].get('drumclash') or {}; fin = h.get('after') or h.get('before') or {}
        sc = S.score(rec['pro_clip'], c['mp3'], src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), use_demucs=False, cache=paths.CACHE)
        r = dict(win=w, pro_match=sc['score'], level=h.get('level'), kind=h.get('kind'), lattice=(fin.get('lattice') or {}).get('confidence'), pulse=(fin.get('pulse') or {}).get('confidence'))
    except Exception as e:
        r = dict(win=w, error=f'{type(e).__name__}: {str(e)[-200:]}')
    out.append(r); print('WIN', json.dumps(r, default=str), flush=True)
json.dump(out, open('/workspace/mixes/protrans/rca_beats/hm09_cuecheck2.json', 'w'), indent=1, default=str)
# clip for listener: 144/48/16 with 24 pre-roll bars (48 bars, ~66 s), linear gain to -14 LUFS integrated on the final mp3
import subprocess, blend_diag as BD
BB.PRE = 24; w = ['n', 144, None, 48, 16]; c = dict(fam='cue48', win=w, env=dict(env)); dk, M = BB.render(c, a, b, 'hm09cue48clip')
src = c['master'] if c.get('master') else c['mp3']; dst = '/workspace/mixes/deliver/protrans/rca_2026-11-20_hm09_exit144_cue48.mp3'
def integ(p):
    st = subprocess.run(['ffmpeg', '-hide_banner', '-i', p, '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(st[st.rindex('"input_i"'):].split('"')[3])
g = -14.0 - integ(src)
for _ in range(5):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-af', f'volume={g:.2f}dB', '-ar', '44100', '-b:a', '256k', dst], check=True)
    m = integ(dst)
    if abs(m + 14.0) <= 0.03: break
    g += -14.0 - m
png = '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-20_hm09_exit144_cue48.png'
BD.figure(M, 0, png, 'hm09: A exits over its breakdown, B cue 48 (B drop lands at A bar 144)', pro=rec['pro_clip'],
          src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), ours=c['mp3'])
dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', dst], capture_output=True, text=True).stdout)
print('CLIP', json.dumps(dict(clip=dst, png=png, lufs=round(m, 2), gain_db=round(g, 2), dur_s=round(dur, 1))), flush=True)
cleanup.drop_our_src2(created)
