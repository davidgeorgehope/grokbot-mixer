#!/usr/bin/env python3
"""CLI for the isolated corpus_v2 pipeline. See docs/LEARNED_RANKER.md."""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus_v2_pipeline as P

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print('usage: run_corpus_v2.py [all|discover|ingest [N]|split|manifest|train|retry-slash|retry-resolve [N]|resume]')
        return 0
    cmd = argv[0]
    if cmd == 'discover':
        P.discover()
    elif cmd == 'ingest':
        P.ingest_all(limit=int(argv[1]) if len(argv) > 1 else None)
    elif cmd == 'split':
        import json
        print(json.dumps(P.assign_split(), indent=2))
    elif cmd == 'manifest':
        P.write_manifest()
        print('wrote', P.MANIFEST)
    elif cmd == 'train':
        import json
        split = json.load(open(P.SPLIT)) if os.path.exists(P.SPLIT) else P.assign_split()
        print(json.dumps(P.train_ranker(split), indent=2))
    elif cmd == 'retry-slash':
        import json
        print(json.dumps(P.retry_slash_rejects(), indent=2))
    elif cmd == 'retry-resolve':
        import json
        print(json.dumps(P.retry_resolve_rejects(limit=int(argv[1]) if len(argv) > 1 else None), indent=2))
    elif cmd == 'resume':
        P.resume()
    elif cmd == 'all':
        P.run_all()
    else:
        raise SystemExit(f'unknown command {cmd}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
