import sys
import os

sys.path.append("/Users/johngiles/projects/tradingbot")
from db_adapter import db_session_adapter as db_session

with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT id, symbol, category FROM PortfolioPositions LIMIT 5;")
    for row in c.fetchall():
        print(row)
