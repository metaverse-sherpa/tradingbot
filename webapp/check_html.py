import re

html_content = open("webapp/app.js", "r").read()
spans = re.findall(r'<\/?span[^>]*>', html_content)
stack = []
for i, tag in enumerate(spans):
    if tag.startswith('</'):
        if not stack:
            print(f"Dangling closing span at index {i}: {tag}")
        else:
            stack.pop()
    else:
        stack.append(tag)

if stack:
    print(f"Unclosed spans found: {len(stack)}")
    for t in stack:
        print(t)
else:
    print("All spans matched.")
