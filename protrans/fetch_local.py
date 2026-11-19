"""Local-box and remote fetch helpers for fetch.py.

YouTube runs on this box. SoundCloud and Bandcamp prefer FETCH_PREFERRED_HOST
when that is set, then the residential HOST. Never prints cookie values or
credentials. Host names and local browser-profile paths come from config.env
or the environment, not from this file.
"""
from __future__ import annotations
import glob, json, os, shutil, subprocess

import paths

LOCAL_DL = os.path.join(paths.CACHE, 'protrans_dl')


def config_value(key, default=''):
    """Return a config.env or environment value. config.env wins if the key is set there."""
    cfg = os.path.join(paths.MIXES, 'config.env')
    if os.path.exists(cfg):
        prefixes = ('export %s=' % key, '%s=' % key)
        for line in open(cfg):
            line = line.strip()
            if line.startswith(prefixes):
                return line.split('=', 1)[1].strip().strip("'\"")
    val = os.environ.get(key)
    if val is not None and val != '':
        return val
    return default


def preferred_fetch_host():
    return config_value('FETCH_PREFERRED_HOST')


def cookieless_hosts():
    raw = config_value('FETCH_COOKIELESS_HOSTS')
    hosts = [h.strip() for h in raw.split(',') if h.strip()]
    pref = preferred_fetch_host()
    if pref and pref not in hosts:
        hosts.append(pref)
    return tuple(hosts)


def fetch_host_order(fallback_host):
    """Preferred Linux fetch host first, then the residential fallback."""
    hosts, seen = [], set()
    for h in (preferred_fetch_host(), fallback_host):
        if h and h not in seen:
            seen.add(h)
            hosts.append(h)
    return hosts


def local_ytdlp():
    for cand in (os.path.expanduser('~/.local/bin/yt-dlp'), shutil.which('yt-dlp')):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    raise RuntimeError('yt-dlp not found on this box')


def chrome_profile():
    root = config_value('FETCH_CHROME_PROFILE') or config_value('CHROME_PROFILE')
    if not root:
        return None
    root = os.path.expanduser(root)
    cookies = os.path.join(root, 'Default', 'Cookies')
    if os.path.isfile(cookies):
        return root
    return None


def ssh_bash(host, script, timeout=20):
    return subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', f'ConnectTimeout={int(timeout)}',
         host, 'bash', '-s'],
        input=script, text=True, capture_output=True)


def is_cookieless_host(host):
    return (host or '') in cookieless_hosts()


def choose_dl_dir_snippet():
    """Remote bash: pick a writable download dir without touching a broken symlink."""
    return (
        'choose_dl_dir() {\n'
        '  prefer="$HOME/protrans_dl"\n'
        '  fallback="$HOME/protrans_dl_local"\n'
        '  if [ -d "$prefer" ] && [ -w "$prefer" ]; then\n'
        '    printf "%s\\n" "$prefer"\n'
        '    return 0\n'
        '  fi\n'
        '  if [ -L "$prefer" ]; then\n'
        '    # Broken or unmounted symlink (e.g. an external volume). Leave it alone.\n'
        '    mkdir -p "$fallback"\n'
        '    printf "%s\\n" "$fallback"\n'
        '    return 0\n'
        '  fi\n'
        '  if mkdir -p "$prefer" 2>/dev/null; then\n'
        '    printf "%s\\n" "$prefer"\n'
        '    return 0\n'
        '  fi\n'
        '  mkdir -p "$fallback"\n'
        '  printf "%s\\n" "$fallback"\n'
        '}\n'
    )


def remote_ytdlp_preamble(host, ytdlp_snippet):
    if is_cookieless_host(host):
        return (
            'set -euo pipefail\n'
            'export PATH=/usr/local/bin:/usr/bin:$PATH\n'
            'YTDLP=$(command -v yt-dlp || true)\n'
            '[ -n "$YTDLP" ]\n'
        )
    return (
        'set -euo pipefail\n'
        'export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH\n'
        + ytdlp_snippet
    )


def cookie_jars(host):
    # Linux fetch hosts have no Safari/Chrome cookie jars; try cookieless.
    if is_cookieless_host(host):
        return ['NONE']
    return ['safari', 'chrome', 'NONE']


def cleanup_remote(host, remote_path):
    if not host or not remote_path:
        return
    subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', host,
         'rm', '-f', remote_path],
        capture_output=True, text=True)


def looks_like_bot_block(err):
    s = (err or '').lower()
    return any(tok in s for tok in (
        'sign in to confirm', 'not a bot', 'confirm you’re not a bot',
        "confirm you're not a bot", 'use --cookies',
    ))


