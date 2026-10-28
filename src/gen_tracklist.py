#!/usr/bin/env python3
"""Timestamped tracklist (with Camelot keys) from a mix_simple.py meta.
Titles come from OUT if it already lists the tracks as '(youtu.be/<id>)'; otherwise the id is shown.
usage: gen_tracklist.py META OUT.md "TITLE"
  e.g. python3 src/gen_tracklist.py src2/mixS_meta.json dj-mix-03-60-tracklist.md "DJ Mix 03 – Liquid (60 min)" """
import json,re,sys
meta,OUT,TITLE=sys.argv[1:4]
M=json.load(open(meta));BAR=M['bar_sec'];T={}
try:
  for l in open(OUT):
    m=re.match(r'\s*\d+\.\s+[\d:]+\s+(.*?)(?:\s+\[\w+\])?\s+\(youtu\.be/([\w-]+)\)',l)
    if m:T[m.group(2)]=m.group(1)
except FileNotFoundError:pass
K={}
for t in M['trans']:
  ka,kb=(t.get('keys') or '->').split('->');K.setdefault(t['a'],ka);K.setdefault(t['b'],kb)
fmt=lambda s:f"{int(s)//60}:{int(s)%60:02d}"
key=lambda i:f"  [{K[i]}]" if K.get(i) and K[i]!='None' else ''
short=lambda i:T[i].split('–',1)[-1].strip() if i in T else i
order=[(M['plan'][0]['id'],0.0)]+[(t['b'],t['start_bar']*BAR) for t in M['trans']]
md=[f"# {TITLE}\n",f"Length {fmt(M['len_sec'])} · 174 BPM · times from {meta} · crossfader engine: one monotonic equal-power 16-bar crossfade per blend, constant per-track gain (-16 LUFS), no stems/EQ/ducking\n"]
md+=[f"{i:2d}. {fmt(s)}  {T.get(b,b)}{key(b)}  (youtu.be/{b})" for i,(b,s) in enumerate(order,1)]
md.append("\n## Transitions")
for t in M['trans']:
  md.append(f"- {fmt(t['start_bar']*BAR)} {short(t['a'])}{key(t['a'])} → {short(t['b'])}{key(t['b'])}: {t['tech']}"+(f" ({'; '.join(n.strip(': ') for n in t['notes'])})" if t.get('notes') else ''))
open(OUT,'w').write('\n'.join(md)+'\n');print('wrote',OUT,len(order),'tracks',fmt(M['len_sec']))
