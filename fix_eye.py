with open("webapp/app.js", "r") as f:
    content = f.read()

old_class = 'class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center text-on-surface-variant hover:text-white transition-colors"'
new_class = 'class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);"'

content = content.replace(old_class, new_class)

with open("webapp/app.js", "w") as f:
    f.write(content)
print("Done!")
