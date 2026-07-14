import database
from web_api.db_web import get_web_user_by_email

user = get_web_user_by_email("gilesasp@gmail.com")
print(f"Original keys for gilesasp:")
print(user.get("api_key"))
print(database.decrypt(user.get("api_key")) if user.get("api_key") else "None")

