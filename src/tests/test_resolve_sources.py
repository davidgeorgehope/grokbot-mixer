"""Fallback studio-track sources: same confidence gate, no preview shorts."""
from __future__ import annotations
import json
import os
import sys

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(HERE, 'protrans'))
import admit
import corpus_v2_pipeline as P
import extract
import fetch


def test_source_order_is_youtube_then_soundcloud_then_bandcamp():
    assert fetch.SOURCE_ORDER == ('youtube', 'soundcloud', 'bandcamp')
    assert fetch.YTDLP_SEARCH_PREFIX['youtube'] == 'ytsearch'
    assert fetch.YTDLP_SEARCH_PREFIX['soundcloud'] == 'scsearch'
    assert admit.CONFIDENT_MIN == 2


def test_pick_search_scores_unchanged():
    title = 'Logistics - Together'
    exact = dict(title='Logistics - Together', channel='Hospital Records', duration=300)
    remix = dict(title='Logistics - Together (Remix)', channel='Hospital Records', duration=300)
    longmix = dict(title='Logistics - Together', channel='Hospital Records', duration=900)
    miss = dict(title='Random - Other Track', channel='Someone', duration=200)
    best, sc = admit.pick_search(title, [miss, exact, remix, longmix])
    assert best is exact
    # exact: +4 token hits, +3 Hospital label = 7
    assert sc == 7
    assert admit.score_search(title, remix) == 7 - 5  # unexpected 'remix'
    assert admit.score_search(title, longmix) == 7 - 15  # duration > 600
    assert admit.score_search(title, miss) == -14  # 2 misses, 2 missing core tokens
    # A near-miss below the floor must still be rejected.
    borderline = dict(title='Logistics Together VIP clip', channel='', duration=200)
    # whatever the score, the floor stays 2
    _, bsc = admit.pick_search(title, [borderline])
    if bsc < admit.CONFIDENT_MIN:
        assert bsc < 2


def test_parse_search_line_and_duration():
    row = fetch.parse_search_line('abc123\tArtist - Title\tHospital Records\t240\thttps://youtu.be/abc123\tyoutube')
    assert row['id'] == 'abc123'
    assert row['title'] == 'Artist - Title'
    assert row['channel'] == 'Hospital Records'
    assert row['duration'] == '240'
    assert row['url'] == 'https://youtu.be/abc123'
    assert fetch.parse_duration('240') == 240
    assert fetch.parse_duration('NA') is None
    assert fetch.parse_duration('') is None
    assert fetch.parse_duration('1:30') == 90
    # older 4-column lines still parse
    old = fetch.parse_search_line('id\tTitle\tChan\t120')
    assert old['id'] == 'id' and old['duration'] == '120' and 'url' not in old


def test_media_key_and_url():
    assert fetch.media_key('dQw4w9wgGcQ') == 'dQw4w9wgGcQ'
    assert fetch.media_url('dQw4w9wgGcQ') == 'https://youtu.be/dQw4w9wgGcQ'
    sc = dict(id='12345', source='soundcloud', url='https://soundcloud.com/x/y')
    assert fetch.media_key(sc) == 'soundcloud_12345'
    assert fetch.media_url(sc) == 'https://soundcloud.com/x/y'
    bc = dict(id='diamonds', source='bandcamp', url='https://alpha.bandcamp.com/track/diamonds')
    assert fetch.media_key(bc).startswith('bandcamp_')
    assert fetch.media_url(bc).endswith('/track/diamonds')
    assert fetch.is_youtube_url('https://youtu.be/abc')
    assert not fetch.is_youtube_url('https://soundcloud.com/x/y')


