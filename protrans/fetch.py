"""Download mix or source audio via the residential host (yt-dlp + browser cookies).

Reads HOST from mixes/config.env. Does not hardcode a hostname. Copies the
file back into protrans/cache. Never prints cookie values or credentials.
"""
from __future__ import annotations
import os, subprocess, shlex, json, time, re, hashlib, urllib.parse, urllib.request
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

def normalize_track_title(title, strip_timestamps=True):
    """Strip leading list junk so source search sees the real track name.

    Chapters and descriptions often prefix titles with '//', bullets, a
    list number, or a leftover timestamp. Those tokens poison yt search
    (for example '// DC Breaks - Never Stop' scores -25). Artist names
    like '1991 - Nine Clouds' are left alone.

    strip_timestamps should stay True for search/resolve. Line parsers that
    still need the leading MM:SS for the cue time should pass False.
    """
    s = (title or '').strip()
    if not s:
        return s
    while True:
        prev = s
        s = re.sub(r'^(?://|\\)+\s*', '', s)
        s = re.sub(r'^[-–—•·▪●*]+\s*', '', s)
        if strip_timestamps:
            s = re.sub(r'^\d{1,2}:\d{2}(?::\d{2})?\s+[-–—.]?\s*', '', s)
        s = re.sub(r'^(?:#\s*)?\d{1,2}[.)]\s+', '', s)
        s = re.sub(r'^\[\s*\d{1,2}\s*\]\s+', '', s)
        s = re.sub(r'^\d{1,2}\s+[-–—]\s+', '', s)
        s = s.strip()
        if s == prev:
            break
    return s


_KEEP_TAG = re.compile(r'vip|remix|refix|edit|bootleg|instrumental|extended|dub', re.I)


def strip_tracklist_tags(title):
    """Drop label annotations such as [Forthcoming Fokuz] or [Celsius].

    Version tags like [VIP] or [Remix] stay, because pick_search uses them.
    Used only for source search/scoring; stored titles are unchanged.
    """
    def repl(m):
        return m.group(0) if _KEEP_TAG.search(m.group(0)) else ' '
    s = re.sub(r'\s*\[[^\]]{1,40}\]\s*', repl, title or '')
    return re.sub(r'\s+', ' ', s).strip()


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
# Reuse a file left by a previous attempt so a flaky copy does not re-encode.
if [ -s "$DEST" ]; then
  echo "$DEST"
  ls -l "$DEST" | awk '{print $5}'
  exit 0
fi
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
    if not is_youtube_url(url):
        return _ytdlp_remote_other(host, url, dest, rid)
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
    scp_from_host(host, remote_path, dest)
    return dest


def scp_from_host(host, remote_path, dest, attempts=4):
    """Copy one file off the download host, retrying the copy only (no re-encode)."""
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    last = None
    for i in range(attempts):
        r = subprocess.run(
            ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=30',
             '-o', 'ConnectionAttempts=3', f'{host}:{remote_path}', dest],
            capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 1000:
            return dest
        last = r
        try:
            if os.path.exists(dest) and os.path.getsize(dest) < 1000:
                os.remove(dest)
        except OSError:
            pass
        time.sleep(2 * (i + 1))
    err = (last.stderr or last.stdout or '')[-300:] if last else ''
    raise RuntimeError(f'copy from download host failed for {remote_path}: {err}')

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
            items.append(dict(t=float(c['start']), title=normalize_track_title(c.get('title') or '')))
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
        items.append(dict(t=float(t), title=normalize_track_title(title)))
    # unique increasing times
    seen=set(); out=[]
    for it in items:
        k=round(it['t'],2)
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def _ytdlp_remote_other(host, url, dest, rid):
    """Download a non-YouTube URL on HOST and remux to m4a at dest."""
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    script = r'''
set -euo pipefail
export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH
SCRIPT_YTDLP_PLACEHOLDER
URL="$1"
BASE="$2"
mkdir -p "$(dirname "$BASE")"
# Reuse a previous audio file so a flaky copy does not re-download.
existing=$(ls -1 "$BASE".* 2>/dev/null | head -n 1 || true)
if [ -n "$existing" ] && [ -s "$existing" ]; then
  echo "$existing"
  ls -l "$existing" | awk '{print $5}'
  exit 0
fi
ok=0
for jar in safari chrome NONE; do
  if [ "$jar" = NONE ]; then
    if $YTDLP --no-update -f "bestaudio/best" -o "$BASE.%(ext)s" --no-progress --no-warnings "$URL"; then
      ok=1; break
    fi
  else
    if $YTDLP --no-update --cookies-from-browser "$jar" -f "bestaudio/best" -o "$BASE.%(ext)s" --no-progress --no-warnings "$URL"; then
      ok=1; break
    fi
  fi
done
found=$(ls -1 "$BASE".* 2>/dev/null | head -n 1 || true)
[ "$ok" = 1 ] && [ -n "$found" ] && [ -s "$found" ]
echo "$found"
ls -l "$found" | awk '{print $5}'
'''
    script = script.replace('SCRIPT_YTDLP_PLACEHOLDER', _ytdlp_snippet())
    script = script.replace('URL="$1"', f'URL={shlex.quote(url)}')
    script = script.replace('BASE="$2"', f'BASE={shlex.quote(f"$HOME/protrans_dl/{rid}")}')
    # The second replace left $HOME literal on the remote, which is what we want,
    # but shlex.quote would have quoted it. Inject without quoting the $HOME prefix.
    script = script.replace(
        f'BASE={shlex.quote(f"$HOME/protrans_dl/{rid}")}',
        f'BASE="$HOME/protrans_dl/{rid}"',
    )
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'download failed for {url}: {(r.stderr or r.stdout)[-400:]}')
    remote_path = None
    for line in (r.stdout or '').splitlines():
        line=line.strip()
        if line.startswith('/') and '/protrans_dl/' in line:
            remote_path = line
    if not remote_path:
        raise RuntimeError(f'download succeeded but no remote path printed for {url}: {(r.stdout or "")[-200:]}')
    ext = os.path.splitext(remote_path)[1] or '.bin'
    tmp = dest + '.dl' + ext
    scp_from_host(host, remote_path, tmp)
    return ensure_m4a(tmp, dest)


