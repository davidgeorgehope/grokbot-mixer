"""Decision distance of each labelled clip's *known* engine window to the pro's measured entry (bars).
ours blend start: outgoing at e-X, incoming at ib. pro: out_bar_at_entry / in_bar_at_entry (replica/protrans_decisions.json)."""
import json, os
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H)
PRO = json.load(open(os.path.join(P, 'replica', 'protrans_decisions.json')))
WIN = {  # from deliver/protrans diagnostics / clip jsons / log ours_pick
 'daily_1111': ('joe_syntax_hospital__08', ['n',240,None,24,32]), 'daily_1112': ('hybrid_minds_ukf__08', ['n',224,None,32,16]),
 'daily_1113': ('hybrid_minds_ukf__12', ['n',304,None,32,16]), 'daily_1114': ('hybrid_minds_ukf__19', ['n',176,None,32,16]),
 'daily_1115': ('hybrid_minds_ukf__25', ['n',192,None,0,16]), 'daily_1116': ('hybrid_minds_ukf__45', ['n',128,None,32,16]),
 'daily_1117': ('joe_syntax_hospital__11', ['n',240,None,24,16]),
 'planner_ukf19': ('hybrid_minds_ukf__19', ['n',112,None,48,16]), 'planner_ukf25': ('hybrid_minds_ukf__25', ['n',128,None,64,16]),
 'planner_ukf25_v2': ('hybrid_minds_ukf__25', ['n',128,None,192,16]), 'ranker_A_default': ('hybrid_minds_ukf__25', ['n',192,None,0,16]),
 'ranker_B_ranker': ('hybrid_minds_ukf__25', ['n',112,None,160,16]),
 'replica_v1_ukf19': ('hybrid_minds_ukf__19', ['n',128,None,32,16]), 'replica_v2_js08': ('joe_syntax_hospital__08', ['n',144,None,40,16]),
}
out = {}
for k, (pid, w) in WIN.items():
    p = PRO[pid]; o_out, o_in = w[1] - w[4], w[3]
    d_out = abs(o_out - p['out_bar_at_entry']); d_in = abs(o_in - p['in_bar_at_entry'])
    out[k] = dict(pick=pid, win=w, ours_out=o_out, ours_in=o_in, pro_out=p['out_bar_at_entry'], pro_in=p['in_bar_at_entry'],
                  d_out=round(d_out, 1), d_in=round(d_in, 1), d_sum=round(d_out + d_in, 1))
    print(f"{k:18s} {pid:26s} ours out {o_out:5.0f} in {o_in:5.0f} | pro out {p['out_bar_at_entry']:6.1f} in {p['in_bar_at_entry']:6.1f} | d_out {d_out:5.1f} d_in {d_in:5.1f}")
json.dump(out, open(os.path.join(H, 'decision_windows.json'), 'w'), indent=1)
for a, b in (('planner_ukf19', 'daily_1114'), ('planner_ukf25_v2', 'planner_ukf25'), ('ranker_B_ranker', 'ranker_A_default')):
    print(f'{a} preferred over {b}: decision distance {out[a]["d_sum"]} vs {out[b]["d_sum"]} -> agree={out[a]["d_sum"] < out[b]["d_sum"]}')
