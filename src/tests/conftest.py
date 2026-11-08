import json,pytest,checks
@pytest.fixture(scope='session')
def T(): 
  import os
  if not os.environ.get('MIX_NAME'):pytest.skip('integration QA needs explicit MIX_NAME')
  t=checks.transitions();open(f'{checks.SRC}/{checks.NAME}_qa_report.json','w').write(json.dumps(t,indent=1))
  return t
def pytest_terminal_summary(terminalreporter):
  import os
  if not os.environ.get('MIX_NAME'):return
  try:
    terminalreporter.write_line('\nPER-TRANSITION REPORT');
    for r in json.load(open(f'{checks.SRC}/{checks.NAME}_qa_report.json')):terminalreporter.write_line(str(r))
  except Exception as e:terminalreporter.write_line(f'(no report: {e})')

# Build QA is meaningful only for an explicitly selected render. Never silently
# judge the stale mixS metadata when running the unit/regression suite.
BUILD_MODULES = {'test_mix', 'test_mix02_traits', 'test_guardrails', 'test_ears',
                 'test_ears_gate', 'test_crossfader', 'test_eq_swap', 'test_echo_out',
                 'test_structure_tail', 'test_variety'}

@pytest.fixture(autouse=True)
def selected_build(request):
  import os
  if request.module.__name__.split('.')[-1] not in BUILD_MODULES:
    return
  if not os.environ.get('MIX_NAME'):
    pytest.skip('integration QA needs an explicit MIX_NAME; no build selected')
  # An explicit build is a release gate: absent fixtures MUST fail, not skip.
  assert os.path.isfile(f'{checks.SRC}/{checks.NAME}_meta.json'), 'selected build meta missing'


def require_fixtures(*paths):
  import os
  missing = [str(p) for p in paths if not os.path.isfile(p)]
  if missing:
    pytest.skip('archival fixture missing: ' + ', '.join(missing))
