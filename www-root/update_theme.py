import os
import re

filepath = "/Users/johngiles/projects/metaversesherpa/index.html"
with open(filepath, "r") as f:
    html = f.read()

# 1. Update Logo
old_logo = '<img src="https://lh3.googleusercontent.com/aida-public/AB6AXuCeFw4UWcGnXNh8L0fqCiA6LrgVT472mj1YXt-18hJvZQQXka7hFZGOvN9PJX9DNhd-7wePS7H7wBvKYUvH9UJLdsho8pyTxc-lfV5O_tt2Q_tK3F2z0aFfvNxfVAZo_486hlilr60-WEk8Y75KX-6VW2pyXqyoxIO-Rku0XuabD4fYYH_lkuJwdvt37I8yhP1HgjOYWO_SJwhJ6ZGqvcIMM6s26Zz2sF404MsrWBOYLEY-nNDW4hreZYdZYrAReeiKrXDxWLPUvZKU" alt="Metaverse Sherpa Logo" class="h-8 w-auto">'
new_logo = '<img src="images/favicon.svg" alt="Metaverse Sherpa Logo" class="w-8 h-8">'
html = html.replace(old_logo, new_logo)

# 2. Update Tailwind Config colors
color_replacements = {
    '"primary": "#c6c6ca"': '"primary": "#ffffff"',
    '"secondary": "#e9c349"': '"secondary": "#3cd7ff"',
    '"tertiary": "#68dba9"': '"tertiary": "#0099ff"',
    '"background": "#131316"': '"background": "#0f131f"',
    '"surface": "#131316"': '"surface": "#131620"',
    '"surface-container-lowest": "#0e0e11"': '"surface-container-lowest": "#0f131f"',
    '"surface-variant": "#353437"': '"surface-variant": "#1f2028"',
}

for old, new in color_replacements.items():
    html = html.replace(old, new)

# 3. Update Fonts
# The user wants fonts to match the bot (which uses system sans). We'll remove custom fonts to let tailwind fall back to standard fonts
html = re.sub(r'"fontFamily":\s*\{[^}]+\},?', '', html)

# 4. Update the "Access the Terminal" buttons to use the bot gradient
old_btn1 = 'bg-surface-variant text-secondary border border-secondary/30 hover:bg-secondary/10 px-4 py-2 rounded font-label-caps text-xs transition-all uppercase tracking-wider'
new_btn1 = 'bg-gradient-to-r from-secondary to-tertiary text-white font-bold rounded-xl shadow-lg hover:shadow-secondary/25 transition-all hover:-translate-y-0.5 px-4 py-2 text-xs uppercase tracking-wider'
html = html.replace(old_btn1, new_btn1)

old_btn2 = 'bg-surface-container-lowest text-secondary border border-secondary font-label-caps text-label-caps uppercase py-4 px-8 hover:bg-secondary hover:text-on-secondary transition-all text-center tracking-wider'
new_btn2 = 'bg-gradient-to-r from-secondary to-tertiary text-white font-bold rounded-xl shadow-lg hover:shadow-secondary/25 transition-all hover:-translate-y-0.5 py-4 px-8 text-center uppercase tracking-wider'
html = html.replace(old_btn2, new_btn2)

with open(filepath, "w") as f:
    f.write(html)
print("Updated index.html theme successfully.")
