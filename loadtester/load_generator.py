import asyncio
import os
import sys
import json
import time
import random
import subprocess
import argparse
from playwright.async_api import async_playwright

# Setup simple stdout logger for communicating with Flask backend
def log_event(event_type, details):
    print(json.dumps({
        "timestamp": time.time(),
        "type": event_type,
        "details": details
    }), flush=True)

# Helper to promote a user to premium via SSH database update on VPS
def promote_to_premium(email):
    # Update premium status in the new live PostgreSQL database instead of the old SQLite file
    cmd = (
        f"ssh -o StrictHostKeyChecking=no johngiles@35.208.90.255 "
        f"\"PGPASSWORD=0018c695559ba14b172d08308b45c071 psql -U sherpa_admin -d sherpa_prod -h 127.0.0.1 "
        f"-c \\\"UPDATE webusers SET premium_expiry = {int(time.time()) + 864000} WHERE email = '{email}';\\\"\""
    )
    try:
        log_event("info", f"Attempting to promote {email} to premium via PostgreSQL SSH...")
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            log_event("info", f"Successfully promoted {email} to premium in Postgres.")
            return True
        else:
            log_event("error", f"Failed to promote {email}. PostgreSQL/SSH error: {res.stderr.strip()}")
            return False
    except Exception as e:
        log_event("error", f"Exception promoting user: {e}")
        return False

async def run_worker(worker_id, target_url, routes, is_premium, screenshots_dir, semaphore):
    """
    Simulates a single virtual user executing a sequence of routes/actions.
    Uses a semaphore to throttle concurrent Chrome execution on low-spec host CPUs.
    """
    async with semaphore:
        # Generate unique user details
        unique_suffix = f"{int(time.time() * 1000) % 1000000}_{worker_id}"
        email = f"user_{unique_suffix}@metaversesherpa.io"
        name = f"LoadTester User {unique_suffix}"
        password = "TestPassword123!"

        async with async_playwright() as p:
            # Optimize launch arguments to utilize less CPU/RAM
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--single-process",
                    "--js-flags=--max-old-space-size=256"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            console_logs = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: console_logs.append(f"[pageerror] {err}"))

            log_event("worker_start", {"worker_id": worker_id, "email": email, "is_premium": is_premium})

            current_path = "unknown"
            try:
                for idx, route in enumerate(routes):
                    path = route.get("path", "")
                    current_path = path
                    action = route.get("action", "navigate")
                    full_url = f"{target_url.rstrip('/')}{path}"
                    
                    if action == "navigate":
                        log_event("worker_step", {"worker_id": worker_id, "step": idx, "action": "navigate", "path": path})
                        start_time = time.time()
                        
                        if path == "/#/register" or path == "/register":
                            await page.goto(full_url, wait_until="domcontentloaded")
                            await page.wait_for_selector("#reg-email", timeout=10000)
                            
                            await page.fill("#reg-name", name)
                            await page.fill("#reg-email", email)
                            await page.fill("#reg-password", password)
                            await page.fill("#reg-password-confirm", password)
                            
                            await page.click("form#register-form button[type='submit']")
                            try:
                                await page.wait_for_function("() => window.location.hash.includes('dashboard') || localStorage.getItem('session_token') !== null", timeout=30000)
                            except Exception as e:
                                error_text = await page.evaluate("() => { const err = document.querySelector('.toast, .alert, .error-message, .text-danger, .text-red-500'); return err ? err.innerText : 'No visible UI error found'; }")
                                raise Exception(f"Registration Timeout exceeded. UI Error context: {error_text}")
                            
                            if is_premium:
                                promote_to_premium(email)
                                await page.reload(wait_until="domcontentloaded")
                                await page.wait_for_timeout(1000)
                        
                        elif path == "/#/login" or path == "/login":
                            await page.goto(full_url, wait_until="domcontentloaded")
                            await page.wait_for_selector("#login-email", timeout=10000)
                            await page.fill("#login-email", email)
                            await page.fill("#login-password", password)
                            await page.click("form#login-form button[type='submit']")
                            try:
                                await page.wait_for_function("() => window.location.hash.includes('dashboard')", timeout=30000)
                            except Exception as e:
                                error_text = await page.evaluate("() => { const err = document.querySelector('.toast, .alert, .error-message, .text-danger, .text-red-500'); return err ? err.innerText : 'No visible UI error found'; }")
                                raise Exception(f"Login Timeout exceeded. UI Error context: {error_text}")
                        
                        else:
                            await page.goto(full_url, wait_until="domcontentloaded")
                            await page.wait_for_selector("#app", timeout=15000)
                        
                        latency = time.time() - start_time
                        log_event("latency", {"worker_id": worker_id, "path": path, "latency": latency})

                    elif action == "click":
                        selector = route.get("selector", "")
                        log_event("worker_step", {"worker_id": worker_id, "step": idx, "action": "click", "selector": selector})
                        start_time = time.time()
                        await page.click(selector)
                        await page.wait_for_timeout(500)
                        latency = time.time() - start_time
                        # Record latency under the action type + selector
                        log_event("latency", {"worker_id": worker_id, "path": f"Click: {selector}", "latency": latency})

                    elif action == "wait":
                        duration = float(route.get("duration", 1))
                        log_event("worker_step", {"worker_id": worker_id, "step": idx, "action": "wait", "duration": duration})
                        start_time = time.time()
                        await page.wait_for_timeout(int(duration * 1000))
                        latency = time.time() - start_time
                        log_event("latency", {"worker_id": worker_id, "path": f"Wait: {duration}s", "latency": latency})

                    elif action == "wait_for_selector":
                        selector = route.get("selector", "")
                        timeout = int(route.get("timeout", 30000))
                        log_event("worker_step", {"worker_id": worker_id, "step": idx, "action": "wait_for_selector", "selector": selector})
                        start_time = time.time()
                        await page.wait_for_selector(selector, timeout=timeout)
                        latency = time.time() - start_time
                        log_event("latency", {"worker_id": worker_id, "path": f"Wait for selector: {selector}", "latency": latency})

                    if route.get("screenshot", False) or idx == len(routes) - 1:
                        screenshot_path = os.path.join(screenshots_dir, f"worker_{worker_id}_step_{idx}_{int(time.time())}.png")
                        await page.screenshot(path=screenshot_path)
                        log_event("screenshot", {"worker_id": worker_id, "step": idx, "path": path, "file": screenshot_path})

                log_event("worker_success", {"worker_id": worker_id})
            except Exception as e:
                error_screenshot_path = os.path.join(screenshots_dir, f"error_worker_{worker_id}_{int(time.time())}.png")
                try:
                    await page.screenshot(path=error_screenshot_path)
                    log_event("screenshot_error", {"worker_id": worker_id, "path": current_path, "file": error_screenshot_path, "console": "\n".join(console_logs)})
                except Exception:
                    pass
                log_event("worker_failure", {"worker_id": worker_id, "error": str(e), "path": current_path, "console": "\n".join(console_logs)})
            finally:
                await context.close()
                await browser.close()

