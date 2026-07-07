import os
import sys
import json
import time
import subprocess
import threading
from flask import Flask, jsonify, request, send_from_directory
from monitor_gcp import get_vm_metrics

app = Flask(__name__, static_folder='static')

# Base directory for absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Create necessary directories
os.makedirs(os.path.join(BASE_DIR, "static", "screenshots"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

CONFIG_PATH = os.path.join(BASE_DIR, "data", "load_test_config.json")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "test_history.json")

DEFAULT_CONFIG = {
    "target_url": "https://bot.metaversesherpa.io",
    "concurrency": 5,
    "duration": 60,
    "ramp_up": 10,
    "premium_ratio": 0.2,
    "max_active_browsers": 4,
    "routes": [
        {"path": "/register", "action": "navigate", "screenshot": True},
        {"path": "/dashboard", "action": "navigate", "screenshot": True},
        {"path": "/stats", "action": "navigate", "screenshot": True},
        {"path": "/settings", "action": "navigate", "screenshot": True}
    ]
}

# State management
test_state = {
    "status": "idle", # idle, running, completed, error
    "start_time": 0,
    "end_time": 0,
    "active_workers": 0,
    "success_count": 0,
    "failure_count": 0,
    "latencies": [], # list of {timestamp, path, latency}
    "errors": [],    # list of {timestamp, worker_id, path, error}
    "gcp_metrics": {"cpu": [], "memory": []},
    "screenshots": [] # list of {worker_id, step, path, file}
}

generator_process = None
monitor_thread = None
stop_monitor_event = threading.Event()

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

def save_run_to_history():
    """Saves the completed test state summary to the history JSON file."""
    history = []
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, 'r') as f:
                history = json.load(f)
        except Exception:
            pass
            
    run_summary = {
        "id": f"run_{int(test_state['start_time'])}",
        "timestamp": test_state["start_time"],
        "duration": round(test_state["end_time"] - test_state["start_time"], 2),
        "status": test_state["status"],
        "success_count": test_state["success_count"],
        "failure_count": test_state["failure_count"],
        "latencies_count": len(test_state["latencies"]),
        "errors": test_state["errors"],
        "screenshots_count": len(test_state["screenshots"]),
        "peak_cpu": max([p["value"] for p in test_state["gcp_metrics"]["cpu"]], default=0.0),
        "peak_memory": max([p["value"] for p in test_state["gcp_metrics"]["memory"]], default=0.0)
    }
    
    history.append(run_summary)
    history = history[-10:] # Store last 10 runs
    
    try:
        with open(HISTORY_PATH, 'w') as f:
            json.dump(history, f, indent=4)
    except Exception:
        pass

def run_gcp_monitor_loop(stop_event, run_start_time):
    """
    Periodically queries GCP VM metrics in real-time via SSH.
    """
    from monitor_gcp import get_vm_realtime_metrics
    
    while not stop_event.is_set():
        cpu, mem = get_vm_realtime_metrics()
        now = time.time()
        
        if cpu is not None:
            test_state["gcp_metrics"]["cpu"].append({"timestamp": now, "value": cpu})
        if mem is not None:
            test_state["gcp_metrics"]["memory"].append({"timestamp": now, "value": mem})
            
        for _ in range(2):
            if stop_event.is_set():
                break
            time.sleep(1)