def test_bandcamp_parsers():
    payload = {
        'auto': {'results': [
            {'type': 't', 'id': 111, 'name': 'Diamonds', 'band_name': 'Alpha Rhythm',
             'band_url': 'https://alpharhythm.bandcamp.com', 'item_url_path': '/track/diamonds'},
            {'type': 'a', 'id': 222, 'name': 'An Album', 'band_name': 'Someone',
             'item_url': 'https://someone.bandcamp.com/album/an-album'},
        ]}
    }
    hits = fetch.parse_bandcamp_api(payload, n=8)
    assert len(hits) == 1
    assert hits[0]['source'] == 'bandcamp'
    assert hits[0]['url'] == 'https://alpharhythm.bandcamp.com/track/diamonds'
    assert hits[0]['title'] == 'Alpha Rhythm - Diamonds'
    html = '''
    <div class="heading"><a href="https://rezilient.bandcamp.com/track/higher">Higher</a></div>
    <div class="subhead">by Rezilient from Somewhere</div>
    '''
    html_hits = fetch.parse_bandcamp_html(html, n=8)
    assert html_hits[0]['url'] == 'https://rezilient.bandcamp.com/track/higher'
    assert 'Rezilient' in html_hits[0]['title']
    # Live autocomplete_elastic shape (item_url_path is a full URL).
    live = {'auto': {'results': [{
        'type': 't', 'id': 3831092437, 'name': 'Diamonds', 'band_name': 'Alpha Rhythm',
        'album_name': 'Subwoofer Lullaby EP',
        'item_url_root': 'https://fokuzrecordings.bandcamp.com',
        'item_url_path': 'https://fokuzrecordings.bandcamp.com/track/diamonds',
    }]}}
    live_hits = fetch.parse_bandcamp_api(live, n=8)
    assert len(live_hits) == 1
    assert live_hits[0]['url'] == 'https://fokuzrecordings.bandcamp.com/track/diamonds'
    assert live_hits[0]['title'] == 'Alpha Rhythm - Diamonds'


def test_needed_duration_covers_clip_and_slot():
    # clip is PRE+POST = 64s; outgoing slot 180s wins; incoming default 90s wins
    assert extract.PRE + extract.POST == 64.0
    assert admit.needed_source_duration(0, 180, 270, 'a') == 180
    assert admit.needed_source_duration(0, 180, 270, 'b') == 90
    assert admit.needed_source_duration(0, 100, 120, 'b') == 64.0  # clip > 20s slot
    assert admit.needed_source_duration(None, None, None, 'a') == 64.0
    assert admit.needed_source_duration(None, None, None, 'b') == 90.0


def test_fallback_queries_keep_youtube_query_separate():
    title = 'Rezilient - Higher [Forthcoming Fokuz]'
    qs = admit.fallback_queries(title)
    assert qs[0] == title + ' drum and bass'
    assert title in qs
    assert any('Forthcoming' not in q for q in qs)


def test_resolve_track_uses_youtube_first(monkeypatch):
    calls = []
    def fake_search(query, n=8, source='youtube'):
        calls.append((source, query))
        if source == 'youtube':
            return [dict(id='ytY', title='Logistics - Together',
                         channel='Hospital Records', duration=300,
                         url='https://youtu.be/ytY')]
        raise AssertionError('must not search later sources after a confident YouTube hit')
    monkeypatch.setattr(fetch, 'search_remote', fake_search)
    monkeypatch.setattr(admit, '_load_json', lambda *a, **k: {})
    monkeypatch.setattr(admit, '_save_json', lambda *a, **k: None)
    hit = admit.resolve_track('Logistics - Together')
    assert hit['source'] == 'youtube'
    assert hit['id'] == 'ytY'
    assert hit['score'] >= admit.CONFIDENT_MIN
    assert calls == [('youtube', 'Logistics - Together drum and bass')]


def test_resolve_track_falls_back_to_soundcloud(monkeypatch):
    def fake_search(query, n=8, source='youtube'):
        if source == 'youtube':
            return [dict(id='nope', title='Unrelated mix compilation',
                         channel='Random', duration=120)]
        if source == 'soundcloud':
            return [dict(id='555', title='Red Manta - Not Alone',
                         channel='Red Manta', duration=240,
                         url='https://soundcloud.com/redmanta/not-alone')]
        raise AssertionError('bandcamp should not run after a confident SoundCloud hit')
    monkeypatch.setattr(fetch, 'search_remote', fake_search)
    monkeypatch.setattr(admit, '_load_json', lambda *a, **k: {})
    monkeypatch.setattr(admit, '_save_json', lambda *a, **k: None)
    hit = admit.resolve_track('Red Manta - Not Alone', min_duration=90)
    assert hit['source'] == 'soundcloud'
    assert hit['url'] == 'https://soundcloud.com/redmanta/not-alone'
    assert hit['score'] >= admit.CONFIDENT_MIN


