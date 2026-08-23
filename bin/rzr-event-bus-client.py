#!/usr/bin/env python3
"""Hardened daemon API bridge for opt-in status and exact-offer reconciliation."""
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
    def __init__(self, home_fd: int): self.home_fd=home_fd; self.root_fd=-1; self.lock_fd=-1
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
        self._validate_clean()
        return self
    def _validate_clean(self):
        for name in os.listdir(self.root_fd):
            if name==".authority.lock": continue
            try:
                dfd=os.open(name,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0),dir_fd=self.root_fd)
            except OSError as exc: raise BridgeError(f"unsafe legacy driver entry {name}: {exc}") from exc
            try:
                info=os.fstat(dfd)
                if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077: raise BridgeError(f"unsafe legacy driver directory {name}")
                generation=self._pending(dfd,name); ack=self._ack(dfd,name)
                if generation>ack:
                    raise BridgeError(f"legacy wake ledger still has pending work ({name} generation={generation} ack={ack}). Reconcile legacy state first with ROZORO_EVENT_BUS_FALLBACK=1 ./bin/rozoro reconcile --driver {name}")
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
            return os.read(fd,protocol.MAX_FRAME_BYTES+1)
        finally: os.close(fd)
    def _pending(self,dfd,driver):
        raw=self._read(dfd,"pending.json",False)
        if raw is None: return 0
        try:
            value=json.loads(raw); generation=value["generation"]
            if not isinstance(generation,int) or isinstance(generation,bool) or generation<0: raise ValueError
            return generation
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc: raise BridgeError(f"malformed legacy pending ledger for {driver}") from exc
    def _ack(self,dfd,driver):
        raw=self._read(dfd,"ack",False)
        if raw is None: return 0
        try:
            text=raw.decode("ascii").strip()
            if not text or not text.isdigit(): raise ValueError
            return int(text)
        except (UnicodeError,ValueError) as exc: raise BridgeError(f"malformed legacy ACK ledger for {driver}") from exc
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
    p=report["projection"]; handoff=p.get("report",{}); verdict=report["verdict"]
    errors=handoff.get("protocol_errors",[]); unresolved=handoff.get("unresolved",0); open_items=handoff.get("open_items",[])
    if errors: task="protocol-error"
    elif handoff.get("blocks",0)==0: task="no-handoff"
    elif unresolved: task="open-items"
    elif verdict=="waiting": task="waiting" if report["availability"]=="waiting-background" else "reported-incomplete"
    elif verdict=="done": task="reported-done"
    elif verdict=="failed": task="reported-failed"
    else: task="reported-incomplete"
    reason=report["actionable_reason"]
    return {"schema_version":2,"id":report["task_id"],"runtime_status":report["availability"],
      "foreground_status":p.get("foreground","unknown"),"runtime_freshness":"current",
      "availability":report["availability"],"availability_source":"event-bus-snapshot",
      "background_activity":{"supported":True,"state":p.get("background","unknown"),"active_count":p.get("background_count")},
      "task_status":task,"handoff_verdict":verdict,"verdict":verdict or "(no-handoff-yet)","turn_report_status":"unobserved",
      "action_required":reason!="none","action_reason":None if reason=="none" else reason,
      "blocks":handoff.get("blocks",0),"acked_through":handoff.get("acked_through",0),"acked_source":handoff.get("acked_source","none"),
      "unresolved":unresolved,"open_items":open_items,"protocol_errors":errors,"inconsistencies":[],
      "heading":handoff.get("heading",""),"reason":handoff.get("reason",""),"pending":handoff.get("pending",""),
      "inputs_needed":handoff.get("inputs_needed",""),"artifacts":handoff.get("artifacts",""),"snapshot_generation":report["generation"]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("operation",choices=["status","reconcile"]); ap.add_argument("--task"); ap.add_argument("--driver"); ap.add_argument("--json",action="store_true")
    a=ap.parse_args(); home_arg=os.environ.get("ROZORO_HOME",str(Path.home()/".rozoro"))
    try: home,home_fd=_open_home(home_arg,create=False)
    except (OSError,UnsafePathError) as exc: raise BridgeError(f"refusing unsafe ROZORO_HOME: {exc}") from exc
    try:
      with AuthorityBoundary(home_fd):
        flow=DaemonFlow(home,home_fd)
        try:
          if a.operation=="status":
            if not a.task: ap.error("--task is required")
            print(json.dumps(flow.request(req("task.status",task_id=a.task)),sort_keys=True,separators=(",",":")))
          else:
            if not a.driver: ap.error("--driver is required")
            snap=flow.request(req("reconcile.pending",driver_id=a.driver)); through=snap["through"]
            reports=[compat(r) for r in snap["reports"]]; vanished=[r["id"] for r in reports if r["availability"]=="gone"]
            out={"driver":a.driver,"acknowledged_generation":through,"reports":reports,"vanished":vanished,"source":"event-bus"}
            if a.json: print(json.dumps(out,sort_keys=True,separators=(",",":")))
            else:
              print(f"reconciled driver {a.driver} through generation {through}")
              for r in reports: print(f"  {r['id']}: runtime={r['runtime_status']} task={r['task_status']} turn={r['turn_report_status']} action={r['action_reason'] or 'none'}")
            sys.stdout.flush()
            if through>0 and snap["reports"]: flow.request(req("reconcile.ack",driver_id=a.driver,through=through))
        finally: flow.close()
    finally: os.close(home_fd)

if __name__=="__main__":
  try: main()
  except (BridgeError,protocol.ProtocolError,OSError) as exc:
    print(f"rozoro event bus: {exc}",file=sys.stderr); raise SystemExit(2)
