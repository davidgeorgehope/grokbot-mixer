"""Pin n1121-era st/*.json (and sections) so official scoring does not read live
src2/st files that Mix 10 vocfix / search rewrite.

Does not write into live /workspace/mixes/src2. Does not change rules.json.
Set PROTRANS_SRC2 to ensure_shadow() before importing paths (or in the
environment of a fresh process).
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys
def _safe_symlink(src, dst):
    try:
        os.symlink(src, dst)
    except FileExistsError:
        pass


HERE = os.path.dirname(os.path.abspath(__file__))
MIXES = os.path.abspath(os.path.join(HERE, '..'))
LIVE_SRC2 = os.path.join(MIXES, 'src2')
PIN_DIR = os.path.join(HERE, 'replica', 'st_pin_n1121')
SHADOW = os.path.join(MIXES, 'src2_pin_n1121')  # sibling of src2 so relative ../src/tests resolves
GIT = '/workspace/yt-dj-crate-git'
REV = 'd05db72'  # 2026-11-20 16:23 ET; matches pre-vocfix bak; n1121 (01:32 ET 11/21) used these grids
PREFIX = 'grokbot-mixer/src2/st/'


def official_yts():
    sys.path.insert(0, HERE)
    import run_admitted_tune as T
    yts = set()
    for r in T.load_recs():
        yts.add(r['a']['yt'])
        yts.add(r['b']['yt'])
    return sorted(yts)


def _git_show(rel):
    return subprocess.check_output(['git', '-C', GIT, 'show', f'{REV}:{PREFIX}{rel}'])


def extract_pin(yts=None):
    """Copy n1121-era json + sections for official YT ids into PIN_DIR/st. Live tree is not written."""
    yts = list(yts or official_yts())
    dest = os.path.join(PIN_DIR, 'st')
    os.makedirs(dest, exist_ok=True)
    manifest = dict(rev=REV, n=0, files=[], missing=[])
    for yt in yts:
        for name in (f'{yt}.json', f'{yt}.sections.json'):
            out = os.path.join(dest, name)
            try:
                blob = _git_show(name)
            except subprocess.CalledProcessError:
                manifest['missing'].append(name)
                continue
            with open(out, 'wb') as f:
                f.write(blob)
            manifest['files'].append(dict(name=name, sha256=hashlib.sha256(blob).hexdigest(), n=len(blob)))
            manifest['n'] += 1
    manifest['yts'] = yts
    os.makedirs(PIN_DIR, exist_ok=True)
    with open(os.path.join(PIN_DIR, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    return manifest


def ensure_shadow(yts=None):
    """Shadow src2: symlink live tree, overlay pinned json/sections as real files.

    Mix 10 keeps using /workspace/mixes/src2. Official jobs set PROTRANS_SRC2 to
    the returned path. Existing wav/npz files are symlinks; pinned json are copies.
    """
    os.environ['PROTRANS_SRC2'] = SHADOW
    if 'paths' in sys.modules:
        sys.modules['paths'].SRC2 = SHADOW
    man_p = os.path.join(PIN_DIR, 'manifest.json')
    if not os.path.exists(man_p):
        extract_pin(yts)
    else:
        # refresh if official id count changed
        man = json.load(open(man_p))
        if yts is None:
            try:
                if man.get('yts') != official_yts():
                    extract_pin(yts)
            except Exception:
                pass
    os.makedirs(SHADOW, exist_ok=True)
    # symlink every top-level src2 entry except st, which we build ourselves
    for name in os.listdir(LIVE_SRC2):
        if name == 'st':
            continue
        src = os.path.join(LIVE_SRC2, name)
        dst = os.path.join(SHADOW, name)
        if os.path.lexists(dst) or os.path.exists(dst):
            if os.path.islink(dst) or os.path.isfile(dst):
                os.remove(dst)
            elif os.path.isdir(dst) and not os.path.islink(dst):
                # leftover; leave if it is our dir — but top-level should be links
                continue
        _safe_symlink(src, dst)
    st_live = os.path.join(LIVE_SRC2, 'st')
    st_sh = os.path.join(SHADOW, 'st')
    os.makedirs(st_sh, exist_ok=True)
    # symlink every live st file, then overlay pins as copies
    if os.path.isdir(st_live):
        for name in os.listdir(st_live):
            src = os.path.join(st_live, name)
            dst = os.path.join(st_sh, name)
            pin = os.path.join(PIN_DIR, 'st', name)
            if os.path.exists(pin):
                continue  # overlay below
            if os.path.lexists(dst):
                if os.path.islink(dst) or os.path.isfile(dst):
                    os.remove(dst)
            if not os.path.lexists(dst):
                _safe_symlink(src, dst)
    pin_st = os.path.join(PIN_DIR, 'st')
    n_overlay = 0
    if os.path.isdir(pin_st):
        for name in os.listdir(pin_st):
            src = os.path.join(pin_st, name)
            dst = os.path.join(st_sh, name)
            if os.path.lexists(dst) or os.path.exists(dst):
                if os.path.islink(dst) or os.path.isfile(dst):
                    os.remove(dst)
            shutil.copy2(src, dst)
            n_overlay += 1
    os.environ['PROTRANS_SRC2'] = SHADOW
    if 'paths' in sys.modules:
        sys.modules['paths'].SRC2 = SHADOW
    print(f'st_pin shadow {SHADOW} overlay_files={n_overlay}', flush=True)
    return SHADOW


if __name__ == '__main__':
    man = extract_pin()
    path = ensure_shadow()
    print(json.dumps(dict(pin=PIN_DIR, shadow=path, n=man['n'], missing=man['missing'][:20], n_missing=len(man['missing'])), indent=2))
