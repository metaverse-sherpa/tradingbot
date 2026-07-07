import re

# Update Settings.tsx
with open("webapp-react/src/components/Settings.tsx", "r") as f:
    settings = f.read()

settings = settings.replace("value={giftResult.web_gift_url}", "value={`${window.location.origin}/?gift=${giftResult.code}`}")
settings = settings.replace('copyToClipboard(giftResult.web_gift_url, "Web link")', 'copyToClipboard(`${window.location.origin}/?gift=${giftResult.code}`, "Web link")')

with open("webapp-react/src/components/Settings.tsx", "w") as f:
    f.write(settings)

# Update ReferralsPage.tsx
with open("webapp-react/src/components/ReferralsPage.tsx", "r") as f:
    referrals = f.read()

# Replace the referral_url property which might be hardcoded from backend
# Wait, let's look at ReferralsPage.tsx first to see the exact variable names
