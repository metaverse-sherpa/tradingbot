import database
from web_api import db_web

email = "gilesasp@gmail.com"
user = db_web.get_web_user_by_email(email)
print("api_key raw:", user.get("api_key") if user else "user is None")
