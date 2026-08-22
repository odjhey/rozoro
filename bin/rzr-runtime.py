#!/usr/bin/env python3
"""Atomic watcher-owned foreground/turn reducer (Herdr background capability ready)."""
import argparse,datetime,fcntl,importlib.util,json,os,tempfile,time

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
def load(path,tid):
 try: return json.load(open(path))
 except Exception: return {"schema_version":2,"id":tid,"source":{"kind":"herdr-watch","protocol":None,"freshness":"current","observed_at":None,"event_seq":None},"runtime_status":"unknown","foreground_status":None,"background_activity":{"supported":None,"state":"unknown","active_count":None,"jobs":[],"observed_at":None,"event_seq":None},"turn":{"turn_key":None,"transition":None,"blocks_before":None,"blocks_after":None,"report_indices":[],"report_status":"unobserved","observed_at":None},"action":{"required":False,"reason":None,"edge_id":None}}
def count(handoff,parser):
 spec=importlib.util.spec_from_file_location("h",parser); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.parse(handoff)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("operation",choices=["reconcile","event","mark-stale"]); ap.add_argument("--id",required=True); ap.add_argument("--path",required=True); ap.add_argument("--handoff",required=True); ap.add_argument("--parser",required=True); ap.add_argument("--foreground"); ap.add_argument("--seq",type=int); ap.add_argument("--observed-at"); ap.add_argument("--delay-ms",type=int,default=int(os.environ.get("RZR_HANDOFF_DELAY_MS","200"))); a=ap.parse_args()
 os.makedirs(os.path.dirname(a.path),exist_ok=True); lock=a.path+".lock"
 with open(lock,"a+") as lf:
  fcntl.flock(lf,fcntl.LOCK_EX); d=load(a.path,a.id); ts=a.observed_at or now(); old=d.get("foreground_status"); oldseq=(d.get("source") or {}).get("event_seq")
  if a.operation=="mark-stale": d["source"]["freshness"]="stale"
  elif a.seq is not None and oldseq is not None and a.seq<=oldseq: pass
  else:
   st=a.foreground or "unknown"; seq=a.seq if a.seq is not None else ((oldseq or 0)+1); d["source"].update({"freshness":"current","observed_at":ts,"event_seq":seq,"sequence_kind":"herdr" if a.seq is not None else "synthetic-fallback"}); d["foreground_status"]=st; d["runtime_status"]=st
   parsed=count(a.handoff,a.parser); turn=d["turn"]
   if a.operation=="reconcile":
    if st=="working": turn.update({"turn_key":f"{a.id}:{seq}","blocks_before":parsed["blocks"],"report_status":"in-progress","observed_at":ts})
   elif st=="working" and old!="working":
    turn.update({"turn_key":f"{a.id}:{seq}","transition":f"{old or 'unknown'}->working","blocks_before":parsed["blocks"],"blocks_after":None,"report_indices":[],"report_status":"in-progress","observed_at":ts}); d["action"]={"required":False,"reason":None,"edge_id":None}
   elif st=="gone" and old not in (None,"gone","shell"):
    turn.update({"transition":f"{old}->gone","observed_at":ts})
    d["action"]={"required":True,"reason":"pane-gone","edge_id":f"{a.id}:{seq}:pane-gone"}
   elif (old=="working" and st in ("idle","done","blocked")) or st=="blocked":
    before=turn.get("blocks_before"); after=parsed["blocks"]
    # Exactly one bounded retry closes the foreground-event/handoff-append race.
    if old=="working" and after==(before or 0) and a.delay_ms>0:
     time.sleep(a.delay_ms/1000.0); parsed=count(a.handoff,a.parser); after=parsed["blocks"]
    indices=list(range((before or 0)+1,after+1)); status="missing-handoff"; reason="missing-handoff"
    if len(indices)==1: status="reported" if parsed["block_details"][indices[0]-1]["valid"] else "invalid-report"; reason="turn-settled" if status=="reported" else "invalid-report"
    elif len(indices)>1: status="invalid-report"; reason="invalid-report"
    if st=="blocked": reason="runtime-blocked"
    # Current Herdr has no background capability: waiting can never suppress.
    if indices and parsed["block_details"][indices[-1]-1]["fields"].get("verdict")=="waiting": reason="inconsistent-wait"
    turn.update({"transition":f"working->{st}","blocks_after":after,"report_indices":indices,"report_status":status,"observed_at":ts}); d["action"]={"required":True,"reason":reason,"edge_id":f"{a.id}:{seq}:{reason}"}
  fd,tmp=tempfile.mkstemp(prefix=os.path.basename(a.path)+".",dir=os.path.dirname(a.path)); os.close(fd)
  with open(tmp,"w") as f: json.dump(d,f,sort_keys=True,separators=(",",":")); f.write("\n")
  os.replace(tmp,a.path); print(json.dumps(d,sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