async def main():
    parser = argparse.ArgumentParser(description="Asynchronous load generator using Playwright")
    parser.add_argument("--config", type=str, required=True, help="JSON config string or filepath")
    args = parser.parse_args()

    try:
        if os.path.exists(args.config):
            with open(args.config, 'r') as f:
                config = json.load(f)
        else:
            config = json.loads(args.config)
    except Exception as e:
        print(f"Error parsing config: {e}", file=sys.stderr)
        sys.exit(1)

    target_url = config.get("target_url", "https://bot.metaversesherpa.io")
    concurrency = int(config.get("concurrency", 5))
    duration = int(config.get("duration", 60))
    ramp_up = int(config.get("ramp_up", 10))
    routes = config.get("routes", [])
    premium_ratio = float(config.get("premium_ratio", 0.2))
    
    screenshots_dir = config.get("screenshots_dir", "static/screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    log_event("test_init", {
        "target_url": target_url,
        "concurrency": concurrency,
        "duration": duration,
        "ramp_up": ramp_up,
        "routes": routes,
        "premium_ratio": premium_ratio
    })

    # Allow customizable concurrency throttle for active browsers running in parallel to prevent Mac CPU overloading
    max_active_browsers = int(config.get("max_active_browsers", 4))
    semaphore = asyncio.Semaphore(max_active_browsers)

    tasks = []
    step_delay = ramp_up / max(concurrency - 1, 1)

    for i in range(concurrency):
        # Force all simulated load test accounts to premium to test charts and backtests
        is_premium = True
        
        async def delayed_launch(wid, prem):
            if wid > 0 and step_delay > 0:
                await asyncio.sleep(wid * step_delay)
            await run_worker(wid, target_url, routes, prem, screenshots_dir, semaphore)

        tasks.append(delayed_launch(i, is_premium))

    await asyncio.gather(*tasks)
    log_event("test_complete", {})

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