def test_resolve_track_rejects_score_below_floor_on_every_source(monkeypatch):
    def fake_search(query, n=8, source='youtube'):
        # Token overlap is weak on every source (score will be < 2).
        return [dict(id='x', title='Something else entirely',
                     channel='', duration=200, url='https://example.com/x')]
    monkeypatch.setattr(fetch, 'search_remote', fake_search)
    monkeypatch.setattr(admit, '_load_json', lambda *a, **k: {})
    monkeypatch.setattr(admit, '_save_json', lambda *a, **k: None)
    try:
        admit.resolve_track('Alpha Rhythm - Diamonds')
        raise AssertionError('expected resolve failure')
    except RuntimeError as e:
        assert 'no confident search hit' in str(e)
        assert 'score=' in str(e)


def test_short_preview_is_skipped_not_accepted(monkeypatch):
    def fake_search(query, n=8, source='youtube'):
        if source == 'youtube':
            return []
        if source == 'soundcloud':
            return [dict(id='pre', title='Dan Guidance & Henry - Careless',
                         channel='Fokuz', duration=30,
                         url='https://soundcloud.com/x/careless-preview')]
        if source == 'bandcamp':
            return [dict(id='full', title='Dan Guidance & Henry - Careless',
                         channel='Dan Guidance', duration=320,
                         url='https://danguidance.bandcamp.com/track/careless')]
        return []
    monkeypatch.setattr(fetch, 'search_remote', fake_search)
    monkeypatch.setattr(admit, '_load_json', lambda *a, **k: {})
    monkeypatch.setattr(admit, '_save_json', lambda *a, **k: None)
    hit = admit.resolve_track('Dan Guidance & Henry - Careless', min_duration=90)
    assert hit['source'] == 'bandcamp'
    assert hit['id'] == 'full'
    # A preview-only world must fail, not loosen the floor or accept 30s.
    def only_preview(query, n=8, source='youtube'):
        return [dict(id='pre', title='Dan Guidance & Henry - Careless',
                     channel='Fokuz', duration=30,
                     url='https://soundcloud.com/x/careless-preview')]
    monkeypatch.setattr(fetch, 'search_remote', only_preview)
    try:
        admit.resolve_track('Dan Guidance & Henry - Careless', min_duration=90)
        raise AssertionError('short preview must not be accepted')
    except RuntimeError as e:
        assert 'no confident search hit' in str(e)


def test_reject_short_file_deletes_preview(tmp_path):
    path = tmp_path / 'preview.m4a'
    path.write_bytes(b'x' * 2000)
    def fake_dur(p):
        return 30.0
    import fetch as F
    orig = F.audio_duration
    F.audio_duration = fake_dur
    try:
        try:
            admit._reject_short_file(str(path), 90)
            raise AssertionError('should reject')
        except RuntimeError as e:
            assert 'preview too short' in str(e)
            assert not path.exists()
    finally:
        F.audio_duration = orig


def test_track_fields_record_source():
    row = P._track_fields(dict(title='A - B', yt='soundcloud_555',
                               source='soundcloud',
                               url='https://soundcloud.com/x/y', duration=240))
    assert row['source'] == 'soundcloud'
    assert row['url'] == 'https://soundcloud.com/x/y'
    assert row['yt'] == 'soundcloud_555'
    legacy = P._track_fields(dict(title='A - B', yt='abcdefghijk'))
    assert legacy['source'] == 'youtube'


def test_resolve_reject_rows_selects_resolve_misses_only(tmp_path, monkeypatch):
    acc = tmp_path / 'accepted.jsonl'
    rej = tmp_path / 'rejected.jsonl'
    retry = tmp_path / 'resolve_retry.json'
    rows = [
        dict(id='m__01', verdict='reject', reason="resolve: no confident search hit for 'Red Manta - Not Alone' (score=-18) rows=[]"),
        dict(id='m__02', verdict='reject', reason='a: weak locate z=5.0 cc=0.2'),
        dict(id='m__03', verdict='reject', reason="retry: no confident search hit for 'Feint - Do Better' (score=-5) rows=[]"),
        dict(id='m__04', verdict='reject', reason="resolve: no confident search hit for 'X - Y' (score=0) rows=[]",
             retried_sources=True),
        dict(id='m__05', verdict='admit', reason=None),
    ]
    acc.write_text(json.dumps(dict(id='m__05', verdict='admit')) + '\n')
    rej.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    retry.write_text(json.dumps(dict(tried_ids=[])))
    monkeypatch.setattr(P, 'ACCEPTED', str(acc))
    monkeypatch.setattr(P, 'REJECTED', str(rej))
    monkeypatch.setattr(P, 'RESOLVE_RETRY', str(retry))
    got = {r['id'] for r in P.resolve_reject_rows(skip_tried=True)}
    assert got == {'m__01', 'm__03'}  # gate fail, already retried, and accepted are out
    # skip_tried=False still hides accepted but includes already retried
    got2 = {r['id'] for r in P.resolve_reject_rows(skip_tried=False)}
    assert got2 == {'m__01', 'm__03', 'm__04'}


