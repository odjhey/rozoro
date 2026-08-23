#!/usr/bin/env python3
"""Real socket/store/CLI rollback boundary regression."""
import json, os, socket, subprocess, sys, time, uuid
from pathlib import Path
repo=Path(sys.argv[1]); home=Path(sys.argv[2]); sys.path.insert(0,str(repo/'lib'))
from rozoro_monitor import protocol

def send(stream,msg,extra=False):
 stream.write(protocol.encode(msg).encode()); first=protocol.decode(stream.readline())
 return (first,protocol.decode(stream.readline())) if extra else first
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.connect(str(home/'monitor.sock')); stream=s.makefile('rwb',buffering=0)
assert send(stream,{"v":1,"type":"watchtower.register","request_id":"reg","session_id":"watch-session","harness":"pi","driver_id":"driver-rollback"})["type"]=="ok"
base={"v":1,"session_id":"crew-session","harness":"pi","role":"crew","task_id":"task-rb"}
frames=[dict(base,type="session.register",event_id=uuid.uuid4().hex,producer_seq=1),dict(base,type="turn.start",event_id=uuid.uuid4().hex,producer_seq=2,turn_id="turn"),dict(base,type="turn.stop",event_id=uuid.uuid4().hex,producer_seq=3,turn_id="turn",background_active=False)]
for frame in frames: assert send(stream,frame)["type"]=="ack"
assert send(stream,{"v":1,"type":"notification.pending","request_id":"open","driver_id":"driver-rollback"})["type"]=="ok"
time.sleep(.4)
ok,note=send(stream,{"v":1,"type":"notification.pending","request_id":"poll","driver_id":"driver-rollback"},True); generation=note["generation"]
assert send(stream,{"v":1,"type":"notification.delivered","request_id":"del","driver_id":"driver-rollback","generation":generation})["type"]=="ok"
env={**os.environ,"ROZORO_HOME":str(home)}
legacy=home/'watchtowers/driver-rollback'; legacy.mkdir(parents=True,exist_ok=True); os.chmod(home/'watchtowers',0o700); os.chmod(legacy,0o700)
subprocess.run([sys.executable,str(repo/'bin/rzr-event-bus-client.py'),'authority-activate','--driver','driver-rollback'],env=env,check=True,stdout=subprocess.DEVNULL)
marker=home/'watchtowers/driver-rollback/.event-bus-authority'; assert marker.is_file()
dirty=subprocess.run([str(repo/'bin/rozoro'),'rollback','--driver','driver-rollback'],env=env,text=True,capture_output=True)
assert dirty.returncode!=0 and marker.is_file(),dirty
assert send(stream,{"v":1,"type":"reconcile","request_id":"rec","driver_id":"driver-rollback","through":generation})["type"]=="reconcile.result"
assert send(stream,{"v":1,"type":"ack-generation","request_id":"ack","driver_id":"driver-rollback","through":generation})["type"]=="ok"
clean=subprocess.run([str(repo/'bin/rozoro'),'rollback','--driver','driver-rollback'],env=env,text=True,capture_output=True)
assert clean.returncode==0 and not marker.exists(),clean
stream.close();s.close()
