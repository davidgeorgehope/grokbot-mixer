#!/usr/bin/env bash
# usage: runjob.sh <name> <command...>  -> writes jobs/<name>.status + .log; optional POST to $JOB_WEBHOOK_URL
name="$1"; shift; d=/workspace/mixes/jobs
echo "running $(date -Is)" > "$d/$name.status"
"$@" > "$d/$name.log" 2>&1; rc=$?
if [ $rc -eq 0 ]; then st=done; else st=failed; fi
echo "$st rc=$rc $(date -Is)" > "$d/$name.status"
if [ -n "$JOB_WEBHOOK_URL" ]; then curl -s -m 20 -X POST -H "Content-Type: application/json" ${JOB_WEBHOOK_KEY:+-H "Authorization: Bearer $JOB_WEBHOOK_KEY"} -d "{\"job\":\"$name\",\"status\":\"$st\",\"rc\":$rc,\"tail\":$(tail -c 1500 "$d/$name.log" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}" "$JOB_WEBHOOK_URL" >/dev/null; fi
exit $rc
