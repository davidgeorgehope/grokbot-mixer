"""Release QA requires a real explicitly selected build, never an archival default."""
import os, json
from pathlib import Path
import checks

def selected_build():
    assert os.environ.get('MIX_NAME'), 'release QA requires explicit MIX_NAME'
    meta=Path(checks.SRC, checks.NAME+'_meta.json')
    assert meta.is_file(), 'selected build meta missing'
    assert Path(checks.WAV).is_file(), 'selected build WAV missing'
    assert Path(checks.MP3).is_file(), 'selected build MP3 missing'
    for deck in json.loads(meta.read_text())['decks']:
        stem=Path(checks.SRC, 'st', deck['id']+'.wav')
        assert stem.is_file(), f'selected build source missing: {stem}'
