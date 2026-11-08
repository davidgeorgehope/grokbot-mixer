"""Live-build acceptance gates run before cleanup, never as default regressions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src2'))
import json, pytest, checks
from release_selection import selected_build

@pytest.fixture(autouse=True)
def explicit_release():
    selected_build()

@pytest.fixture(scope='session')
def T():
    selected_build()
    rows=checks.transitions()
    Path(checks.SRC, checks.NAME+'_qa_report.json').write_text(json.dumps(rows,indent=1))
    return rows
