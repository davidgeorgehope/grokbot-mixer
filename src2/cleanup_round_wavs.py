"""Keep only the current render round and the best prior round's raw/master WAVs.

A round name looks like mix07r9 (family prefix + digits). Best = lowest
guard_{name}/guardrails.json n_fail, then longest *_meta.json len_sec.

usage:
  python3 cleanup_round_wavs.py mix07r9
  python3 cleanup_round_wavs.py mix07r9 --delivered   # delete every family round WAV
"""
import glob, json, os, re, sys

def family(name):
    m = re.match(r'^(.*r)(\d+)$', name)
    return (m.group(1), int(m.group(2))) if m else (name, None)

def score(name, src):
    n_fail = 999
    g = os.path.join(src, f'guard_{name}', 'guardrails.json')
    if os.path.exists(g):
        try:
            n_fail = int(json.load(open(g)).get('n_fail', 999))
        except Exception:
            pass
    dur = 0.0
    meta = os.path.join(src, f'{name}_meta.json')
    if os.path.exists(meta):
        try:
            dur = float(json.load(open(meta)).get('len_sec') or 0)
        except Exception:
            pass
    pyt = 99
    import re
    for cand in (os.path.join(src, '..', 'mix07', f'{name}_pytest.log'), os.path.join(src, f'{name}_pytest.log')):
        if os.path.exists(cand):
            m = re.search(r'(\d+) failed', open(cand).read())
            if m:
                pyt = int(m.group(1)); break
            if 'passed' in open(cand).read() and 'failed' not in open(cand).read().split('short test summary')[-1] if False else '':
                pyt = 0; break
    has = os.path.exists(os.path.join(src, f'{name}_raw.wav')) or os.path.exists(os.path.join(src, f'{name}_master.wav'))
    return (has, -n_fail, -pyt, dur)

def peers(prefix, src):
    names = set()
    for p in glob.glob(os.path.join(src, f'{prefix}[0-9]*_raw.wav')) + glob.glob(os.path.join(src, f'{prefix}[0-9]*_master.wav')):
        base = os.path.basename(p)
        if base.endswith('_raw.wav'):
            names.add(base[:-8])
        elif base.endswith('_master.wav'):
            names.add(base[:-11])
    return names

def cleanup(current, delivered=False, src=None):
    src = src or os.path.dirname(os.path.abspath(__file__))
    current = os.path.basename(current)
    pref, _ = family(current)
    names = peers(pref, src)
    if current not in names and (os.path.exists(os.path.join(src, current + '_raw.wav')) or os.path.exists(os.path.join(src, current + '_master.wav'))):
        names.add(current)
    if delivered:
        keep = set()
    else:
        others = [n for n in names if n != current]
        keep = {current}
        if others:
            keep.add(max(others, key=lambda n: score(n, src)))
    removed = []
    for n in sorted(names):
        if n in keep:
            continue
        for suf in ('_raw.wav', '_master.wav'):
            p = os.path.join(src, n + suf)
            if os.path.exists(p):
                os.remove(p)
                removed.append(os.path.basename(p))
    return keep, removed

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--delivered']
    delivered = '--delivered' in sys.argv[1:]
    if not args:
        sys.exit('usage: cleanup_round_wavs.py NAME [--delivered]')
    keep, removed = cleanup(args[0], delivered=delivered)
    print('cleanup_round_wavs keep', sorted(keep), 'removed', removed or 'nothing')
