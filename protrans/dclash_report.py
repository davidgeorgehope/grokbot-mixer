"""Veto and breakdown-exit share for DRUMCLASH nightly candidates.

A confident clash veto is drumclash.hard.flagged. The safe fallback is a
landing / breakdown fade (landing_pick set): the outgoing leaves where a
breakdown ends, and the incoming drop starts on that same bar. This module
does not change picks or write rules.json.
"""
from __future__ import annotations


def _id_map(rows):
    out = {}
    for r in rows or []:
        if r.get('id') and not r.get('error'):
            out[r['id']] = r
    return out


def _vetoed(row):
    hd = (row.get('drumclash') or {}).get('hard') or {}
    return bool(hd.get('flagged'))


def _landing_win(row):
    lp = (row.get('drumclash') or {}).get('landing_pick')
    return list(lp) if lp else None


def summarize(arm_rows, base_rows=None):
    """Return counts for one arm, compared with the default (base) rows."""
    A = _id_map(arm_rows)
    B = _id_map(base_rows)
    ids = sorted(A)
    n = len(ids)
    veto_ids = [i for i in ids if _vetoed(A[i])]
    land_ids = [i for i in ids if _landing_win(A[i])]
    base_land = [i for i in ids if i in B and _landing_win(B[i])]
    base_veto = [i for i in ids if i in B and _vetoed(B[i])]
    details = []
    for i in veto_ids:
        d = A[i].get('drumclash') or {}
        hd = d.get('hard') or {}
        details.append(dict(
            id=i,
            confidence=hd.get('confidence'),
            level=hd.get('level'),
            landing_pick=_landing_win(A[i]),
            win=(A[i].get('pick') or {}).get('win'),
            base_win=(B.get(i, {}).get('pick') or {}).get('win') if B else None,
        ))
    def share(k):
        return round(k / n, 3) if n else None
    return dict(
        n=n,
        vetoed=len(veto_ids),
        vetoed_ids=veto_ids,
        veto_share=share(len(veto_ids)),
        breakdown_exits=len(land_ids),
        breakdown_exit_ids=land_ids,
        breakdown_exit_share=share(len(land_ids)),
        base_vetoed=len(base_veto),
        base_veto_share=share(len(base_veto)),
        base_breakdown_exits=len(base_land),
        base_breakdown_exit_share=share(len(base_land)),
        vetoes=details,
    )


def format_line(name, stats):
    if not stats:
        return ''
    return (f"  dclash {name}: vetoed {stats['vetoed']}/{stats['n']} "
            f"({stats['veto_share']}) vs default {stats['base_vetoed']}/{stats['n']} "
            f"({stats['base_veto_share']}); breakdown-exits {stats['breakdown_exits']}/{stats['n']} "
            f"({stats['breakdown_exit_share']}) vs default {stats['base_breakdown_exits']}/{stats['n']} "
            f"({stats['base_breakdown_exit_share']})")
