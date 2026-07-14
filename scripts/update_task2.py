import re

with open("/Users/johngiles/.gemini/antigravity-ide/brain/f920f101-aa91-4266-a1e2-24a6fd468eee/task.md", "r") as f:
    content = f.read()

for i in range(6, 10):
    content = content.replace(f"- [ ] {i}", f"- [x] {i}")

with open("/Users/johngiles/.gemini/antigravity-ide/brain/f920f101-aa91-4266-a1e2-24a6fd468eee/task.md", "w") as f:
    f.write(content)

