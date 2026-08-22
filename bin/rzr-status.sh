#!/usr/bin/env bash
# Pure composition of durable handoff and watcher-owned runtime projection.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"
[ $# -ge 1 ] || rzr_die "usage: rzr-status.sh <id> [--json] [--peek]"
ID="$1"; shift; JSON=0
for a in "$@"; do case "$a" in --json) JSON=1 ;; --peek) : ;; *) rzr_die "unknown flag $a" ;; esac; done
FOLDER="$(rzr_task_dir "$ID")"; HF="$FOLDER/handoff.md"
[ -f "$HF" ] || rzr_die "no task folder for '$ID' ($HF missing)"
RZR_ID="$ID" RZR_HF="$HF" RZR_ACK2="$FOLDER/.acked-blocks-v2" RZR_ACK="$FOLDER/.acked-blocks" \
RZR_RUNTIME="$RZR_STATE/$ID.runtime.json" RZR_LEGACY="$RZR_STATE/$ID.status" RZR_JSON="$JSON" \
RZR_PARSER="$RZR_BIN/rzr-handoff.py" python3 - <<'PY'
import importlib.util,json,os
spec=importlib.util.spec_from_file_location("handoff",os.environ["RZR_PARSER"]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
p=m.parse(os.environ["RZR_HF"],os.environ["RZR_ACK2"],os.environ["RZR_ACK"])
bg={"supported":None,"state":"unknown","active_count":None}
runtime="unknown"; fg=None; freshness="absent"; turn="unobserved"; action={"required":False,"reason":None}
try:
 r=json.load(open(os.environ["RZR_RUNTIME"])); runtime=r.get("runtime_status","unknown"); fg=r.get("foreground_status"); freshness=(r.get("source") or {}).get("freshness","current"); bg.update(r.get("background_activity") or {}); turn=(r.get("turn") or {}).get("report_status","unobserved"); action.update(r.get("action") or {})
except Exception:
 try: fg=open(os.environ["RZR_LEGACY"]).read().strip(); runtime=fg or "unknown"; freshness="legacy"
 except Exception: pass
latest=p["latest"]; f=(latest or {}).get("fields",{}); verdict=f.get("verdict") or None
verdict_norm=(verdict or "").lower()
inconsist=[]
waiting_ok=(verdict_norm=="waiting" and not p["unresolved"] and latest and latest["valid"] and freshness=="current" and bg.get("supported") is True and bg.get("state")=="active" and (bg.get("active_count") or 0)>0)
if p["protocol_errors"]: task="protocol-error"
elif not latest: task="no-handoff"
elif p["unresolved"]: task="open-items"
elif verdict_norm=="waiting":
 task="waiting" if waiting_ok else "reported-incomplete"
 if not waiting_ok: inconsist.append("waiting handoff is not certified by current supported background activity")
elif verdict_norm=="done": task="reported-done"
elif verdict_norm=="failed": task="reported-failed"
else: task="reported-incomplete"
if inconsist and not action["required"]: action={"required":True,"reason":"inconsistent-wait"}
out={"schema_version":2,"id":os.environ["RZR_ID"],"runtime_status":runtime,"foreground_status":fg,"runtime_freshness":freshness,"background_activity":bg,"task_status":task,"handoff_verdict":verdict,"verdict":verdict or "(no-handoff-yet)","turn_report_status":turn,"action_required":bool(action.get("required")),"action_reason":action.get("reason"),"blocks":p["blocks"],"acked_through":p["acked_through"],"acked_source":p["acked_source"],"unresolved":p["unresolved"],"open_items":p["open_items"],"protocol_errors":p["protocol_errors"],"inconsistencies":inconsist,"heading":(latest or {}).get("heading",""),"reason":f.get("reason",""),"pending":f.get("pending",""),"inputs_needed":f.get("inputs-needed",""),"artifacts":f.get("artifacts","")}
if os.environ["RZR_JSON"]=="1": print(json.dumps(out,sort_keys=True,separators=(",",":")))
else:
 print(f'{out["id"]:<16} runtime={runtime} foreground={fg or "unknown"} background={bg["state"]} task={task} turn={turn}')
 for e in p["protocol_errors"]: print("  ! protocol: "+e)
 for e in inconsist: print("  ! "+e)
 if p["open_items"]: print(f'  ⚠ {len(p["open_items"])} unresolved open item(s)')
 for i in p["open_items"]: print(f'  OPEN turn {i["turn"]} [{i["verdict"] or "?"}] {i["heading"]}')
PY
