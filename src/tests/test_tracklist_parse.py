"""Official Artist - Title parser: real Hospital Podcast junk vs official lists."""
from __future__ import annotations
import json
import os
import sys

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(HERE, 'protrans'))
import tracklist_parse as TP

# Real chapter labels that were ingested as "tracks" in the first corpus-v2 run.
JUNK_CHAPTERS = [
    'Politics', 'Cmon Cookies', 'Nostalgia', 'Drum and bass favorites',
    'Etherwood and chat debate', 'Introduction and new music',
    'Music showcase and shoutouts', 'Ingredients label spotlight',
    'Halloween events recap', 'Hospitality events 2015',
    'Tour dates and lineup', 'Pioneer mixer demonstration',
    'Podcast feedback and future', 'Wrap up', 'Setting the vibe',
    'Who is George', 'Im oscillating', 'Boris Johnson',
    'Listener weekend stories', 'The drum and bass community',
]

OFFICIAL_LINES = [
    'Etherwood - Driving Out',
    'Bop x Subwave - Take It Off',
    'Camo & Krooked - Loa',
    'Hugh Hardie & Unglued - Resistance',
    'Inja x Whiney - She Just Wanna Dance (Kyrist Remix)',
    'Fred V - Cosmic Flowchart',
    "S.P.Y - Don't You Leave Me (Dead Man's Chest Remix)",
    'Grafix - Radiance',
    '1. Gridlok - Here to Wherever',
    'Logistics – Lotus Flower',  # en-dash
    'Etherwood – Bear’s Breeches (feat Anile)',
    'goddard. & Greentea Peng – Downers (Rework)',
    '0:00 Fred V & Grafix - Find My Way',
    '1:07:18 LSB - I Need Love',
]

NOT_TITLES = [
    'Subscribe to Hospital on YouTube and tune in - http://www.youtube.com/hospitalrecords',
    'For pre-show news follow @londonelek on twitter - https://twitter.com/#!/londonelek',
    'Tracklist:',
    'Podcast Tracklist:',
    'Intro',
    'Shouts',
]


def test_junk_chapter_labels_are_not_artist_title():
    for s in JUNK_CHAPTERS:
        assert not TP.is_artist_title(s), s


def test_official_artist_title_lines_are_accepted():
    for s in OFFICIAL_LINES:
        assert TP.is_artist_title(s), s
        row = TP.parse_artist_title_line(s)
        assert ' - ' in row['title']
        assert row['artist'] and row['track']
    timed = TP.parse_artist_title_line('0:00 Fred V & Grafix - Find My Way')
    assert timed['t'] == 0
    assert timed['title'] == 'Fred V & Grafix - Find My Way'
    late = TP.parse_artist_title_line('1:07:18 LSB - I Need Love')
    assert late['t'] == 1 * 3600 + 7 * 60 + 18


def test_urls_and_headers_rejected():
    for s in NOT_TITLES:
        assert not TP.is_artist_title(s), s


def _meta(vid):
    p = os.path.join(HERE, 'protrans', 'corpus_v2', 'meta_cache', vid + '.json')
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def test_hp393_uses_description_titles_not_cmon_cookies():
    m = _meta('2wXDFi2eL1U')
    if not m:
        return
    rows = TP.parse_official_tracklist(m.get('description') or '', m.get('chapters'), min_tracks=8)
    titles = [r['title'] for r in rows]
    assert 'Cmon Cookies' not in titles and 'Nostalgia' not in titles
    assert any('She Just Wanna Dance' in t and 'Inja' in t for t in titles)
    assert any("Don't You Leave Me" in t and 'S.P.Y' in t for t in titles)
    assert any('Cosmic Flowchart' in t and 'Fred V' in t for t in titles)
    assert all(r.get('t') is not None for r in rows)
    assert len(rows) >= 8


def test_talk_show_chapters_without_official_list_yield_nothing():
    # HP400 has no description tracklist; chapters are 'Politics', 'Music', ...
    m = _meta('az6BZJAQCGo')
    if not m:
        return
    rows = TP.parse_official_tracklist(m.get('description') or '', m.get('chapters'), min_tracks=8)
    assert rows == []
    assert not any(TP.is_artist_title(c.get('title') or '') for c in (m.get('chapters') or []))


def test_hp356_binds_lotus_flower_to_logistics_not_bare_title():
    m = _meta('7OC4GdybCyY')
    if not m:
        return
    rows = TP.parse_official_tracklist(m.get('description') or '', m.get('chapters'), min_tracks=8)
    # If alignment can't confidently time 8 official titles, we must not
    # fall back to bare chapter names like 'Own Leaf' / 'Titles'.
    titles = [r['title'] for r in rows]
    assert 'Own Leaf' not in titles and 'Titles' not in titles
    assert 'What You Say' not in titles  # official is "Fliwo - What U Say"
    if rows:
        assert any('Lotus Flower' in t and 'Logistics' in t for t in titles)
        assert any("Breeches" in t and 'Etherwood' in t for t in titles)
        assert all(' - ' in t for t in titles)
        assert len(rows) >= 8


def test_timestamped_description_block():
    desc = """KushSessions tracklist
0:00 Echomatics - How It Used to Be
4:25 Blean & Bloque - In This Moment
7:44 Sereni7 & Kate Clark - Run To Me
11:25 Hybrid Minds - Bored
14:10 Monrroe - Days Like These V.I.P.
19:00 Outer Bass - My Heart (Instrumental)
20:50 Phloem - Variegate
24:09 Maykors & Duoscience - Equilibrium
"""
    rows = TP.tracks_for_mix(desc, None, min_tracks=8)
    assert len(rows) == 8
    assert rows[0] == dict(t=0.0, title='Echomatics - How It Used to Be')
    assert rows[3]['title'] == 'Hybrid Minds - Bored'


def test_leading_timestamp_in_title_is_stripped():
    row = TP.parse_artist_title_line('[0:00] Logistics - Watching The World Go By')
    assert row['artist'] == 'Logistics'
    assert row['title'] == 'Logistics - Watching The World Go By'
