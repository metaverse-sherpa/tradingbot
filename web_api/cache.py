import threading

# Thread-safe in-memory cache for slow external API responses
RESPONSE_CACHE = {}  # Format: { (cache_type, user_id): (expiry_timestamp, data) }
RESPONSE_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds
