"""Official Artist - Title tracklists for corpus_v2.

YouTube chapters on talk-heavy podcasts are often segment labels
('Politics', 'Introduction and new music'), not tracks. Prefer a
description (or official Tracklist: block) of 'Artist - Title' lines,
and only keep a row when it has both that shape and a timestamp.
Chapter times may be bound to official titles when they clearly line
up; chapters that are not themselves Artist - Title are never used
alone.
"""
from __future__ import annotations

import re
import unicodedata

# Optional leading timestamp and/or a numbered prefix, then Artist - Title.
_LINE = re.compile(
    r"""
    ^\s*
    (?:
        (?:[#]?\s*)?(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?
        \s+[-–.]?\s*
    )?
    (?:(?P<num>\d{1,3})[.)]\s+)?
    (?P<body>.+?)\s*$
    """,
    re.VERBOSE,
)

_SPLIT = re.compile(r'\s+[-–—]\s+')

_BAD_LINE = re.compile(
    r'https?://|www\.|subscribe|follow (us|me|hospital|on)|'
    r'tune in|pre-show|twitter\.|instagram\.|facebook\.|'
    r'click here|leave a comment',
    re.I,
)
_BAD_SIDE = re.compile(
    r'^(tracklist|timestamps|podcast tracklist|follow|subscribe|'
    r'introduction|intro|outro|shoutouts?|wrap up|welcome)$',
    re.I,
)

# Chapter / segment labels that must not be treated as track titles.
_SEGMENTISH = re.compile(
    r'\b(introduction|intro|outro|shoutouts?|wrap up|welcome|'
    r'interview|feedback|recap|preview|news|chat|debate|'
    r'spotlight|demonstration|tour dates|lineup|set up|setup|'
    r'listener|weekend stories|goodbyes?|origins of)\b',
    re.I,
)


