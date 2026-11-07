"""Isolated paths. Never writes Mix 07 plans or existing src2 audio."""
import os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
MIXES = os.path.abspath(os.path.join(ROOT, '..'))
SRC2 = os.path.join(MIXES, 'src2')
DELIVER = os.path.join(MIXES, 'deliver', 'protrans')
CACHE = os.path.join(ROOT, 'cache')
LIB = os.path.join(ROOT, 'lib')
CLIPS = os.path.join(ROOT, 'clips')
LOGS = os.path.join(ROOT, 'logs')
RULES = os.path.join(ROOT, 'rules.json')
CORPUS = os.path.join(ROOT, 'corpus.json')
RESULTS = os.path.join(ROOT, 'results')
for d in (CACHE, LIB, CLIPS, LOGS, RESULTS, DELIVER):
    os.makedirs(d, exist_ok=True)
