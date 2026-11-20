#!/usr/bin/env python3
"""Killable Demucs vocal-stem worker for talkover._vocals.

Run as a standalone script so the caller's __main__ is never re-imported.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import talkover as T

def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    inp, outp, label, errp = argv[1], argv[2], argv[3], argv[4]
    T._IN_VOCALS_WORKER = True
    try:
        y = np.load(inp)['y']
        v = T._vocals_impl(y, label)
        np.savez(outp, v=v)
    except Exception as e:
        try:
            open(errp, 'w').write(str(e))
        except OSError:
            pass
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
