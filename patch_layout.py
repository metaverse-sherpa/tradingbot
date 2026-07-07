import re

with open("webapp-react/src/components/Layout.tsx", "r") as f:
    content = f.read()

content = content.replace(
    "flex items-center justify-start md:justify-center gap-1 md:gap-2",
    "flex items-center justify-center gap-1 md:gap-2"
)

with open("webapp-react/src/components/Layout.tsx", "w") as f:
    f.write(content)

