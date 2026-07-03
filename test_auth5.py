import database
from web_api import db_web

email = "gilesasp@gmail.com"
user = db_web.get_web_user_by_email(email)
if user:
    print("KEYS:", list(user.keys()))
    print("api_key in keys?", "api_key" in user)
    print("value:", user.get("api_key"))
else:
    print("USER IS NONE")
