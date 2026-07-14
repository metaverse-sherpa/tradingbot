import utils_gcp
import psycopg2

def test_conn():
    url = utils_gcp.get_secret("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL is not set or couldn't be loaded from secrets.")
        return
    print(f"Connecting to database using url retrieved from GCP secrets...")
    try:
        conn = psycopg2.connect(url)
        print("Success! PostgreSQL connection established.")
        conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_conn()
