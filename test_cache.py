from web_api.db_web import _USER_BY_EMAIL_CACHE, invalidate_cache_by_user_id, get_web_user_by_email, update_web_user_preferences
print("Before:", _USER_BY_EMAIL_CACHE)
user = get_web_user_by_email("metaversesherpa@gmail.com")
print("After fetch:", _USER_BY_EMAIL_CACHE.keys())
invalidate_cache_by_user_id(user["id"])
print("After invalidate:", _USER_BY_EMAIL_CACHE.keys())
