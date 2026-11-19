"""Grok vision judge client (xAI only). Key: $XAI_API_KEY, else /workspace/private/.xai_key (filled from 1Password
vault Grokbot, item 'xAI API key'); never printed or logged. Every call is appended to runs/calls.jsonl with token usage."""
import base64, json, os, time, urllib.request
H = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get('JUDGE_MODEL', 'grok-4.20-0309-non-reasoning')
URL = 'https://api.x.ai/v1/chat/completions'
PRICE = {'grok-4.20-0309-non-reasoning': (1.25, 2.50), 'grok-4.20-0309-reasoning': (1.25, 2.50), 'grok-4.3': (1.25, 2.50), 'grok-4.7': (2.0, 6.0), 'grok-4.6': (2.0, 6.0), 'grok-4.5': (2.0, 6.0)}  # $/M in, out (xAI /v1/language-models, 2026-11-18)
LOG = os.path.join(H, 'runs', 'calls.jsonl')

def _key():
    k = os.environ.get('XAI_API_KEY')
    if not k:
        k = open('/workspace/private/.xai_key').read().strip()
    return k

def img(path):
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(open(path, 'rb').read()).decode(), 'detail': 'high'}}

def ask(system, parts, tag, model=None, temperature=0.0, retries=3):
    model = model or MODEL
    body = dict(model=model, temperature=temperature, response_format={'type': 'json_object'},
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': parts}])
    data = json.dumps(body).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(URL, data=data, headers={'Authorization': 'Bearer ' + _key(), 'Content-Type': 'application/json'})
            t0 = time.time(); r = json.load(urllib.request.urlopen(req, timeout=180))
            txt = r['choices'][0]['message']['content']; u = r.get('usage', {})
            try: out = json.loads(txt)
            except Exception: out = {'_unparsed': txt[:2000]}
            pi, po = PRICE.get(model, (2.0, 6.0))
            cost = u['cost_in_usd_ticks'] / 1e10 if 'cost_in_usd_ticks' in u else (u.get('prompt_tokens', 0) * pi + (u.get('total_tokens', 0) - u.get('prompt_tokens', 0)) * po) / 1e6  # xAI bills in 1e-10 USD ticks
            open(LOG, 'a').write(json.dumps(dict(tag=tag, model=model, t=round(time.time() - t0, 1), usage=u, cost=round(cost, 5), out=out)) + '\n')
            return out
        except Exception as ex:
            err = str(ex)[:300]; time.sleep(3 * (att + 1))
    open(LOG, 'a').write(json.dumps(dict(tag=tag, model=model, error=err)) + '\n')
    return {'_error': err}
