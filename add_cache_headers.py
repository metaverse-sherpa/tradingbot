import re

with open("server.py", "r") as f:
    content = f.read()

if "def add_header(response):" not in content:
    header_code = """
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response
"""
    content = content.replace("app = Flask(__name__)", "app = Flask(__name__)\n" + header_code)
    
    with open("server.py", "w") as f:
        f.write(content)
    print("Added cache headers.")
else:
    print("Cache headers already exist.")
