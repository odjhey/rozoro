#!/usr/bin/env python3
"""Hardened daemon API bridge for daemon-authoritative status and reconciliation."""
from __future__ import annotations
import argparse, fcntl, json, os, socket, stat, sys, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from rozoro_monitor import protocol
from rozoro_monitor.client import UnsafePathError, _open_home

class BridgeError(RuntimeError): pass

def req(kind: str, **fields):
    return {"v": 1, "type": kind, "request_id": uuid.uuid4().hex, **fields}

class AuthorityBoundary:
    """Exclude every legacy ledger writer while validating and using the daemon."""
    def __init__(self, home_fd: int): self.home_fd=home_fd; self.root_fd=-1; self.lock_fd=-1; self.cursors={}
    def __enter__(self):
        try: os.mkdir("watchtowers", 0o700, dir_fd=self.home_fd)
        except FileExistsError: pass
        flags=os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0)
        self.root_fd=os.open("watchtowers",flags,dir_fd=self.home_fd)
        info=os.fstat(self.root_fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise BridgeError("unsafe legacy watchtowers directory")
        self.lock_fd=os.open(".authority.lock",os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=self.root_fd)
        info=os.fstat(self.lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise BridgeError("unsafe legacy authority lock")
        fcntl.flock(self.lock_fd,fcntl.LOCK_EX)
        self._validate_structure()
        return self
    def _validate_structure(self):
        for name in os.listdir(self.root_fd):
            if name==".authority.lock": continue
            try:
                dfd=os.open(name,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0),dir_fd=self.root_fd)
            except OSError as exc: raise BridgeError(f"unsafe legacy driver entry {name}: {exc}") from exc
            try:
                info=os.fstat(dfd)
                if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077: raise BridgeError(f"unsafe legacy driver directory {name}")
                marker=self._read(dfd,".event-bus-authority",False)
                if marker is not None and marker!=b"event-bus-v1\n": raise BridgeError(f"malformed event-bus authority marker for {name}")
                generation,delivered=self._pending(dfd,name); ack=self._ack(dfd,name)
                if not 0<=ack<=delivered<=generation:
                    raise BridgeError(f"malformed legacy cursor invariants for {name}: require 0<=ack<=delivered<=generation")
                self.cursors[name]=(generation,delivered,ack)
            finally: os.close(dfd)
    @staticmethod
    def _read(dfd,name,required):
        try: fd=os.open(name,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0),dir_fd=dfd)
        except FileNotFoundError:
            if required: raise BridgeError(f"malformed legacy ledger: missing {name}")
            return None
        except OSError as exc: raise BridgeError(f"unreadable legacy ledger {name}: {exc}") from exc
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
                raise BridgeError(f"unsafe legacy ledger file {name}")
            chunks=bytearray()
            while True:
                chunk=os.read(fd,min(65536,protocol.MAX_FRAME_BYTES+1-len(chunks)))
                if not chunk: break
                chunks.extend(chunk)
                if len(chunks)>protocol.MAX_FRAME_BYTES: raise BridgeError(f"oversized legacy ledger file {name}")
            return bytes(chunks)
        finally: os.close(fd)
    def _pending(self,dfd,driver):
        raw=self._read(dfd,"pending.json",False)
        if raw is None: return 0,0
        try:
            def unique(pairs):
                result={}
                for key,item in pairs:
                    if key in result: raise ValueError("duplicate JSON key")
                    result[key]=item
                return result
            value=json.loads(raw,object_pairs_hook=unique)
            allowed={"schema","generation","delivered","tasks","delivery_state","retries","last_error","updated"}
            schema=value.get("schema") if isinstance(value,dict) else None
            if type(schema) is not int or schema!=1 or set(value)-allowed or not {"generation","delivered","tasks"}<=value.keys() or not isinstance(value["tasks"],dict): raise ValueError
            for task_id,item in value["tasks"].items():
                if not isinstance(task_id,str) or not isinstance(item,dict) or set(item)-{"status","edge_id","updated"}: raise ValueError
                if "status" not in item or not isinstance(item["status"],str): raise ValueError
                if item.get("edge_id") is not None and not isinstance(item["edge_id"],str): raise ValueError
                if "updated" in item and not isinstance(item["updated"],str): raise ValueError
            for field in ("delivery_state","last_error","updated"):
                if field in value and not isinstance(value[field],str): raise ValueError
            if "retries" in value and (type(value["retries"]) is not int or not 0<=value["retries"]<=protocol.MAX_INTEGER): raise ValueError
            generation=value["generation"]; delivered=value["delivered"]
            for cursor in (generation,delivered):
                if not isinstance(cursor,int) or isinstance(cursor,bool) or not 0<=cursor<=protocol.MAX_INTEGER: raise ValueError
            return generation,delivered
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc: raise BridgeError(f"malformed legacy pending ledger for {driver}") from exc
    def _ack(self,dfd,driver):
        raw=self._read(dfd,"ack",False)
        if raw is None: return 0
        try:
            text=raw.decode("ascii").strip()
            if not text or not text.isdigit(): raise ValueError
            value=int(text)
            if value>protocol.MAX_INTEGER: raise ValueError
            return value
        except (UnicodeError,ValueError) as exc: raise BridgeError(f"malformed legacy ACK ledger for {driver}") from exc
    def require_clean(self,driver:str):
        generation,_,ack=self.cursors.get(driver,(0,0,0))
        if generation>ack:
            raise BridgeError(f"legacy wake ledger still has pending work ({driver} generation={generation} ack={ack}). This release refuses until it is drained; check out the prior release and run: ./bin/rozoro reconcile --driver {driver}")
    def drivers(self):
        return [n for n in os.listdir(self.root_fd) if n!=".authority.lock"]
    def activate(self, driver: str|None=None):
        names=[driver] if driver else self.drivers()
        for name in names:
            try: dfd=os.open(name,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0),dir_fd=self.root_fd)
            except FileNotFoundError: continue
            try:
                fd=os.open(".event-bus-authority",os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=dfd)
                os.write(fd,b"event-bus-v1\n"); os.fsync(fd); os.close(fd); os.fsync(dfd)
            except FileExistsError:
                marker=self._read(dfd,".event-bus-authority",True)
                if marker!=b"event-bus-v1\n": raise BridgeError(f"malformed event-bus authority marker for {name}")
            finally: os.close(dfd)
    def disable(self,driver:str):
        dfd=os.open(driver,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0),dir_fd=self.root_fd)
        try:
            try: os.unlink(".event-bus-authority",dir_fd=dfd); os.fsync(dfd)
            except FileNotFoundError: pass
        finally: os.close(dfd)
    def __exit__(self,*_):
        if self.lock_fd>=0: os.close(self.lock_fd)
        if self.root_fd>=0: os.close(self.root_fd)