def run_load_generator_subprocess(config):
    global generator_process, monitor_thread
    
    config_str = json.dumps({
        **config,
        "screenshots_dir": os.path.join(BASE_DIR, "static", "screenshots")
    })
    
    test_state["status"] = "running"
    test_state["start_time"] = time.time()
    test_state["end_time"] = 0
    test_state["active_workers"] = 0
    test_state["success_count"] = 0
    test_state["failure_count"] = 0
    test_state["latencies"] = []
    test_state["errors"] = []
    test_state["screenshots"] = []
    test_state["gcp_metrics"] = {"cpu": [], "memory": []}
    
    stop_monitor_event.clear()
    monitor_thread = threading.Thread(target=run_gcp_monitor_loop, args=(stop_monitor_event, test_state["start_time"]))
    monitor_thread.daemon = True
    monitor_thread.start()
    
    try:
        python_bin = os.path.abspath("venv/bin/python")
        generator_process = subprocess.Popen(
            [python_bin, os.path.join(BASE_DIR, "load_generator.py"), "--config", config_str],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        for line in generator_process.stdout:
            try:
                data = json.loads(line.strip())
                evt_type = data.get("type")
                details = data.get("details", {})
                
                if evt_type == "worker_start":
                    test_state["active_workers"] += 1
                elif evt_type == "worker_success":
                    test_state["success_count"] += 1
                    test_state["active_workers"] = max(0, test_state["active_workers"] - 1)
                elif evt_type == "worker_failure":
                    test_state["failure_count"] += 1
                    test_state["active_workers"] = max(0, test_state["active_workers"] - 1)
                    test_state["errors"].append({
                        "timestamp": data.get("timestamp"),
                        "worker_id": details.get("worker_id"),
                        "path": details.get("path", "unknown"),
                        "error": details.get("error"),
                        "console": details.get("console", "")
                    })
                elif evt_type == "latency":
                    test_state["latencies"].append({
                        "timestamp": data.get("timestamp"),
                        "worker_id": details.get("worker_id"),
                        "path": details.get("path"),
                        "latency": details.get("latency")
                    })
                elif evt_type in ("screenshot", "screenshot_error"):
                    filepath = details.get("file", "")
                    relative_path = filepath.split("static/")[-1] if "static/" in filepath else filepath
                    test_state["screenshots"].append({
                        "worker_id": details.get("worker_id"),
                        "step": details.get("step", "error"),
                        "path": details.get("path"),
                        "url": f"/static/{relative_path}",
                        "is_error": evt_type == "screenshot_error",
                        "console": details.get("console", "")
                    })
            except Exception:
                pass
                
        generator_process.wait()
        test_state["status"] = "completed" if generator_process.returncode == 0 else "error"
    except Exception as e:
        test_state["status"] = "error"
        test_state["errors"].append({
            "timestamp": time.time(),
            "worker_id": "system",
            "path": "system",
            "error": str(e)
        })
    finally:
        test_state["end_time"] = time.time()
        stop_monitor_event.set()
        if monitor_thread:
            monitor_thread.join(timeout=2)
        save_run_to_history()

@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "templates"), "index.html")

@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(os.path.join(BASE_DIR, "static"), path)

@app.route("/api/config", methods=["GET", "POST"])
def manage_config():
    if request.method == "POST":
        config = request.json
        save_config(config)
        return jsonify({"message": "Configuration saved", "config": config})
    return jsonify(load_config())

@app.route("/api/start", methods=["POST"])
def start_test():
    if test_state["status"] == "running":
        return jsonify({"error": "A load test is already running"}), 400
        
    config = load_config()
    t = threading.Thread(target=run_load_generator_subprocess, args=(config,))
    t.daemon = True
    t.start()
    return jsonify({"message": "Load test initiated"})

@app.route("/api/stop", methods=["POST"])
def stop_test():
    global generator_process
    if test_state["status"] != "running":
        return jsonify({"message": "No test currently running"})
        
    if generator_process:
        generator_process.terminate()
        generator_process.wait()
        
    # Force kill any lingering chrome processes spawned by playwright
    try:
        # pkill -f matches full command lines including chromium/playwright
        subprocess.run("pkill -f -9 chromium", shell=True)
        subprocess.run("pkill -f -9 playwright", shell=True)
    except Exception:
        pass
        
    stop_monitor_event.set()
    test_state["status"] = "idle"
    save_run_to_history()
    return jsonify({"message": "Load test stopped and browser processes forcefully killed"})

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify(test_state)

@app.route("/api/history", methods=["GET"])
def get_history():
    history = []
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, 'r') as f:
                history = json.load(f)
        except Exception:
            pass
    return jsonify(history)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting load tester dashboard on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
