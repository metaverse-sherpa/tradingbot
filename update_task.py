import re

with open("/Users/johngiles/.gemini/antigravity-ide/brain/f920f101-aa91-4266-a1e2-24a6fd468eee/task.md", "r") as f:
    content = f.read()

content = content.replace("- [ ] 1", "- [x] 1")
content = content.replace("- [ ] 2", "- [x] 2")
content = content.replace("- [ ] 3", "- [x] 3")

with open("/Users/johngiles/.gemini/antigravity-ide/brain/f920f101-aa91-4266-a1e2-24a6fd468eee/task.md", "w") as f:
    f.write(content)
