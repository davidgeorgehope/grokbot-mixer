import json,pytest,checks
@pytest.fixture(scope='session')
def T(): 
  t=checks.transitions();open(f'{checks.SRC}/{checks.NAME}_qa_report.json','w').write(json.dumps(t,indent=1))
  return t
def pytest_terminal_summary(terminalreporter):
  try:
    terminalreporter.write_line('\nPER-TRANSITION REPORT');
    for r in json.load(open(f'{checks.SRC}/{checks.NAME}_qa_report.json')):terminalreporter.write_line(str(r))
  except Exception as e:terminalreporter.write_line(f'(no report: {e})')
