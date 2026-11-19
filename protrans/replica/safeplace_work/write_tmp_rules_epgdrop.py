#!/usr/bin/env python3
import json
r = json.load(open("/workspace/mixes/protrans/rules.json"))
assert not r.get("EXITPOS") and not r.get("EXITPOS_GATE") and not r.get("EXITPOS_DROP") and not r.get("SLOWDOWN")
q = dict(r)
q.update({"EXITPOS": 1, "EXITPOS_DROP": 1})
json.dump(q, open("/tmp/rules_epgdrop_1119.json", "w"), indent=1)
print("wrote /tmp/rules_epgdrop_1119.json; rules.json unchanged")
