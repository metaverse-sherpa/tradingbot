import sys
import os
import logging
logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.abspath("."))
from web_api.email_service import _send_email_thread

reset_url = "https://bot.metaversesherpa.io/#/reset-password?token=test-token-123"
html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #0c1f30; color: #fff; padding: 20px; border-radius: 10px;">
    <h2 style="color: #3cd7ff;">Password Reset Request</h2>
    <p>You requested a password reset for Metaverse Sherpa.</p>
    <p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: #3cd7ff; color: #000; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 10px;">Reset Your Password</a></p>
    <p style="margin-top: 20px; font-size: 12px; color: #888;">If you didn't request this, you can safely ignore this email. The link will expire in 1 hour.</p>
</div>
"""

print("Sending test email to sherpa@metaversesherpa.io synchronously...")
_send_email_thread("sherpa@metaversesherpa.io", "Metaverse Sherpa Password Reset", html)
print("Done!")
