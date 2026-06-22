import os
import logging
from google.cloud import secretmanager
from dotenv import load_dotenv

# Ensure local .env is loaded before any secret resolution to prevent GCP timeouts in local/VPS environments
load_dotenv()

logger = logging.getLogger("SecretManager")

# In-memory cache to share keys across the application and avoid network round-trips
_secrets_cache = {}
_gcp_failed = False

def get_secret(secret_id, project_id="cyber-sherpa-trading", fallback_env_key=None):
    """
    Fetches a secret from Google Cloud Secret Manager.
    If it fails (e.g., running locally without gcloud auth), it gracefully
    falls back to os.getenv(). Uses an in-memory cache to eliminate GCP round-trips.
    """
    global _gcp_failed
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
        
    if not _gcp_failed:
        try:
            # Try to fetch from GCP Secret Manager
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name}, timeout=10.0)
            payload = response.payload.data.decode("UTF-8")
            _secrets_cache[secret_id] = payload
            return payload
        except Exception as e:
            # Graceful fallback to local .env
            _gcp_failed = True
            logger.warning(f"Could not fetch '{secret_id}' from GCP (timeout/failure - falling back to .env): {e}")
            
    val = os.getenv(fallback_env_key)
    if not val:
        logger.error(f"Failed to find {fallback_env_key} in local .env as well.")
    if val:
        _secrets_cache[secret_id] = val
    return val
