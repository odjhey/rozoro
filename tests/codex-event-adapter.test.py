#!/usr/bin/env python3
import importlib.util, json, socket, tempfile, threading, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("adapter",ROOT/"bin/rzr-codex-event-adapter.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)

def test_ten_second_style_completion_emits_structured_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); store=root/"sessions/2026/08/24"; store.mkdir(parents=True)
        rollout=store/"rollout.jsonl"; cwd=str(root/"repo"); (root/"repo").mkdir()
        rows=[
          {"type":"session_meta","payload":{"id":"codex-session","cwd":cwd}},
          {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"rozoro-task: sleep-10\nsleep 10"}]}},
          {"type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1","started_at":100}},
          {"type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1","started_at":100,"completed_at":110,"duration_ms":10000}},
        ]
        rollout.write_text("".join(json.dumps(row)+"\n" for row in rows))
        sockpath=root/"monitor.sock"; server=socket.socket(socket.AF_UNIX); server.bind(str(sockpath)); server.listen()
        frames=[]
        def serve():
            while len(frames)<3:
                conn,_=server.accept()
                with conn:
                    frame=json.loads(conn.makefile().readline()); frames.append(frame)
                    conn.sendall((json.dumps({"v":1,"type":"ack","event_id":frame["event_id"],"durable_seq":len(frames)})+"\n").encode())
        threading.Thread(target=serve,daemon=True).start()
        args=type("Args",(),{"store":str(root/"sessions"),"task":"sleep-10","cwd":cwd,"session":None,"socket":str(sockpath)})
        threading.Thread(target=adapter.run,args=(args,),daemon=True).start()
        deadline=time.time()+3
        while len(frames)<3 and time.time()<deadline: time.sleep(.01)
        server.close()
        assert [f["type"] for f in frames]==["session.register","turn.start","turn.stop"]
        assert [f["producer_seq"] for f in frames]==[1,2,3]
        assert frames[-1]["background_active"] is None and frames[-1]["turn_id"]=="turn-1"

if __name__=="__main__": test_ten_second_style_completion_emits_structured_lifecycle()
