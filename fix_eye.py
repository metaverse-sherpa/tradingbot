import re

with open("webapp/app.js", "r") as f:
    content = f.read()

old_class = 'class="absolute right-0 top-0 h-full px-3 flex items-center justify-center text-on-surface-variant hover:text-white transition-colors"'
new_class = 'class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center text-on-surface-variant hover:text-white transition-colors"'

content = content.replace(old_class, new_class)

with open("webapp/app.js", "w") as f:
    f.write(content)
print("Done!")
