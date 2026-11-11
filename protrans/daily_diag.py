"""Standard diagnostic figure for a daily protrans A/B pick (2026-11-11 RCA figure, made routine). Generate-only.

Re-renders the pick with the given rules (default rules.json, i.e. what the daily round left in place), scores it, and
writes deliver/protrans/diagnostics/daily_<date>.png/.json via src2/blend_diag.figure (engine curves, rendered lows,
per-bar deck offset + half-beat verdict, drum fold, and the pro panel: fitted per-deck gains and the pro deck lock).
usage: python3 protrans/daily_diag.py <pick_id> [--date YYYY-MM-DD] [--rules rules.json] [--name NAME]"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, recreate, score, cleanup
import run_admitted_tune as T


def make(pick_id, name=None, rules=None, out_dir=None):
    recs = {r['id']: r for r in T.load_recs()}
    rec = recs[pick_id]; rules = rules or json.load(open(paths.RULES))
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb, hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                             rules=rules, tag=f'diag{os.getpid()}')   # unique: two runs sharing one tag clobbered each other's mp3 (2026-11-11: 46.36 vs 23.95)
    sc = score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    out_dir = out_dir or os.path.join(paths.DELIVER, 'diagnostics'); name = name or f'daily_{time.strftime("%Y-%m-%d")}'
    sys.path.insert(0, paths.SRC2); cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        import blend_diag
        M = json.load(open(info['meta_path']))
        summ = blend_diag.figure(M, 0, os.path.join(out_dir, name + '.png'),
                                 f"{pick_id} {rec['pair']} fam={info['fam']} score {sc['score']} (v2 {sc.get('score_v2')})",
                                 pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=info['ours'])
    finally:
        os.chdir(cwd)
    summ.update(pick_id=pick_id, fam=info['fam'], win=info['win'], score=sc['score'], score_v2=sc.get('score_v2'),
                breakdown=sc.get('breakdown'), ours=info['ours'])
    json.dump(summ, open(os.path.join(out_dir, name + '.json'), 'w'), indent=1, default=str)
    cleanup.drop_our_src2(info.get('created') or [])
    return summ


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('pick_id'); ap.add_argument('--date'); ap.add_argument('--rules'); ap.add_argument('--name')
    a = ap.parse_args()
    s = make(a.pick_id, a.name or (f'daily_{a.date}' if a.date else None), json.load(open(a.rules)) if a.rules else None)
    print('DIAG ' + json.dumps({k: s.get(k) for k in ('png', 'score', 'score_v2', 'fam', 'halfbeat', 'pro_lock')}, default=str))
