import time
import subprocess
import logging

logger = logging.getLogger("GCPMonitor")

def get_vm_realtime_metrics():
    """
    Queries the VM via SSH for real-time CPU and Memory utilization.
    Returns a tuple: (cpu_utilization_pct, memory_utilization_pct)
    """
    cmd = (
        "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 johngiles@35.208.90.255 "
        "\"CORES=\\$(nproc); top -bn1 | grep 'Cpu(s)' | awk -v cores=\\$CORES '{print (\\$2 + \\$4) * cores}'; free | grep Mem | awk '{print (\\$3/\\$2)*100}'\""
    )
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            lines = res.stdout.strip().split('\n')
            if len(lines) >= 2:
                cpu = round(float(lines[0]), 2)
                mem = round(float(lines[1]), 2)
                return cpu, mem
    except Exception as e:
        logger.error(f"Error polling VM metrics over SSH: {e}")
    return None, None

def get_vm_metrics(project_id="cyber-sherpa-trading", instance_name="cyber-sherpa-vps", minutes=5):
    """
    Legacy method kept for compatibility. Returns real-time metrics in list format.
    """
    cpu, mem = get_vm_realtime_metrics()
    now = time.time()
    return {
        "cpu": [{"timestamp": now, "value": cpu}] if cpu is not None else [],
        "memory": [{"timestamp": now, "value": mem}] if mem is not None else []
    }

if __name__ == "__main__":
    print("Testing real-time VM metric collection over SSH...")
    cpu, mem = get_vm_realtime_metrics()
    print(f"Current VPS State -> CPU: {cpu}%, Memory: {mem}%")
