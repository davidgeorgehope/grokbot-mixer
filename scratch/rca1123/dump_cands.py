#!/usr/bin/env python3
"""Dry candidate dumps for js13. Isolated scratch. No pro audio. No live mix_simple edit."""
import json, os, subprocess, sys
from pathlib import Path

SRC2 = '/workspace/mixes/src2'
PLAN = '/tmp/rca1123/thin_dropcue/plan.json'
RULES = json.load(open('/workspace/mixes/protrans/rules.json'))
sys.path.insert(0, '/workspace/mixes/protrans')
import recreate
base_env = recreate.apply_rules(RULES)

ARMS = [
    ('default', {}),
    ('SLOWDOWN', {'SLOWDOWN': '1'}),
    ('STRUCT_COND', {'STRUCT_COND': '1'}),
    ('OUTRO_QC', {'OUTRO_QC': '1'}),
    ('EXITPOS', {'EXITPOS': '1'}),
    ('epg_drop', {'EXITPOS': '1', 'EXITPOS_DROP': '1'}),
    ('STRUCT_THIN', {'STRUCT_THIN': '1'}),
    ('THIN_DROPCUE', {'THIN_DROPCUE': '1'}),
    ('STRUCT_BREAK', {'STRUCT_BREAK': '1'}),
]

SCRIPT_DEFAULT = 'mix_simple.py'
SCRIPT_BREAK = '/tmp/rca1123/engine/mix_simple_break.py'
OUT = Path('/tmp/rca1123/dump')
OUT.mkdir(parents=True, exist_ok=True)

def run(name, delta):
    env = os.environ.copy()
    env.update(base_env)
    env.update(delta)
    env['DUMP_CANDS'] = str(OUT / f'c_{name}.json')
    env['BB_SCRATCH'] = str(OUT / name)
    Path(env['BB_SCRATCH']).mkdir(parents=True, exist_ok=True)
    # do not leak other research flags
    script = SCRIPT_BREAK if 'STRUCT_BREAK' in delta else SCRIPT_DEFAULT
    cmd = [sys.executable, script, '--plan', PLAN, '--out', str(Path(env['BB_SCRATCH'])/'x'), '--dry']
    r = subprocess.run(cmd, cwd=SRC2, env=env, capture_output=True, text=True)
    Path(OUT / f'{name}.stderr').write_text(r.stderr)
    Path(OUT / f'{name}.stdout').write_text(r.stdout)
    if r.returncode != 0 and not Path(env['DUMP_CANDS']).exists():
        print(f'FAIL {name} rc={r.returncode}')
        print(r.stderr[-2000:])
        return
    cs = json.load(open(env['DUMP_CANDS']))
    # unique by win
    seen=set(); top=[]
    for row in cs:
        w=tuple(row['win'])
        if w in seen: continue
        seen.add(w); top.append(row)
    print(f'\n=== {name} n={len(seen)} script={Path(script).name} ===')
    for i,row in enumerate(top[:8]):
        mark='  '
        w=row['win']
        if w==['n',160,None,32,32]: mark='**'
        if w==['n',256,None,48,16]: mark='d '
        if w==['n',256,None,32,32]: mark='p '
        if w==['n',256,None,64,16]: mark='t '
        if w==['n',224,None,48,16]: mark='e '
        print(f"  {mark}{i} cost={row['cost']:8.1f} win={row['win']} pen={row.get('pen')}")
    # rank of target windows
    want={('n',160,None,32,32):'break 160/32/32',
          ('n',128,None,32,32):'break 128/32/32',
          ('n',256,None,48,16):'default',
          ('n',256,None,64,16):'thin_dropcue',
          ('n',224,None,48,16):'epg_drop'}
    idx={tuple(r['win']):i for i,r in enumerate(top)}
    for k,lab in want.items():
        if k in idx:
            r=next(x for x in top if tuple(x['win'])==k)
            print(f'    rank {idx[k]:3d} {lab} cost={r["cost"]:.1f}')
    print('  PICK', top[0]['win'], 'cost', top[0]['cost'])

for name,delta in ARMS:
    run(name,delta)
