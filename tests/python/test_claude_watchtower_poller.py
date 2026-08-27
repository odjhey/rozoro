import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("claude_poller", ROOT / "bin/rzr-claude-watchtower-poll.py")
POLL = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(POLL)


class PollerTests(unittest.TestCase):
    def test_selected_home_is_expanded_and_lexically_normalized_once(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"HOME": td}):
            with mock.patch.object(POLL.os.path, "expanduser", wraps=os.path.expanduser) as expand:
                self.assertEqual(POLL.normalized_path("~/parent/../home"), Path(td) / "home")
                expand.assert_called_once_with("~/parent/../home")
        unresolved = "~rozoro-user-that-does-not-exist-129/home"
        with self.assertRaisesRegex(ValueError, "unresolved user path"):
            POLL.normalized_path(unresolved)

    def test_late_generation_waits_for_quiescence_then_confirms_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td); sock = home / "monitor.sock"; ready = threading.Event()
            availability = ["quiescent", "busy", "waiting-background", "quiescent", "gone"]
            polls = 0; confirms = []; transcript = []
            def serve():
                nonlocal polls
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); server.bind(str(sock)); server.listen(); ready.set()
                connection, _ = server.accept()
                with connection, connection.makefile("rwb", buffering=0) as stream:
                    registered = False
                    for line in stream:
                        msg = json.loads(line); transcript.append(msg["type"]); rid = msg["request_id"]
                        if msg["type"] == "watchtower.register": registered = True; reply = {"v":1,"type":"ok","request_id":rid}
                        elif msg["type"] == "watchtower.availability":
                            reply={"v":1,"type":"watchtower.availability.result","request_id":rid,"driver_id":"d","availability":availability.pop(0)}
                        elif msg["type"] == "notification.pending":
                            self.assertTrue(registered); polls += 1; reply={"v":1,"type":"ok","request_id":rid}
                        else:
                            confirms.append(msg["generation"]); reply={"v":1,"type":"ok","request_id":rid}
                        stream.write((json.dumps(reply)+"\n").encode())
                        # First quiescent poll has no work. A generation arrives
                        # later, after busy/waiting-background, at the next safe poll.
                        if msg["type"] == "notification.pending" and polls == 2:
                            stream.write((json.dumps({"v":1,"type":"notification","generation":7,"priority":"normal","task_count":1})+"\n").encode())
                server.close()
            threading.Thread(target=serve, daemon=True).start(); ready.wait(1)
            completed = subprocess.CompletedProcess([], 0)
            with mock.patch.object(POLL.subprocess, "run", return_value=completed) as actuator:
                self.assertEqual(POLL.run(home,"d","s","pane",poll=.01,rpc_timeout=.2),0)
            self.assertEqual(polls,2)
            self.assertEqual(confirms,[7])
            actuator.assert_called_once_with(["herdr","agent","prompt","pane",POLL.FIXED], timeout=.2,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            self.assertEqual(transcript.count("notification.pending"),2)

    def test_connected_poller_closes_promptly_when_owner_dies(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); sock=home/"monitor.sock"; ready=threading.Event(); connected=threading.Event(); closed=threading.Event()
            def serve():
                server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); server.bind(str(sock)); server.listen(); ready.set()
                connection,_=server.accept(); connected.set()
                try:
                    with connection, connection.makefile("rwb",buffering=0) as stream:
                        for line in stream:
                            msg=json.loads(line); rid=msg["request_id"]
                            reply={"v":1,"type":"ok","request_id":rid} if msg["type"]=="watchtower.register" else {"v":1,"type":"watchtower.availability.result","request_id":rid,"driver_id":"d","availability":"busy"}
                            stream.write((json.dumps(reply)+"\n").encode())
                finally:
                    closed.set(); server.close()
            threading.Thread(target=serve,daemon=True).start(); ready.wait(1)
            owner=subprocess.Popen(["sleep","10"])
            poller=subprocess.Popen([str(ROOT/"bin/rzr-claude-watchtower-poll.py"),"--home",str(home),"--driver","d","--session","s","--pane","p","--parent",str(owner.pid),"--poll",".02"])
            self.assertTrue(connected.wait(1)); owner.terminate(); owner.wait()
            self.assertEqual(poller.wait(timeout=1.5),0); self.assertTrue(closed.wait(1))

    def test_refusal_keeps_server_socket_open_then_reconnects_and_confirms(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); sock=home/"monitor.sock"; ready=threading.Event(); epochs=[]; confirms=[]; first_eof=[]
            def serve():
                server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); server.bind(str(sock)); server.listen(); ready.set()
                for epoch in (1,2):
                    connection,_=server.accept(); epochs.append(epoch); availability_calls=0
                    with connection, connection.makefile("rwb",buffering=0) as stream:
                        for line in stream:
                            msg=json.loads(line); rid=msg["request_id"]; kind=msg["type"]
                            if kind=="watchtower.register": reply={"v":1,"type":"ok","request_id":rid}
                            elif kind=="watchtower.availability":
                                availability_calls += 1
                                state = "gone" if epoch==2 and availability_calls>1 else "quiescent"
                                reply={"v":1,"type":"watchtower.availability.result","request_id":rid,"driver_id":"d","availability":state}
                            elif kind=="notification.pending":
                                reply={"v":1,"type":"ok","request_id":rid}; stream.write((json.dumps(reply)+"\n").encode()); stream.write((json.dumps({"v":1,"type":"notification","generation":4,"priority":"normal","task_count":1})+"\n").encode()); continue
                            else: confirms.append((epoch,msg["generation"])); reply={"v":1,"type":"ok","request_id":rid}
                            stream.write((json.dumps(reply)+"\n").encode())
                    if epoch==1: first_eof.append(True)  # client closed after refusal; server never forced it
                server.close()
            threading.Thread(target=serve,daemon=True).start(); ready.wait(1)
            outcomes=[subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0)]
            with mock.patch.object(POLL.subprocess,"run",side_effect=outcomes):
                self.assertEqual(POLL.run(home,"d","s","pane",poll=.01,rpc_timeout=.1),0)
            self.assertEqual(epochs,[1,2]); self.assertEqual(first_eof,[True]); self.assertEqual(confirms,[(2,4)])


if __name__ == "__main__": unittest.main()
