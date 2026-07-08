import time
from database import db_session

def delete_mock_signal():
    with db_session() as session:
        sql = "DELETE FROM theoreticaltrades WHERE symbol = %s AND strategy = %s"
        params = ("ASST", "Mock Strategy")
        session.execute(sql, params)
        session.commit()
        print("Deleted mock signal for ASST")

if __name__ == "__main__":
    delete_mock_signal()
