import re

with open("webapp-react/src/components/ReferralsPage.tsx", "r") as f:
    content = f.read()

content = content.replace(
    "const inviteLink = user?.invite_link || `https://bot.metaversesherpa.io/#/register?ref=${refId}`;",
    "const inviteLink = `${window.location.origin}/?ref=${refId}`;"
)

with open("webapp-react/src/components/ReferralsPage.tsx", "w") as f:
    f.write(content)