def _norm(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = s.replace('–', '-').replace('—', '-').replace('’', "'").replace('‘', "'")
    s = s.replace("'", '')  # Bear's / Bears
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _letters(s):
    return sum(ch.isalpha() for ch in s)


def is_artist_title(text):
    """True when text is an 'Artist - Title' (optionally numbered / timestamped)."""
    import fetch
    text = fetch.normalize_track_title(text, strip_timestamps=False)
    if not text or _BAD_LINE.search(text):
        return False
    m = _LINE.match(text.strip())
    if not m:
        return False
    body = fetch.normalize_track_title(m.group('body') or '')
    parts = _SPLIT.split(body, maxsplit=1)
    if len(parts) != 2:
        return False
    artist, title = parts[0].strip(' -–—.'), parts[1].strip(' -–—.')
    if not artist or not title:
        return False
    if _BAD_SIDE.match(artist) or _BAD_SIDE.match(title):
        return False
    if _letters(artist) < 2 or _letters(title) < 2:
        return False
    if len(artist) > 80 or len(title) > 160:
        return False
    # Sentences like "Subscribe to Hospital on YouTube and tune in - http://..."
    if artist.lower().startswith(('subscribe', 'follow', 'thanks', 'video by',
                                  'for pre-show', 'make sure')):
        return False
    # Artist is a name, not a clause: allow '&', 'x', 'feat.', but not a long sentence.
    words = artist.split()
    if len(words) > 8:
        return False
    return True


def parse_artist_title_line(text):
    """Return {t, title} if the line is Artist - Title. t is None when untimed."""
    import fetch
    raw = text
    text = fetch.normalize_track_title(text, strip_timestamps=False)
    if not is_artist_title(text):
        return None
    m = _LINE.match(text.strip())
    body = fetch.normalize_track_title(m.group('body') or '')
    parts = _SPLIT.split(body, maxsplit=1)
    artist, title = parts[0].strip(), parts[1].strip()
    artist = re.sub(r'^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*', '', artist)
    title = re.sub(r'^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*', '', title)
    full = f'{artist} - {title}'
    t = None
    if m.group('h') is not None:
        h, mm = int(m.group('h')), int(m.group('m'))
        if m.group('s') is None:
            # MM:SS or H:MM (ambiguous). Prefer MM:SS when first field <= 59
            # and no third group; H:MM:SS already has s.
            t = float(h * 60 + mm)
        else:
            t = float(h * 3600 + mm * 60 + int(m.group('s')))
    return dict(t=t, title=full, artist=artist, track=title, raw=(raw or text).strip())


def parse_description_titles(description):
    """Official titles from a description, preferring a Tracklist: block."""
    if not description:
        return []
    lines = description.splitlines()
    # Prefer an explicit tracklist section when present.
    block_at = None
    for i, ln in enumerate(lines):
        if re.match(r'^\s*(podcast\s+)?tracklist\s*:?\s*$', ln, re.I):
            block_at = i + 1
            break
    chunks = []
    if block_at is not None:
        block = []
        for ln in lines[block_at:]:
            if re.match(r'^\s*(-{3,}|follow\s+\w+|http)', ln, re.I):
                break
            if not ln.strip():
                # allow a single blank inside a list; stop on a second gap after items
                if block:
                    break
                continue
            block.append(ln)
        chunks.append(block)
    chunks.append(lines)
    for chunk in chunks:
        items = []
        for ln in chunk:
            row = parse_artist_title_line(ln)
            if row:
                items.append(row)
        # de-dupe by normalised title, keep order
        seen, out = set(), []
        for it in items:
            k = _norm(it['title']).lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        if len(out) >= 4:
            return out
    return out if 'out' in dir() else []


def parse_chapter_titles(chapters):
    """Chapters that are themselves Artist - Title, with their start times."""
    out = []
    for c in chapters or []:
        if c.get('start') is None:
            continue
        raw = c.get('title') or ''
        row = parse_artist_title_line(raw)
        if not row:
            continue
        row['t'] = float(c['start'])
        out.append(row)
    return out


def _tokens(s):
    s = _norm(s).lower()
    s = re.sub(r'[^a-z0-9&+]+', ' ', s)
    stop = {'the', 'and', 'feat', 'ft', 'featuring', 'with', 'a', 'of', 'to', 'remix', 'vip', 'edit'}
    return [w for w in s.split() if len(w) > 1 and w not in stop]


def _fuzzy(chapter_title, official_title):
    """0-1 overlap of chapter words against an official Artist - Title."""
    a = _tokens(chapter_title)
    b = _tokens(official_title)
    if not a or not b:
        return 0.0
    # Reject obvious segment labels even if a word overlaps ('new music').
    if _SEGMENTISH.search(chapter_title) and len(a) <= 6:
        return 0.0
    hit = sum(1 for w in a if w in b)
    # also accept when the chapter is a substantial substring of the title
    cn, on = _norm(chapter_title).lower(), _norm(official_title).lower()
    if len(cn) >= 4 and cn in on:
        return max(hit / len(a), 0.85)
    return hit / len(a)


def align_titles_to_chapters(titles, chapters, min_score=0.6):
    """Bind official Artist - Title rows to chapter timestamps.

    Only emits a row when the official title is Artist - Title and a
    chapter time can be assigned. Gap-fill is allowed only when the
    number of leftover chapters in a span equals the number of leftover
    official titles (a 1:1 cue run between two confident anchors).
    """
    if not titles or not chapters:
        return []
    ch = [c for c in chapters if c.get('start') is not None]
    ch = sorted(ch, key=lambda c: float(c['start']))
    # greedy monotonic matching
    used_t = set()
    used_c = set()
    anchors = []  # (title_idx, chapter_idx, score)
    c_i = 0
    for ti, title in enumerate(titles):
        best = None
        for cj in range(c_i, len(ch)):
            if cj in used_c:
                continue
            sc = _fuzzy(ch[cj].get('title') or '', title['title'])
            if sc >= min_score and (best is None or sc > best[0]):
                best = (sc, cj)
        if best:
            anchors.append((ti, best[1], best[0]))
            used_t.add(ti)
            used_c.add(best[1])
            c_i = best[1] + 1
    if len(anchors) < 2 and not (len(anchors) >= 1 and len(titles) == len(ch)):
        # not enough evidence that chapters are track cues
        assigned = {ti: ch[cj] for ti, cj, _ in anchors}
        return _rows_from_assigned(titles, assigned)
    # gap-fill 1:1 between anchors, and at the head if counts match
    assigned = {ti: ch[cj] for ti, cj, _ in anchors}
    # head
    if anchors:
        t0, c0, _ = anchors[0]
        if t0 > 0 and c0 == t0:
            for i in range(t0):
                assigned[i] = ch[i]
        # between anchors
        for (t_a, c_a, _), (t_b, c_b, _) in zip(anchors, anchors[1:]):
            n_t, n_c = t_b - t_a - 1, c_b - c_a - 1
            if n_t == n_c and n_t > 0:
                for k in range(1, n_t + 1):
                    assigned[t_a + k] = ch[c_a + k]
        # tail if leftover chapters == leftover titles
        t_last, c_last, _ = anchors[-1]
        n_t, n_c = len(titles) - t_last - 1, len(ch) - c_last - 1
        if n_t == n_c and n_t > 0:
            for k in range(1, n_t + 1):
                assigned[t_last + k] = ch[c_last + k]
    return _rows_from_assigned(titles, assigned)


def _rows_from_assigned(titles, assigned):
    out = []
    for ti, title in enumerate(titles):
        ch = assigned.get(ti)
        if not ch:
            continue
        row = dict(title)
        row['t'] = float(ch['start'])
        row['time_source'] = 'chapter_aligned'
        row['chapter_title'] = ch.get('title')
        out.append(row)
    return out


def parse_official_tracklist(description, chapters=None, min_tracks=8):
    """Preferred official tracklist: timed Artist - Title rows, or [].

    Order: timestamped description lines, then official titles aligned
    to chapter times, then chapters that are themselves Artist - Title.
    """
    desc_rows = parse_description_titles(description)
    timed_desc = [r for r in desc_rows if r.get('t') is not None]
    if len(timed_desc) >= min_tracks:
        for r in timed_desc:
            r['time_source'] = 'description'
        return timed_desc

    aligned = align_titles_to_chapters(desc_rows, chapters or [])
    if len(aligned) >= min_tracks:
        return aligned

    chapter_rows = parse_chapter_titles(chapters or [])
    if len(chapter_rows) >= min_tracks:
        for r in chapter_rows:
            r['time_source'] = 'chapter_artist_title'
        return chapter_rows

    # Not enough official timed rows. Return the best short list only
    # when the caller wants to inspect; the corpus requires min_tracks.
    return []


def tracks_for_mix(description, chapters=None, min_tracks=8):
    """List of {t, title} suitable for goldilocks pairing, or []."""
    rows = parse_official_tracklist(description, chapters, min_tracks=min_tracks)
    # unique increasing times
    seen, out = set(), []
    for r in rows:
        if r.get('t') is None:
            continue
        k = round(float(r['t']), 2)
        if k in seen:
            continue
        seen.add(k)
        out.append(dict(t=float(r['t']), title=r['title']))
    out.sort(key=lambda x: x['t'])
    return out
