#!/usr/bin/env python3
"""Small daemon API bridge for opt-in status/reconcile commands."""
from __future__ import annotations
import argparse, json, os, socket, sys, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
from rozoro_monitor import protocol

class BridgeError(RuntimeError): pass

def exchange(messages, home):
    path=Path(home)/"monitor.sock"
    replies=[]
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(3); s.connect(str(path))
            stream=s.makefile("rwb",buffering=0)
            for message in messages:
                stream.write(protocol.encode(message).encode())
                while True:
                    raw=stream.readline(protocol.MAX_FRAME_BYTES+2)
                    if not raw: raise BridgeError("daemon closed the connection")
                    reply=protocol.decode(raw)
                    if reply.get("type")=="notification": continue
                    if reply.get("type") in {"frame.error","request.error"}:
                        raise BridgeError(f"daemon rejected {message['type']}: {reply.get('code')}")
                    if reply.get("request_id") != message.get("request_id"):
                        raise BridgeError("daemon returned a mismatched response")
                    replies.append(reply); break
        return replies
    except (OSError,protocol.ProtocolError) as exc:
        raise BridgeError(f"event-bus daemon unavailable at {path}: {exc}") from exc

def req(kind, **fields): return {"v":1,"type":kind,"request_id":uuid.uuid4().hex,**fields}

def legacy_pending(home):
    root=Path(home)/"watchtowers"
    pending=[]
    if root.is_dir():
        for directory in root.iterdir():
            if not directory.is_dir(): continue
            try: data=json.loads((directory/"pending.json").read_text()); generation=int(data.get("generation",0))
            except (OSError,ValueError,TypeError): generation=0
            try: ack=int((directory/"ack").read_text().strip())
            except (OSError,ValueError): ack=0
            if generation>ack: pending.append((directory.name,generation,ack))
    return pending

def enforce_boundary(home):
    pending=legacy_pending(home)
    if pending:
        detail=", ".join(f"{name} generation={g} ack={a}" for name,g,a in pending)
        raise BridgeError("legacy wake ledger still has pending work ("+detail+"). Reconcile legacy state first with ROZORO_EVENT_BUS_FALLBACK=1 ./bin/rozoro reconcile --driver <id>")

def registration(driver,harness):
    return req("watchtower.register",driver_id=driver,session_id=f"cli-{driver}",harness=harness)

def main():
    p=argparse.ArgumentParser(); p.add_argument("operation",choices=["status","snapshot","ack"])
    p.add_argument("--task"); p.add_argument("--driver"); p.add_argument("--harness",default="pi"); p.add_argument("--through",type=int)
    a=p.parse_args(); home=os.environ.get("ROZORO_HOME",str(Path.home()/".rozoro")); enforce_boundary(home)
    if a.operation=="status":
        if not a.task: p.error("--task is required")
        reply=exchange([req("task.status",task_id=a.task)],home)[0]
    else:
        if not a.driver: p.error("--driver is required")
        if a.operation=="snapshot":
            registered,snap=exchange([registration(a.driver,a.harness),req("driver.snapshot",driver_id=a.driver)],home)
            through=snap["generation"]
            if through==0 or through<=snap["acked_generation"]:
                reply={"v":1,"type":"reconcile.result","through":through,"reports":[]}
            else:
                reply=exchange([registration(a.driver,a.harness),req("reconcile",driver_id=a.driver,through=through)],home)[1]
        else:
            if not a.through or a.through<1: p.error("--through must be positive")
            reply=exchange([registration(a.driver,a.harness),req("ack-generation",driver_id=a.driver,through=a.through)],home)[1]
    print(json.dumps(reply,sort_keys=True,separators=(",",":")))

if __name__=="__main__":
    try: main()
    except BridgeError as exc:
        print(f"rozoro event bus: {exc}",file=sys.stderr); raise SystemExit(2)
