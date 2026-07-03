import os
import logging
import time
from google.cloud import secretmanager
from dotenv import load_dotenv

# Ensure local .env is loaded before any secret resolution to prevent GCP timeouts in local/VPS environments
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

logger = logging.getLogger("SecretManager")

# In-memory cache to share keys across the application and avoid network round-trips
_secrets_cache = {}

def get_secret(secret_id, project_id="cyber-sherpa-trading", fallback_env_key=None):
    """
    Fetches a secret from Google Cloud Secret Manager first.
    If it fails (e.g., running locally without gcloud auth or secret not found),
    it gracefully falls back to os.getenv().
    If both fail, it sends a Telegram alert to the administrator.
    Uses an in-memory cache to eliminate round-trips.
    """
    if fallback_env_key is None:
        fallback_env_key = secret_id.replace('-', '_').upper()
        
    # Check cache first
    if secret_id in _secrets_cache:
        return _secrets_cache[secret_id]
        
    val = None
    gcp_failed = False
    gcp_error_msg = ""
        
    # Try to fetch from GCP Secret Manager with retries
    max_retries = 3
    retry_delay = 1
    for attempt in range(max_retries):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name}, timeout=10.0)
            val = response.payload.data.decode("UTF-8")
            break
        except Exception as e:
            gcp_error_msg = str(e)
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed to fetch '{secret_id}' from GCP: {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.warning(f"Could not fetch '{secret_id}' from GCP after {max_retries} attempts: {e}. Falling back to .env...")
                gcp_failed = True
            
    if not val:
        val = os.getenv(fallback_env_key)
        
    if val:
        _secrets_cache[secret_id] = val
        return val
        
    error_desc = f"Failed to retrieve secret '{secret_id}' (Env: {fallback_env_key}) from both GCP Secret Manager and local .env."
    if gcp_failed and gcp_error_msg:
        error_desc += f" GCP Error: {gcp_error_msg}"
        
    logger.error(error_desc)
    
    if secret_id != "TELEGRAM_BOT_TOKEN":
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert(f"SecretManager/Env ({secret_id})", error_desc)
        except Exception as alert_err:
            logger.error(f"Failed to send Telegram alert: {alert_err}")
            
    return None