def ensure_m4a(src, dest):
    """Remux downloaded audio to m4a at dest. Leaves dest in place."""
    if not src or not os.path.exists(src):
        raise RuntimeError(f'no audio to remux: {src}')
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    if src.endswith('.m4a') and os.path.abspath(src) == os.path.abspath(dest):
        return dest
    if src.endswith('.m4a'):
        if os.path.abspath(src) != os.path.abspath(dest):
            os.replace(src, dest)
        return dest
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', src, '-c:a', 'aac', '-b:a', '256k', dest],
        check=True, capture_output=True, text=True)
    try:
        if os.path.abspath(src) != os.path.abspath(dest):
            os.remove(src)
    except OSError:
        pass
    return dest


# Ordered fallback sources for studio-track search. YouTube stays first;
# later sources run only when YouTube has no confident hit.
SOURCE_ORDER = ('youtube', 'soundcloud', 'bandcamp')
YTDLP_SEARCH_PREFIX = {
    'youtube': 'ytsearch',
    'soundcloud': 'scsearch',
}


def is_youtube_url(url):
    u = (url or '').lower()
    return 'youtu.be/' in u or 'youtube.com/' in u or 'youtube-nocookie.com/' in u


def parse_duration(val):
    """Parse a yt-dlp duration field to seconds, or None if unknown."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val == val else None  # NaN check
    s = str(val).strip()
    if not s or s.upper() in ('NA', 'N/A', 'NONE', 'NULL', 'NA', '?'):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    if ':' in s:
        parts = s.split(':')
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        t = 0.0
        for n in nums:
            t = t * 60.0 + n
        return t
    return None


def audio_duration(path):
    """File duration in seconds via ffprobe, or None."""
    if not path or not os.path.exists(path):
        return None
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', path],
        capture_output=True, text=True)
    return parse_duration((r.stdout or '').strip())


def media_key(hit_or_id):
    """Stable filename stem for a resolved source (legacy YouTube id unchanged)."""
    if isinstance(hit_or_id, dict):
        src = (hit_or_id.get('source') or 'youtube').lower()
        tid = str(hit_or_id.get('id') or hit_or_id.get('yt') or '')
        if src in ('youtube', '', 'yt'):
            return tid
        raw = f'{src}_{tid}'
        return re.sub(r'[^A-Za-z0-9._-]+', '_', raw)[:80]
    s = str(hit_or_id or '')
    if s.startswith('http://') or s.startswith('https://'):
        return 'url_' + hashlib.sha1(s.encode()).hexdigest()[:16]
    return s


def media_url(hit_or_id):
    """Absolute URL yt-dlp can fetch for a resolved source or legacy id."""
    if isinstance(hit_or_id, dict):
        if hit_or_id.get('url'):
            return hit_or_id['url']
        tid = hit_or_id.get('id') or hit_or_id.get('yt')
        src = (hit_or_id.get('source') or 'youtube').lower()
        if src in ('youtube', '', 'yt') and tid:
            return f'https://youtu.be/{tid}'
        return tid
    s = str(hit_or_id or '')
    if s.startswith('http://') or s.startswith('https://'):
        return s
    return f'https://youtu.be/{s}'


def parse_search_line(line):
    """Parse one yt-dlp --print search row into a hit dict."""
    line = (line or '').replace('\\t', '\t').strip()
    if '\t' not in line:
        return None
    parts = line.split('\t')
    if len(parts) < 2:
        return None
    hit = dict(id=parts[0].strip(), title=parts[1].strip(),
               channel=parts[2].strip() if len(parts) > 2 else '',
               duration=parts[3].strip() if len(parts) > 3 else '')
    if len(parts) > 4 and parts[4].strip():
        hit['url'] = parts[4].strip()
    if len(parts) > 5 and parts[5].strip():
        hit['extractor'] = parts[5].strip()
    return hit


def _annotate_hits(rows, source):
    out = []
    for r in rows:
        h = dict(r)
        h['source'] = source
        if not h.get('url'):
            if source == 'youtube' and h.get('id'):
                h['url'] = f"https://youtu.be/{h['id']}"
            elif source == 'soundcloud' and h.get('id') and str(h['id']).startswith('http'):
                h['url'] = h['id']
        out.append(h)
    return out


def _ytdlp_search(query, n, prefix):
    """Return hits from a yt-dlp search prefix (ytsearch, scsearch, ...) on HOST."""
    host = _host()
    q = f'{prefix}{int(n)}:{query}'
    # webpage_url + extractor are optional trailing columns; older parsers ignore them.
    print_fmt = '%(id)s\\t%(title)s\\t%(channel,uploader|)s\\t%(duration)s\\t%(webpage_url,url|)s\\t%(extractor|)s'
    script = (
        'set -euo pipefail\n'
        'export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH\n'
        + _ytdlp_snippet() +
        f'\nQ={shlex.quote(q)}\n'
        f'PRINT={shlex.quote(print_fmt)}\n'
        'for jar in safari chrome NONE; do\n'
        '  if [ "$jar" = NONE ]; then\n'
        '    if $YTDLP --no-update --flat-playlist --skip-download --no-warnings --no-progress --print "$PRINT" "$Q"; then\n'
        '      exit 0\n'
        '    fi\n'
        '  else\n'
        '    if $YTDLP --no-update --cookies-from-browser "$jar" --flat-playlist --skip-download --no-warnings --no-progress --print "$PRINT" "$Q"; then\n'
        '      exit 0\n'
        '    fi\n'
        '  fi\n'
        'done\n'
        'exit 1\n'
    )
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'search failed for {query}: {(r.stderr or "")[-300:]}')
    out = []
    for line in (r.stdout or '').splitlines():
        hit = parse_search_line(line)
        if hit:
            out.append(hit)
    return out


def search_remote(query, n=5, source='youtube'):
    """Return [{id,title,channel,duration,url,source}] from HOST. No download.

    source='youtube' (default) keeps the original ytsearch path used by mix
    discovery. Fallback studio-track sources are soundcloud (scsearch) and
    bandcamp (public search API / page, fetched on HOST).
    """
    source = (source or 'youtube').lower()
    if source in YTDLP_SEARCH_PREFIX:
        rows = _ytdlp_search(query, n, YTDLP_SEARCH_PREFIX[source])
        return _annotate_hits(rows, source)
    if source == 'bandcamp':
        return _annotate_hits(bandcamp_search_remote(query, n=n), 'bandcamp')
    raise RuntimeError(f'unknown search source {source}')


def parse_bandcamp_api(payload, n=5):
    """Turn a Bandcamp autocomplete_elastic (or similar) JSON object into hits."""
    if not payload:
        return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return []
    results = payload.get('auto') or payload
    if isinstance(results, dict):
        results = results.get('results') or results.get('items') or []
    if not isinstance(results, list):
        return []
    out = []
    for item in results:
        if not isinstance(item, dict):
            continue
        typ = (item.get('type') or item.get('item_type') or '').lower()
        if typ and typ not in ('t', 'track', 'a', 'album'):
            continue
        url = (item.get('item_url') or item.get('url') or '')
        path = item.get('item_url_path') or ''
        root = (item.get('item_url_root') or item.get('band_url') or '').rstrip('/')
        if not url:
            if isinstance(path, str) and path.startswith('http'):
                url = path
            elif root and path:
                url = root + (path if path.startswith('/') else '/' + path)
        if typ in ('a', 'album'):
            # albums are not a single studio track
            continue
        if typ not in ('t', 'track') and '/track/' not in (url or ''):
            continue
        if not url or '/track/' not in url:
            continue
        title = (item.get('name') or item.get('title') or '').strip()
        artist = (item.get('band_name') or item.get('artist') or item.get('band') or '').strip()
        full = f'{artist} - {title}' if artist and title else (title or artist)
        tid = str(item.get('id') or url.rstrip('/').rsplit('/', 1)[-1])
        dur = item.get('duration') or item.get('track_duration')
        out.append(dict(
            id=tid, title=full, channel=artist, duration=dur or '',
            url=url, source='bandcamp', extractor='Bandcamp',
        ))
        if len(out) >= int(n):
            break
    return out


def parse_bandcamp_html(html, n=5):
    """Extract track links and titles from a Bandcamp search HTML page."""
    if not html:
        return []
    out, seen = [], set()
    # heading link plus nearby "by Artist"
    rx = re.compile(
        r'<div class="heading">\s*<a href="(https?://[^"]+\.bandcamp\.com/track/[^"]+)"[^>]*>(.*?)</a>.*?'
        r'<div class="subhead">\s*by\s+([^<]+)',
        re.I | re.S,
    )
    for url, title, artist in rx.findall(html):
        url = url.split('?')[0].rstrip('/')
        if url in seen:
            continue
        title = re.sub(r'<[^>]+>', '', title).strip()
        artist = artist.strip()
        tid = url.rsplit('/', 1)[-1]
        seen.add(url)
        out.append(dict(id=tid, title=f'{artist} - {title}' if artist else title,
                        channel=artist, duration='', url=url,
                        source='bandcamp', extractor='Bandcamp'))
        if len(out) >= int(n):
            break
    if out:
        return out
    for url in re.findall(r'https?://[a-z0-9-]+\.bandcamp\.com/track/[a-z0-9-]+', html or '', re.I):
        url = url.rstrip('/')
        if url in seen:
            continue
        seen.add(url)
        slug = url.rsplit('/', 1)[-1].replace('-', ' ')
        host = urllib.parse.urlparse(url).hostname or ''
        artist = host.split('.')[0].replace('-', ' ')
        out.append(dict(id=url.rsplit('/', 1)[-1], title=f'{artist} - {slug}',
                        channel=artist, duration='', url=url,
                        source='bandcamp', extractor='Bandcamp'))
        if len(out) >= int(n):
            break
    return out


def bandcamp_search_remote(query, n=5):
    """Search Bandcamp for tracks on HOST (cloud IPs are often challenged)."""
    host = _host()
    q = query or ''
    api_body = json.dumps({
        'search_text': q,
        'search_filter': 't',
        'full_page': True,
        'fan_id': None,
    })
    search_url = 'https://bandcamp.com/search?q=' + urllib.parse.quote(q) + '&item_type=t'
    # Run a tiny Python helper on the host so we don't depend on local egress.
    py = r'''
import json, sys, urllib.request
q = sys.argv[1]
n = int(sys.argv[2])
ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
def grab(url, data=None, typ="application/json"):
    headers = {"User-Agent": ua, "Accept": typ, "Origin": "https://bandcamp.com",
               "Referer": "https://bandcamp.com/search"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")
body = sys.argv[3].encode()
out = {"api": None, "html": None, "api_error": None, "html_error": None}
try:
    raw = grab("https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic", data=body)
    out["api"] = raw
except Exception as e:
    out["api_error"] = str(e)[:200]
try:
    out["html"] = grab(sys.argv[4], typ="text/html")
except Exception as e:
    out["html_error"] = str(e)[:200]
print(json.dumps(out))
'''
    script = (
        'set -euo pipefail\n'
        'export PATH=/opt/homebrew/bin:$PATH\n'
        'python3 - ' + ' '.join(
            shlex.quote(x) for x in (q, str(int(n)), api_body, search_url)
        ) + ' <<\'PY\'\n' + py + 'PY\n'
    )
    r = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=20', host, 'bash','-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'bandcamp search failed for {query}: {(r.stderr or "")[-300:]}')
    raw = (r.stdout or '').strip()
    try:
        blob = json.loads(raw[raw.find('{'):])
    except ValueError as e:
        raise RuntimeError(f'bandcamp search: bad payload for {query}: {e}')
    hits = []
    api_raw = blob.get('api')
    if api_raw:
        # API may be JSON or a challenge page
        try:
            hits = parse_bandcamp_api(json.loads(api_raw) if isinstance(api_raw, str) and api_raw.lstrip()[:1] in '{[' else api_raw, n=n)
        except ValueError:
            hits = []
    if not hits and blob.get('html'):
        hits = parse_bandcamp_html(blob['html'], n=n)
    if not hits and (blob.get('api_error') or blob.get('html_error')) and not (blob.get('api') or blob.get('html')):
        raise RuntimeError(f"bandcamp search failed for {query}: {blob.get('api_error') or blob.get('html_error')}")
    return hits
