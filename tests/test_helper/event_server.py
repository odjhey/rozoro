#!/usr/bin/env python3
import json, os, socket, sys, time

path, record, mode, *events = sys.argv[1:]
try: os.unlink(path)
except FileNotFoundError: pass
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path); server.listen(8)

def serve(conn):
    data = b""
    while b"\n" not in data:
        chunk = conn.recv(65536)
        if not chunk: return
        data += chunk
    with open(record, "w") as out: json.dump(json.loads(data.split(b"\n", 1)[0]), out)
    if mode == "close": return
    if mode == "malformed": conn.sendall(b'{"result":{"type":"wrong"}}\n'); return
    conn.sendall(b'{"id":"rozoro-eventwait","result":{"type":"subscription_started"}}\n')
    if mode == "timeout": time.sleep(2); return
    for item in events:
        pane, workspace, status, agent = item.split(",", 3)
        msg = {"event":"pane.agent_status_changed","data":{"pane_id":pane,"workspace_id":workspace,"agent_status":status,"agent":agent}}
        conn.sendall((json.dumps(msg) + "\n").encode())
    if mode == "hold": time.sleep(5)

if mode == "multi":
    for _ in range(2):
        conn, _ = server.accept(); serve(conn); conn.close()
else:
    conn, _ = server.accept(); serve(conn); conn.close()
server.close()