class DaemonFlow:
    def __init__(self,home:Path,home_fd:int):
        try: info=os.stat("monitor.sock",dir_fd=home_fd,follow_symlinks=False)
        except FileNotFoundError as exc: raise BridgeError(f"event-bus daemon unavailable at {home/'monitor.sock'}: socket missing") from exc
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise BridgeError("refusing unsafe event-bus socket")
        self.identity=(info.st_dev,info.st_ino); self.home=home; self.home_fd=home_fd
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); self.sock.settimeout(3)
        try: self.sock.connect(str(home/"monitor.sock"))
        except OSError as exc: self.sock.close(); raise BridgeError(f"event-bus daemon unavailable at {home/'monitor.sock'}: {exc}") from exc
        after=os.stat("monitor.sock",dir_fd=home_fd,follow_symlinks=False)
        if (after.st_dev,after.st_ino)!=self.identity or not stat.S_ISSOCK(after.st_mode):
            self.sock.close(); raise BridgeError("event-bus socket identity changed during connect")
        self.stream=self.sock.makefile("rwb",buffering=0)
    def request(self,message):
        self.stream.write(protocol.encode(message).encode())
        raw=self.stream.readline(protocol.MAX_FRAME_BYTES+2)
        if not raw: raise BridgeError("daemon closed the correlated flow")
        reply=protocol.decode(raw)
        if reply.get("type") in {"frame.error","request.error"}: raise BridgeError(f"daemon rejected {message['type']}: {reply.get('code')}")
        if reply.get("request_id")!=message["request_id"]: raise BridgeError("daemon returned a mismatched response")
        return reply
    def close(self): self.stream.close(); self.sock.close()

