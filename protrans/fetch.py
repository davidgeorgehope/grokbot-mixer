"""Download mix or source audio via the residential host (yt-dlp + browser cookies).

Reads HOST from mixes/config.env. Does not hardcode a hostname. Copies the
file back into protrans/cache. Never prints cookie values or credentials.
"""
from __future__ import annotations
import os, subprocess, shlex, json
import paths

def _safe_url(url):
    """Avoid remote-shell globbing of watch?v= by using youtu.be/id."""
    if 'watch?v=' in url:
        vid=url.split('watch?v=',1)[1].split('&')[0]
        return f'https://youtu.be/{vid}'
    return url


def _host():
    env = dict(os.environ)
    cfg = os.path.join(paths.MIXES, 'config.env')
    if os.path.exists(cfg):
        # parse export KEY=value lines without sourcing secrets into logs
        for line in open(cfg):
            line=line.strip()
            if line.startswith('export HOST='):
                val=line.split('=',1)[1].strip().strip("'\"")
                env['HOST']=val
    host = env.get('HOST')
    if not host:
        raise RuntimeError('HOST is not set in config.env (ssh alias of the residential download machine)')
    return host


def _ytdlp_snippet():
    """Remote bash that sets $YTDLP to nightly (via Homebrew Python) or brew."""
    return r"""
YTDLP=""
if [ -d "$HOME/.ytdlp-nightly/lib/python3.15/site-packages/yt_dlp" ]; then
  for py in /opt/homebrew/opt/python@3.13/bin/python3.13 /opt/homebrew/opt/python@3.12/bin/python3.12 /opt/homebrew/opt/python@3.11/bin/python3.11; do
    if [ -x "$py" ]; then
      export PYTHONPATH="$HOME/.ytdlp-nightly/lib/python3.15/site-packages${PYTHONPATH:+:$PYTHONPATH}"
      YTDLP="$py -m yt_dlp"
      break
    fi
  done
fi
if [ -z "$YTDLP" ]; then
  if [ -x /opt/homebrew/bin/yt-dlp ]; then YTDLP=/opt/homebrew/bin/yt-dlp
  else YTDLP=$(command -v yt-dlp || true)
  fi
fi
"""

def ytdlp_remote(url, dest, kind='audio'):
    """Download url on HOST and copy to dest. Returns dest or raises."""
    host = _host()
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    rid = os.path.splitext(os.path.basename(dest))[0]
    remote = None  # set unquoted below
    script = r'''
set -euo pipefail
export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH
SCRIPT_YTDLP_PLACEHOLDER
URL="$1"; DEST="$2"
mkdir -p "$(dirname "$DEST")"
ok=0
for jar in safari chrome; do
  if $YTDLP --no-update --cookies-from-browser "$jar" -f "ba[ext=m4a]/bestaudio/140" -o "$DEST" --no-progress --no-warnings "$URL"; then
    ok=1; break
  fi
done
[ "$ok" = 1 ] && [ -s "$DEST" ]
echo "$DEST"
ls -l "$DEST" | awk '{print $5}'
'''
    script = script.replace('SCRIPT_YTDLP_PLACEHOLDER', _ytdlp_snippet())
    url = _safe_url(url)
    script = script.replace('URL="$1"; DEST="$2"', f'URL={shlex.quote(url)}; DEST="$HOME/protrans_dl/{rid}.m4a"')
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'download failed for {url}: {(r.stderr or r.stdout)[-400:]}')
    remote_path = None
    for line in (r.stdout or '').splitlines():
        if line.startswith('/') and line.endswith('.m4a'):
            remote_path = line.strip()
    if not remote_path:
        raise RuntimeError(f'download succeeded but no remote path printed for {url}: {(r.stdout or "")[-200:]}')
    subprocess.run(['scp','-o','BatchMode=yes', f'{host}:{remote_path}', dest], check=True, capture_output=True)
    return dest

def meta_remote(url):
    """Return {id,title,channel,duration,chapters,description} from HOST (no download)."""
    host = _host()
    script = r'''
set -euo pipefail
export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH
SCRIPT_YTDLP_PLACEHOLDER
URL="$1"
for jar in safari chrome; do
  if $YTDLP --no-update --cookies-from-browser "$jar" --skip-download --no-warnings --no-progress --dump-json "$URL"; then
    exit 0
  fi
done
exit 1
'''
    script = script.replace('SCRIPT_YTDLP_PLACEHOLDER', _ytdlp_snippet())
    url = _safe_url(url)
    script = script.replace('URL="$1"', f'URL={__import__("shlex").quote(url)}')
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'meta failed for {url}: {(r.stderr or "")[-300:]}')
    # dump-json can be one huge line; keep the fields we need
    raw = r.stdout[r.stdout.find('{'):]
    info = json.loads(raw)
    ch = info.get('chapters') or []
    return dict(id=info.get('id'), title=info.get('title'), channel=info.get('channel') or info.get('uploader'),
                duration=info.get('duration'),
                chapters=[dict(start=c.get('start_time'), title=c.get('title')) for c in ch],
                description=(info.get('description') or '')[:12000],
                webpage_url=info.get('webpage_url') or url)

def parse_tracklist(description, chapters=None):
    """Parse 'MM:SS Artist - Title' lines or official chapters into [{t, title}]."""
    import re
    items = []
    if chapters:
        for c in chapters:
            if c.get('start') is None: continue
            items.append(dict(t=float(c['start']), title=c.get('title') or ''))
        if len(items) >= 4:
            return items
    rx = re.compile(r'^\s*(?:[#\-]?\s*)?(?:(\d{1,2}):(\d{2})(?::(\d{2}))?)\s+[-–.]?\s*(.+?)\s*$')
    for line in (description or '').splitlines():
        m = rx.match(line)
        if not m: continue
        a,b,c,title = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        if c is None:
            t = int(a)*60 + int(b)
        else:
            t = int(a)*3600 + int(b)*60 + int(c)
        if title.lower() in ('tracklist','timestamps'): continue
        items.append(dict(t=float(t), title=title))
    # unique increasing times
    seen=set(); out=[]
    for it in items:
        k=round(it['t'],2)
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def search_remote(query, n=5):
    """Return [{id,title,channel,duration}] from HOST ytsearch. No download."""
    host = _host()
    q = f'ytsearch{int(n)}:{query}'
    script = (
        'set -euo pipefail\n'
        'export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH\n'
        + _ytdlp_snippet() +
        f'\nQ={shlex.quote(q)}\n'
        'for jar in safari chrome; do\n'
        '  if $YTDLP --no-update --cookies-from-browser "$jar" --flat-playlist --skip-download --no-warnings --no-progress --print "%(id)s\\t%(title)s\\t%(channel)s\\t%(duration)s" "$Q"; then\n'
        '    exit 0\n'
        '  fi\n'
        'done\n'
        'exit 1\n'
    )
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'search failed for {query}: {(r.stderr or "")[-300:]}')
    out=[]
    for line in (r.stdout or '').splitlines():
        line=line.replace('\\t','\t')
        if '\t' not in line: continue
        parts=line.split('\t')
        if len(parts)<2: continue
        out.append(dict(id=parts[0].strip(), title=parts[1].strip(),
                        channel=parts[2].strip() if len(parts)>2 else '',
                        duration=parts[3].strip() if len(parts)>3 else ''))
    return out
