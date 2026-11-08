"""No-build skips must never turn a selected release build green."""
from types import SimpleNamespace
import pytest
import release_selection as selection


def request_for_build():
    return SimpleNamespace()


def test_unselected_release_fails(monkeypatch):
    monkeypatch.delenv('MIX_NAME',raising=False)
    with pytest.raises(AssertionError, match='explicit MIX_NAME'):
        selection.selected_build()


def test_selected_missing_build_fails(monkeypatch,tmp_path):
    monkeypatch.setenv('MIX_NAME','required-release')
    monkeypatch.setattr(selection.checks,'SRC',str(tmp_path))
    monkeypatch.setattr(selection.checks,'NAME','required-release')
    with pytest.raises(AssertionError,match='selected build meta missing'):
        selection.selected_build()


@pytest.mark.parametrize('missing', ['WAV', 'MP3', 'source'])
def test_selected_release_missing_audio_fails(monkeypatch,tmp_path,missing):
    import json
    name='required-release'
    monkeypatch.setenv('MIX_NAME',name)
    monkeypatch.setattr(selection.checks,'SRC',str(tmp_path))
    monkeypatch.setattr(selection.checks,'NAME',name)
    (tmp_path/(name+'_meta.json')).write_text(json.dumps({'decks':[{'id':'source'}]}))
    (tmp_path/'st').mkdir()
    paths={'WAV':tmp_path/'master.wav','MP3':tmp_path/'master.mp3',
           'source':tmp_path/'st/source.wav'}
    for key,path in paths.items():
        if key in ('WAV','MP3'):monkeypatch.setattr(selection.checks,key,str(path))
        if key!=missing:path.write_bytes(b'exists')
    with pytest.raises(AssertionError,match='selected build .* missing'):
        selection.selected_build()
