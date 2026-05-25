import os
import logging
from google.cloud import secretmanager

logger = logging.getLogger("SecretManager")

def get_secret(secret_id, project_id="cyber-sherpa-trading", fallback_env_key=None):
    """
    Fetches a secret from Google Cloud Secret Manager.
    If it fails (e.g., running locally without gcloud auth), it gracefully
    falls back to os.getenv().
    """
    if fallback_env_key is None:
        fallback_env_key = secret_id.replace('-', '_').upper()
        
    try:
        # Try to fetch from GCP Secret Manager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        return payload
    except Exception as e:
        # Graceful fallback to local .env
        logger.warning(f"Could not fetch '{secret_id}' from GCP (falling back to .env): {e}")
        val = os.getenv(fallback_env_key)
        if not val:
            logger.error(f"Failed to find {fallback_env_key} in local .env as well.")
        return val
