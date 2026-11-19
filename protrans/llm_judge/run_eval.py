"""Run the judge on the labelled cases. usage: run_eval.py <prompt_version> <split dev|heldout|all> [repeats]
Tasks: defect (single PNG), pair (two PNGs, less defective, both orders), dec (decision chart, both orders).
Writes runs/<ver>_<split>.jsonl (one row per call, with truth)."""
import json, os, sys, random, hashlib, glob
from concurrent.futures import ThreadPoolExecutor
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import judge, prompts
from redact import redact
RED = os.path.join(H, 'redacted')

def blind(png):
    out = os.path.join(RED, os.path.basename(png))
    if not os.path.exists(out): redact(png, out)
    return out

def chart(label, png, ver):
    """message parts for one chart: whole redacted figure, or (v3) one image per panel"""
    b = blind(png)
    if ver != 'v3': return [{'type': 'text', 'text': label}, ('img', b)]
    from redact import panels
    pre = os.path.join(RED, 'panels', os.path.basename(b)[:-4]); os.makedirs(os.path.dirname(pre), exist_ok=True)
    ps = sorted(glob.glob(pre + '_p*.png')) or panels(b, pre)
    out = [{'type': 'text', 'text': label + f' ({len(ps)} panels, top to bottom)'}]
    for k, p in enumerate(ps): out += [{'type': 'text', 'text': f'{label} panel {k+1}:'}, ('img', p)]
    return out

def load(fn):
    p = os.path.join(H, fn); return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

def jobs(ver, split, reps):
    P = prompts.P[ver]; J = []
    singles = load('cases.jsonl') + load('cases_human.jsonl')
    for c in singles:
        if split != 'all' and c['split'] != split: continue
        for r in range(reps):
            J.append(dict(task='defect', case=c['case'], rep=r, truth=c['truth'], hard=c.get('hard'), source=c['source'],
                          sys=P['defect'], parts=chart('Chart', c['png'], ver)))
    # pairwise less-defective: injected vs clean of the same render, plus human pairs
    byp = {}
    for c in load('cases.jsonl'): byp.setdefault(c['pair'], {})[c['source']] = c
    pairs = [dict(case=f"ipair__{p}", better=d['real_render']['png'], worse=d['injected']['png'], split=d['real_render']['split'], src='injected')
             for p, d in byp.items() if 'real_render' in d and 'injected' in d and not any(d['real_render']['truth'].values())]
    pairs += [dict(h, src='human') for h in load('pairs_human.jsonl')]
    for pr in pairs:
        if split != 'all' and pr['split'] != split: continue
        for order in ('better_first', 'worse_first'):
            a, b = (pr['better'], pr['worse']) if order == 'better_first' else (pr['worse'], pr['better'])
            for r in range(reps):
                J.append(dict(task='pair', case=pr['case'], src=pr['src'], rep=r, order=order, truth='A' if order == 'better_first' else 'B', sys=P['pair'],
                              parts=chart('Chart A', a, ver) + chart('Chart B', b, ver)))
    for c in load('cases_dec.jsonl'):
        if split != 'all' and c['split'] != split: continue
        for order, png, truth in (('orig', c['png'], c['closer']), ('swap', c['png_swap'], 'Y' if c['closer'] == 'X' else 'X')):
            for r in range(reps):
                J.append(dict(task='dec', case=c['case'], kind=c['kind'], rep=r, order=order, truth=truth, sys=P['dec'],
                              parts=[{'type': 'text', 'text': 'Plans:'}, ('img', png)]))
    return J

def run(j, ver):
    parts = [judge.img(p[1]) if isinstance(p, tuple) else p for p in j['parts']]
    out = judge.ask(j['sys'], parts, tag=f"{ver}:{j['task']}:{j['case']}:{j.get('order','')}:{j['rep']}")
    row = {k: v for k, v in j.items() if k not in ('sys', 'parts')}; row['out'] = out; row['ver'] = ver; return row

if __name__ == '__main__':
    ver, split = sys.argv[1], sys.argv[2]; reps = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    tasks = sys.argv[4].split(',') if len(sys.argv) > 4 else ['defect', 'pair', 'dec']
    J = [j for j in jobs(ver, split, reps) if j['task'] in tasks]
    random.Random(7).shuffle(J); print(len(J), 'calls', flush=True)
    outp = os.path.join(H, 'runs', f'{ver}_{split}' + (('_' + os.environ['JUDGE_MODEL']) if os.environ.get('JUDGE_MODEL') else '') + '.jsonl')
    with ThreadPoolExecutor(6) as ex, open(outp, 'a') as f:
        for row in ex.map(lambda j: run(j, ver), J):
            f.write(json.dumps(row) + '\n'); f.flush()
    print('wrote', outp)
