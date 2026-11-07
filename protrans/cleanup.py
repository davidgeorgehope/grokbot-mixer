"""Disk hygiene: keep clips + needed source m4as; drop full mixes, stems, and scored renders."""
from __future__ import annotations
import os, json, shutil, glob
import paths

LEDGER = os.path.join(paths.LOGS, 'created.jsonl')

def note(kind, path, keep=False):
    os.makedirs(paths.LOGS, exist_ok=True)
    with open(LEDGER, 'a') as f:
        f.write(json.dumps(dict(kind=kind, path=path, keep=keep)) + '\n')

def _rm(path):
    if not path: return
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.lexists(path):
        try: os.remove(path)
        except OSError: pass

def drop_full_mix(path, downloaded=False):
    """Delete a mix we downloaded. Never touch shared pro_sets/ files."""
    if not downloaded: return
    path = os.path.abspath(path)
    allow = os.path.abspath(os.path.join(paths.CACHE, 'mixes'))
    if path.startswith(allow + os.sep) or os.path.dirname(path) == allow:
        _rm(path)

def drop_render_dir(d, keep_examples=()):
    keep = {os.path.abspath(p) for p in keep_examples}
    if not os.path.isdir(d): return
    for root, dirs, files in os.walk(d):
        for n in files:
            p = os.path.abspath(os.path.join(root, n))
            if p in keep: continue
            if n.endswith(('.wav', '.mp3', '.flac', '.m4a', '.raw')):
                _rm(p)

def drop_stems():
    _rm(os.path.join(paths.CACHE, 'stems'))
    for p in glob.glob('/tmp/protrans*'):
        _rm(p)
    _rm('/tmp/blend_bench')
    _rm('/tmp/protrans_bench')
    _rm('/tmp/protrans_work')

def drop_our_src2(created):
    """Remove src2 files this harness created (never pre-existing tracks)."""
    for p in created:
        ap = os.path.abspath(p)
        if ap.startswith(os.path.abspath(paths.SRC2) + os.sep):
            _rm(ap)

def drop_stretched(lib_st):
    _rm(lib_st)
