"""Half-beat check over the whole library: every st/<id>.json (not mixpoints). Tracks whose stretched wav was cleaned
up are restored bit-exactly (restore_audio.py) for the check and their restored audio is deleted again afterwards
unless --apply re-grids them (then barfeats needs it; it is still removed at the end). Writes ../eval/halfbeat_library.jsonl.
usage: python3 halfbeat_library.py [--apply] [--jobs N]"""
import json, os, sys, glob
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
import halfbeat, restore_audio

def one(b):
    made = []
    try:
        if not os.path.exists(f'st/{b}.wav'):
            if not restore_audio.src(b):
                return dict(id=b, error='no source audio')
            had_wav = os.path.exists(f'wav/{b}.wav')
            restore_audio.restore(b); made.append(f'st/{b}.wav')
            if not had_wav: made.append(f'wav/{b}.wav')
        r = halfbeat.check(b); out = dict(id=b, **r)
        if '--apply' in sys.argv and r['half_off']:
            out['applied'] = halfbeat.apply(b, r)
        return out
    except Exception as e:
        return dict(id=b, error=f'{type(e).__name__}: {e}'[-300:])
    finally:
        for p in made:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    jobs = int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else 3
    ids = sorted(os.path.basename(p)[:-5] for p in glob.glob('st/*.json') if os.path.basename(p).count('.') == 1)
    out = os.path.join(HERE, '..', 'eval', 'halfbeat_library.jsonl')
    with ProcessPoolExecutor(jobs) as ex, open(out, 'w') as f:
        for r in ex.map(one, ids):
            f.write(json.dumps(r) + '\n'); f.flush()
            print(r['id'], 'ERROR ' + r['error'] if 'error' in r else
                  f"margin={r['margin']:+.2f} bars={r['drum_bars']} offbeat={r['offbeat_ratio']} {'HALF-OFF' if r['half_off'] else 'uncertain' if r['uncertain'] else 'ok'}", flush=True)
