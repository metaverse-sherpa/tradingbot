import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from web_api.routes_portfolio import call_gemini

try:
    print(call_gemini("Test prompt"))
except Exception as e:
    print(f"Exception: {e}")
