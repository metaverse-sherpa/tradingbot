import time
from database import db_session

def add_mock_signal():
    with db_session() as session:
        sql = """
            INSERT INTO theoreticaltrades 
            (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            "ASST",
            "Mock Strategy",
            "LONG",
            10.50,
            12.00,
            9.50,
            int(time.time()),
            "open"
        )
        session.execute(sql, params)
        session.commit()
        print("Inserted mock signal for ASST")

if __name__ == "__main__":
    add_mock_signal()
