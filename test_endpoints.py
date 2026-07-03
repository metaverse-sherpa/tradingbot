import time
import requests

def test_endpoint(url):
    start = time.time()
    try:
        r = requests.get(url, cookies={"session": "..."})  # We need auth?
    except Exception as e:
        print(e)
    end = time.time()
    print(f"{url}: {end - start:.2f}s")

# Actually, the API requires auth. I might not be able to hit it without a session cookie or auth token.
