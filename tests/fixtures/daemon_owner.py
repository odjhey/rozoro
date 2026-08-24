#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_helper import process_cleanup

home = Path(tempfile.mkdtemp(prefix="interrupt-python-")) / "home"
mode, output = sys.argv[1], Path(sys.argv[2])
if mode == "direct":
    process = subprocess.Popen([sys.executable, str(ROOT / "bin/rozorod.py"), "--home", str(home)])
    process_cleanup.register(process, home)
else:
    home.mkdir(mode=0o700)
    subprocess.run([sys.executable, str(ROOT / "bin/rzr-monitor.py"), "start"],
                   env={**os.environ, "ROZORO_HOME": str(home)}, check=True)
    process_cleanup.register_lock(home)
while not (home / "monitor.sock").exists(): time.sleep(.01)
output.write_text(str(home))
if mode == "assertion":
    raise AssertionError("intentional interrupted-path assertion")
while True: time.sleep(1)
