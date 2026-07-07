import sys
sys.path.append('.')
from database import db_session
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT id, symbol, category FROM PortfolioPositions")
    print(c.fetchall())
