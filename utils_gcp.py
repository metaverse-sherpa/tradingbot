import os
import logging
import time
from google.cloud import secretmanager
from dotenv import load_dotenv

# Ensure local .env is loaded before any secret resolution to prevent GCP timeouts in local/VPS environments
load_dotenv()

logger = logging.getLogger("SecretManager")

# In-memory cache to share keys across the application and avoid network round-trips
_secrets_cache = {}

def get_secret(secret_id, project_id="cyber-sherpa-trading", fallback_env_key=None):
    """
    Fetches a secret from Google Cloud Secret Manager.
    If it fails (e.g., running locally without gcloud auth), it gracefully
    falls back to os.getenv(). Uses an in-memory cache to eliminate GCP round-trips.
    """
    if fallback_env_key is None:
        fallback_env_key = secret_id.replace('-', '_').upper()
        
    # Check cache first
    if secret_id in _secrets_cache:
        return _secrets_cache[secret_id]
        
    # Priority 1: Check local environment variable first to bypass GCP overhead in local dev
    val = os.getenv(fallback_env_key)
    if val:
        _secrets_cache[secret_id] = val
        return val
        
    # Try to fetch from GCP Secret Manager with retries
    max_retries = 3
    retry_delay = 1
    for attempt in range(max_retries):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name}, timeout=10.0)
            payload = response.payload.data.decode("UTF-8")
            _secrets_cache[secret_id] = payload
            return payload
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed to fetch '{secret_id}' from GCP: {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(f"Could not fetch '{secret_id}' from GCP after {max_retries} attempts (timeout/failure - falling back to .env): {e}")
                if secret_id != "TELEGRAM_BOT_TOKEN":
                    try:
                        from utils_error import send_telegram_alert
                        send_telegram_alert(f"SecretManager ({secret_id})", e)
                    except Exception as alert_err:
                        logger.error(f"Failed to send Telegram alert for SecretManager failure: {alert_err}")
            
    val = os.getenv(fallback_env_key)
    if not val:
        logger.error(f"Failed to find {fallback_env_key} in local .env as well.")
        if secret_id != "TELEGRAM_BOT_TOKEN":
            try:
                from utils_error import send_telegram_alert
                send_telegram_alert(f"SecretManager/Env ({secret_id})", f"Failed to find {fallback_env_key} in GCP or local .env")
            except Exception as alert_err:
                logger.error(f"Failed to send Telegram alert: {alert_err}")
    if val:
        _secrets_cache[secret_id] = val
    return val