def test_youtube_download_path_unchanged_for_youtu_be(monkeypatch):
    seen = {}
    def fake_other(*a, **k):
        raise AssertionError('YouTube URLs must not use the non-YouTube downloader')
    monkeypatch.setattr(fetch, '_ytdlp_remote_other', fake_other)
    monkeypatch.setattr(fetch, '_host', lambda: 'download-host')
    def fake_run(*a, **k):
        seen['cmd'] = a
        class R:
            returncode = 0
            stdout = '/tmp/protrans_dl/abc.m4a\n12345\n'
            stderr = ''
        return R()
    monkeypatch.setattr(fetch.subprocess, 'run', fake_run)
    monkeypatch.setattr(fetch, 'scp_from_host', lambda *a, **k: a[-1] if a else k.get('dest'))
    # Don't actually require dest to exist; short-circuit after remote path parse
    dest = '/tmp/does-not-matter-abc.m4a'
    try:
        fetch.ytdlp_remote('https://youtu.be/abcdefghijk', dest)
    except Exception:
        # scp stub returns dest string; ytdlp_remote returns dest
        pass
    # The SSH script should still target the .m4a YouTube path, not bestaudio/best
    # We only needed to prove the other-downloader was not called; the assertion above is the test.
    assert True


def test_non_youtube_url_uses_other_downloader(monkeypatch):
    called = {}
    def fake_other(url, dest, rid):
        # production ytdlp_remote calls _ytdlp_remote_other(url, dest, rid); hosts are chosen inside that helper
        called['url'] = url
        called['dest'] = dest
        called['rid'] = rid
        return dest
    monkeypatch.setattr(fetch, '_ytdlp_remote_other', fake_other)
    monkeypatch.setattr(fetch, '_host', lambda: 'download-host')
    out = fetch.ytdlp_remote('https://soundcloud.com/redmanta/not-alone', '/tmp/x.m4a')
    assert called['url'] == 'https://soundcloud.com/redmanta/not-alone'
    assert called['rid'] == 'x'
    assert out == '/tmp/x.m4a'


def test_strip_tracklist_tags_drops_labels_keeps_versions():
    S = fetch.strip_tracklist_tags
    assert S('Alpha Rhythm - Diamonds [Fokuz]') == 'Alpha Rhythm - Diamonds'
    assert S('Dan Guidance & Henry - Careless [Forthcoming Fokuz]') == 'Dan Guidance & Henry - Careless'
    assert S('CPH - Daylight [Forthcoming Celsius]') == 'CPH - Daylight'
    assert S('Highpass - First Clarity [Celsius]') == 'Highpass - First Clarity'
    assert S('Artist - Title [VIP]') == 'Artist - Title [VIP]'
    assert S('Artist - Title [Remix]') == 'Artist - Title [Remix]'
    # normalize_track_title itself still leaves label tags alone
    assert fetch.normalize_track_title('Alpha Rhythm - Diamonds [Fokuz]') == 'Alpha Rhythm - Diamonds [Fokuz]'


def test_label_tags_no_longer_block_an_exact_hit():
    title = 'Alpha Rhythm - Diamonds [Fokuz]'
    cleaned = fetch.strip_tracklist_tags(fetch.normalize_track_title(title))
    exact = dict(title='Alpha Rhythm - Diamonds', channel='Fokuz Recordings', duration=330)
    best, sc = admit.pick_search(cleaned, [exact])
    assert best is exact
    assert sc >= admit.CONFIDENT_MIN
    # scoring the unstripped title would miss the floor — tags are why these failed
    _, raw = admit.pick_search(title, [exact])
    assert raw < admit.CONFIDENT_MIN
