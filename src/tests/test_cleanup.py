"""Auto-cleanup (the listener 2026-10-31): cleanup only removes regenerable audio, and everything it removes can be regenerated."""
import os,subprocess,sys
SRC2=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','src2');SH=os.path.join(SRC2,'..','src','cleanup_after_build.sh')
def _dry():return subprocess.run(['bash',SH,'--dry'],capture_output=True,text=True,check=True).stdout.split()
def test_cleanup_only_targets_regenerable_audio():
  for f in _dry():
    assert f.endswith(('.wav','.mp3')),f
    assert not f.endswith(('.m4a','.flac','.json','.npy','.npz')),f
    if f.endswith('.mp3'):assert os.path.basename(f).startswith('tmp_'),f
def test_every_stem_has_a_source_or_is_kept():
  keep=set(open(os.path.join(SRC2,'st','KEEP_STEMS.txt')).read().split()) if os.path.exists(os.path.join(SRC2,'st','KEEP_STEMS.txt')) else set()
  ids=[f[:-5] for f in os.listdir(os.path.join(SRC2,'st')) if f.endswith('.json')]
  missing=[b for b in ids if os.path.exists(os.path.join(SRC2,'st',b+'.wav')) and b not in keep and not any(os.path.exists(os.path.join(SRC2,f'{b}.{e}')) for e in('m4a','flac'))]
  assert not missing,missing
def test_pipeline_restores_then_cleans():
  s=open(os.path.join(SRC2,'..','src','render_and_test.sh')).read()
  assert s.index('restore_audio.py')<s.index('mix_simple.py --plan')<s.index('cleanup_after_build.sh')
