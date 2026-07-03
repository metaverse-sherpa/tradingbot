import database
from web_api.db_web import update_web_user_keys, get_web_user_by_email

user = get_web_user_by_email("gilesasp@gmail.com")
if user:
    update_web_user_keys(user["id"], "blofin", "DUMMY_KEY", "DUMMY_SECRET", "")
    print("Updated keys for gilesasp@gmail.com")