def ytdlp_local_run(args, url):
    cmd = [local_ytdlp(), '--no-update', '--no-warnings', '--no-progress'] + list(args) + [url]
    return subprocess.run(cmd, capture_output=True, text=True)


def move_or_copy(src, dest):
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dest):
        return dest
    try:
        os.replace(src, dest)
    except OSError:
        shutil.copy2(src, dest)
        try:
            os.remove(src)
        except OSError:
            pass
    return dest


def find_local_download(rid, youtube_m4a):
    if youtube_m4a and os.path.exists(youtube_m4a) and os.path.getsize(youtube_m4a) > 1000:
        return youtube_m4a
    hits = [p for p in glob.glob(os.path.join(LOCAL_DL, rid + '.*'))
            if os.path.isfile(p) and os.path.getsize(p) > 1000]
    if hits:
        return max(hits, key=os.path.getsize)
    return None


def ytdlp_local_download(url, dest, ensure_m4a, is_youtube_url):
    """Download url with the box yt-dlp into dest."""
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    os.makedirs(LOCAL_DL, exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    rid = os.path.splitext(os.path.basename(dest))[0]
    youtube = is_youtube_url(url)
    if youtube:
        out_tmpl = os.path.join(LOCAL_DL, rid + '.m4a')
        fmt = 'ba[ext=m4a]/bestaudio/140'
    else:
        out_tmpl = os.path.join(LOCAL_DL, rid + '.%(ext)s')
        fmt = 'bestaudio/best'
    existing = find_local_download(rid, out_tmpl if youtube else None)
    if existing:
        print(f'fetch via box (reuse) {url}', flush=True)
        return ensure_m4a(existing, dest)
    extras_base = ['-f', fmt, '-o', out_tmpl]
    profile = chrome_profile()
    cookie_attempts = [None]
    last_err = ''
    print(f'fetch via box {url}', flush=True)
    i = 0
    while i < len(cookie_attempts):
        cookies = cookie_attempts[i]
        i += 1
        extra = list(extras_base)
        if cookies:
            extra = ['--cookies-from-browser', cookies] + extra
        r = ytdlp_local_run(extra, url)
        found = find_local_download(rid, out_tmpl if youtube else None)
        if r.returncode == 0 and found:
            return ensure_m4a(found, dest)
        last_err = (r.stderr or r.stdout or '')[-400:]
        if _should_try_cookies(last_err, profile, cookies, cookie_attempts):
            cookie_attempts.append(f'chrome:{profile}')
            continue
        if r.returncode and not looks_like_bot_block(last_err):
            break
    raise RuntimeError(f'local download failed for {url}: {last_err}')


def _should_try_cookies(err, profile, cookies, attempts):
    if not profile or cookies or any(a for a in attempts if a):
        return False
    return looks_like_bot_block(err)


def ytdlp_local_meta(url):
    print(f'fetch meta via box {url}', flush=True)
    r = ytdlp_local_run(['--skip-download', '--dump-json'], url)
    if r.returncode:
        err = (r.stderr or r.stdout or '')[-300:]
        profile = chrome_profile()
        if profile and looks_like_bot_block(err):
            r = ytdlp_local_run(
                ['--cookies-from-browser', f'chrome:{profile}', '--skip-download', '--dump-json'],
                url)
        if r.returncode:
            raise RuntimeError(f'local meta failed for {url}: {(r.stderr or "")[-300:]}')
    raw = r.stdout[r.stdout.find('{'):]
    info = json.loads(raw)
    ch = info.get('chapters') or []
    return dict(id=info.get('id'), title=info.get('title'),
                channel=info.get('channel') or info.get('uploader'),
                duration=info.get('duration'),
                chapters=[dict(start=c.get('start_time'), title=c.get('title')) for c in ch],
                description=(info.get('description') or '')[:12000],
                webpage_url=info.get('webpage_url') or url)


def ytdlp_search_local(query, n, prefix, parse_search_line):
    q = f'{prefix}{int(n)}:{query}'
    print_fmt = '%(id)s\t%(title)s\t%(channel,uploader|)s\t%(duration)s\t%(webpage_url,url|)s\t%(extractor|)s'
    print(f'fetch search via box {q}', flush=True)
    r = ytdlp_local_run(['--flat-playlist', '--skip-download', '--print', print_fmt], q)
    if r.returncode:
        raise RuntimeError(f'local search failed for {query}: {(r.stderr or "")[-300:]}')
    out = []
    for line in (r.stdout or '').splitlines():
        hit = parse_search_line(line)
        if hit:
            out.append(hit)
    return out


def parse_flat_lines(stdout, watch_url=None):
    out = []
    for line in (stdout or '').splitlines():
        if '\\t' in line and '\t' not in line:
            line = line.replace('\\t', '\t')
        if '\t' not in line:
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        dur = parts[2].strip() if len(parts) > 2 else ''
        try:
            duration = float(dur) if dur not in ('', 'NA', 'None') else None
        except ValueError:
            duration = None
        url = (parts[4].strip() if len(parts) > 4 else '') or None
        if not url and watch_url:
            url = watch_url(parts[0].strip())
        out.append(dict(id=parts[0].strip(), title=parts[1].strip(),
                        duration=duration,
                        channel=parts[3].strip() if len(parts) > 3 else '',
                        url=url))
    return out


def ytdlp_flat_local(url, limit=None, watch_url=None):
    args = ['--flat-playlist', '--skip-download']
    if limit:
        args.extend(['--playlist-end', str(int(limit))])
    args.extend(['--print', '%(id)s\t%(title)s\t%(duration)s\t%(channel)s\t%(webpage_url)s'])
    print(f'fetch flat via box {url}', flush=True)
    r = ytdlp_local_run(args, url)
    if r.returncode:
        raise RuntimeError(f'local flat list failed for {url}: {(r.stderr or "")[-300:]}')
    return parse_flat_lines(r.stdout, watch_url=watch_url)

def ytdlp_via(host, url, dest, rid, youtube, ytdlp_snippet, scp_from_host, ensure_m4a):
    """Download url on host into a writable dir, copy back to dest, drop the remote copy."""
    import shlex
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    preamble = remote_ytdlp_preamble(host, ytdlp_snippet)
    choose = choose_dl_dir_snippet()
    fmt = 'ba[ext=m4a]/bestaudio/140' if youtube else 'bestaudio/best'
    jar_lines = []
    for jar in cookie_jars(host):
        if jar == 'NONE':
            jar_lines.append(
                '  if $YTDLP --no-update -f "$FMT" -o "$OUT" --no-progress --no-warnings "$URL"; then ok=1; break; fi'
            )
        else:
            jar_lines.append(
                '  if $YTDLP --no-update --cookies-from-browser %s -f "$FMT" -o "$OUT" --no-progress --no-warnings "$URL"; then ok=1; break; fi'
                % shlex.quote(jar)
            )
    if youtube:
        out_lines = [
            'OUT="$DL/%s.m4a"' % rid,
            "if [ -s \"$OUT\" ]; then echo \"$OUT\"; ls -l \"$OUT\" | awk '{print $5}'; exit 0; fi",
        ]
        found_line = 'found="$OUT"'
    else:
        out_lines = [
            'BASE="$DL/%s"' % rid,
            'OUT="$BASE.%(ext)s"',
            'existing=$(ls -1 "$BASE".* 2>/dev/null | head -n 1 || true)',
            "if [ -n \"$existing\" ] && [ -s \"$existing\" ]; then echo \"$existing\"; ls -l \"$existing\" | awk '{print $5}'; exit 0; fi",
        ]
        found_line = 'found=$(ls -1 "$BASE".* 2>/dev/null | head -n 1 || true)'
    parts = [
        'URL=' + shlex.quote(url),
        'FMT=' + shlex.quote(fmt),
        'DL=$(choose_dl_dir)',
        *out_lines,
        'ok=0',
        *jar_lines,
        found_line,
        '[ "$ok" = 1 ] && [ -n "$found" ] && [ -s "$found" ]',
        'echo "$found"',
        "ls -l \"$found\" | awk '{print $5}'",
    ]
    script = preamble + choose + '\n'.join(parts) + '\n'
    print('fetch via %s %s' % (host, url), flush=True)
    r = ssh_bash(host, script, timeout=90)
    if r.returncode:
        raise RuntimeError('download failed for %s via %s: %s' % (url, host, (r.stderr or r.stdout)[-400:]))
    remote_path = None
    suffixes = ('.m4a', '.mp3', '.opus', '.ogg', '.webm', '.m4b', '.wav', '.aac', '.mp4')
    for line in (r.stdout or '').splitlines():
        line = line.strip()
        if line.startswith('/') and ('/protrans_dl' in line or line.endswith(suffixes)):
            remote_path = line
    if not remote_path:
        raise RuntimeError('download succeeded but no remote path printed for %s: %s' % (url, (r.stdout or '')[-200:]))
    try:
        if youtube and remote_path.endswith('.m4a'):
            scp_from_host(host, remote_path, dest)
            return dest
        ext = os.path.splitext(remote_path)[1] or '.bin'
        tmp = dest + '.dl' + ext
        scp_from_host(host, remote_path, tmp)
        return ensure_m4a(tmp, dest)
    finally:
        cleanup_remote(host, remote_path)
