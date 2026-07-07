import os
import signal
import subprocess
import time

def find_pid():
    try:
        output = subprocess.check_output(["pgrep", "-f", "python server.py"]).decode().strip()
        pids = [int(p) for p in output.split('\n') if p]
        return pids
    except:
        return []

pids = find_pid()
for pid in pids:
    if pid != os.getpid():
        print(f"Killing pid {pid}")
        os.kill(pid, signal.SIGINT)

time.sleep(2)