def compat(report):
    p=report["projection"]; handoff=p.get("report",{}); latest_verdict=handoff.get("latest_verdict")
    required={"folder_present","foreground","background","background_count","report"}
    required_report={"latest_verdict","blocks","acked_through","acked_source","unresolved","open_items","protocol_errors","heading","reason","pending","inputs_needed","artifacts"}
    if not required<=p.keys() or not required_report<=handoff.keys(): raise BridgeError("immutable snapshot is missing compatibility fields")
    if not isinstance(p["folder_present"],bool): raise BridgeError("immutable snapshot has invalid folder membership")
    errors=handoff.get("protocol_errors",[]); unresolved=handoff.get("unresolved",0); open_items=handoff.get("open_items",[])
    if errors: task="protocol-error"
    elif handoff.get("blocks",0)==0: task="no-handoff"
    elif unresolved: task="open-items"
    elif latest_verdict=="waiting": task="waiting" if report["availability"]=="waiting-background" else "reported-incomplete"
    elif latest_verdict=="done": task="reported-done"
    elif latest_verdict=="failed": task="reported-failed"
    else: task="reported-incomplete"
    reason=report["actionable_reason"]
    return {"schema_version":2,"id":report["task_id"],"runtime_status":report["availability"],
      "foreground_status":p.get("foreground","unknown"),"runtime_freshness":"current",
      "availability":report["availability"],"availability_source":"event-bus-snapshot",
      "background_activity":{"supported":True,"state":p.get("background","unknown"),"active_count":p.get("background_count")},
      "task_status":task,"handoff_verdict":latest_verdict,"verdict":latest_verdict or "(no-handoff-yet)","turn_report_status":"unobserved",
      "action_required":reason!="none","action_reason":None if reason=="none" else reason,
      "blocks":handoff.get("blocks",0),"acked_through":handoff.get("acked_through",0),"acked_source":handoff.get("acked_source","none"),
      "unresolved":unresolved,"open_items":open_items,"protocol_errors":errors,"inconsistencies":[],
      "heading":handoff.get("heading",""),"reason":handoff.get("reason",""),"pending":handoff.get("pending",""),
      "inputs_needed":handoff.get("inputs_needed",""),"artifacts":handoff.get("artifacts",""),"snapshot_generation":report["generation"],
      "snapshot_folder_present":p.get("folder_present")}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("operation",choices=["status","reconcile","authority-activate","authority-disable"]); ap.add_argument("--task"); ap.add_argument("--driver"); ap.add_argument("--json",action="store_true"); ap.add_argument("--full",action="store_true")
    a=ap.parse_args(); home_arg=os.environ.get("ROZORO_HOME",str(Path.home()/".rozoro"))
    try: home,home_fd=_open_home(home_arg,create=False)
    except (OSError,UnsafePathError) as exc: raise BridgeError(f"refusing unsafe ROZORO_HOME: {exc}") from exc
    try:
      with AuthorityBoundary(home_fd) as boundary:
        flow=DaemonFlow(home,home_fd)
        try:
          if a.operation=="authority-activate":
            if not a.driver: ap.error("--driver is required")
            authority=flow.request(req("driver.authority",driver_id=a.driver))["authority"]
            if authority!="active": raise BridgeError(f"driver {a.driver} has {authority} daemon authority")
            boundary.require_clean(a.driver); boundary.activate(a.driver); print(a.driver)
          elif a.operation=="authority-disable":
            if not a.driver: ap.error("--driver is required")
            flow.request(req("driver.disable",driver_id=a.driver))
            boundary.disable(a.driver)
            print(a.driver)
          elif a.operation=="status":
            if not a.task: ap.error("--task is required")
            active_drivers=[]
            for driver in boundary.drivers():
              authority=flow.request(req("driver.authority",driver_id=driver))["authority"]
              if authority=="active":
                boundary.require_clean(driver)
                active_drivers.append(driver)
            for driver in active_drivers: boundary.activate(driver)
            print(json.dumps(flow.request(req("task.status",task_id=a.task)),sort_keys=True,separators=(",",":")))
          else:
            if not a.driver: ap.error("--driver is required")
            authority=flow.request(req("driver.authority",driver_id=a.driver))["authority"]
            if authority!="active": raise BridgeError(f"driver {a.driver} has {authority} daemon authority; reconcile through explicit fallback")
            boundary.require_clean(a.driver); boundary.activate(a.driver)
            # Omit `scope` by default so a new client degrades to today's behavior
            # (full snapshot) against an old daemon; only `--full` sends a field.
            pending=req("reconcile.pending",driver_id=a.driver)
            if a.full: pending["scope"]="full"
            snap=flow.request(pending); through=snap["through"]
            projected=[compat(r) for r in snap["reports"]]
            vanished=[r["id"] for r in projected if r["snapshot_folder_present"] is False]
            reports=[r for r in projected if r["snapshot_folder_present"] is True]
            # Surface action-required tasks first; the format is otherwise unchanged.
            reports.sort(key=lambda r: not r["action_required"])
            since=snap.get("since"); unchanged=snap.get("unchanged_count")
            out={"driver":a.driver,"acknowledged_generation":through,"reports":reports,"vanished":vanished,"source":"event-bus"}
            if since is not None: out["changed_since_generation"]=since
            if unchanged is not None: out["unchanged_count"]=unchanged
            out["scope"]="full" if a.full else "delta"
            if a.json: print(json.dumps(out,sort_keys=True,separators=(",",":")))
            else:
              print(f"reconciled driver {a.driver} through generation {through}")
              for r in reports: print(f"  {r['id']}: runtime={r['runtime_status']} task={r['task_status']} turn={r['turn_report_status']} action={r['action_reason'] or 'none'}")
              for task_id in vanished: print(f"  {task_id} : vanished (no task folder)")
              if since is not None and unchanged is not None and not a.full:
                changed=len(reports)+len(vanished)
                print(f"  {changed} changed since generation {since}; {unchanged} unchanged tracked tasks not shown (--full for complete snapshot)")
            sys.stdout.flush()
            if through>0 and snap["reports"]: flow.request(req("reconcile.ack",driver_id=a.driver,through=through))
        finally: flow.close()
    finally: os.close(home_fd)

if __name__=="__main__":
  try: main()
  except (BridgeError,protocol.ProtocolError,OSError) as exc:
    print(f"rozoro event bus: {exc}",file=sys.stderr); raise SystemExit(2)
