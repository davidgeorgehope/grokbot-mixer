"""Run cleanup.drop_stems only when render-mix10-r6e, like1124-rescore, and
corpus-v2 are not using /tmp/protrans* scratch. Polls status files. Does not
write rules.json.
"""
from __future__ import annotations
import os, time, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanup

JOBS = '/workspace/mixes/jobs'
WAIT = [
    'render-mix10-r6e',
    'like1124-rescore',
]
# corpus-v2 may run for days; only block if it actually has files open under /tmp/protrans
CORPUS = 'corpus-v2'

def status(name):
    p = os.path.join(JOBS, name + '.status')
    if not os.path.exists(p):
        return 'missing'
    return open(p).read().strip()

def running(name):
    return status(name).startswith('running')

def corpus_uses_scratch():
    # walk /proc for the corpus python and see cwd/open fds mentioning /tmp/protrans
    try:
        import subprocess
        out = subprocess.check_output(['ps', '-eo', 'pid,cmd'], text=True)
    except Exception:
        return False
    pids = []
    for line in out.splitlines():
        if 'run_corpus_v2.py' in line and 'rg' not in line:
            pids.append(line.split(None, 1)[0])
    for pid in pids:
        try:
            # fd and maps; avoid dumping env
            fds = os.listdir(f'/proc/{pid}/fd')
            for fd in fds:
                try:
                    t = os.readlink(f'/proc/{pid}/fd/{fd}')
                except OSError:
                    continue
                if '/tmp/protrans' in t:
                    return True
        except OSError:
            continue
    return False

def main():
    print('drop_stems watcher starting', flush=True)
    while True:
        busy = [n for n in WAIT if running(n)]
        corpus_busy = running(CORPUS) and corpus_uses_scratch()
        if busy or corpus_busy:
            print(f'waiting: jobs={busy or "ok"} corpus_scratch={corpus_busy} {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
            time.sleep(60)
            continue
        print('scratch free; running drop_stems', flush=True)
        cleanup.drop_stems()
        left = glob.glob('/tmp/protrans*')
        print('drop_stems done; remaining /tmp/protrans*', left, flush=True)
        return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
