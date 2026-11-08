"""Historical report integrity, not a claim to rerender old full mixes."""
import json
from pathlib import Path

def test_saved_bad_spots_are_represented():
    report=json.loads((Path(__file__).parent/'fixtures/guardrails_dj-mix-03-60_v1_rated.json').read_text())
    def sec(t):
        a,b=t.split(':');return int(a)*60+int(b)
    for start,end in [(780,880),(1920,1990),(2160,2370)]:
        assert any(start<=f['sec']<=end or start<=sec(f['t_end'])<=end
                   for f in report['failures'])
