import os
import re

filepath = "/Users/johngiles/projects/metaversesherpa/index.html"

with open(filepath, "r") as f:
    content = f.read()

# Replace py-24 with py-12 md:py-24 for mobile tightening
content = content.replace('class="py-24', 'class="py-12 md:py-24')

# Replace mb-16 with mb-8 md:mb-16 for mobile tightening
content = content.replace('class="mb-16', 'class="mb-8 md:mb-16')
content = content.replace('class="text-center mb-16', 'class="text-center mb-8 md:mb-16')

# Replace grid-bg with starry background
old_grid_bg = """        .grid-bg {
            background-image: 
                linear-gradient(to right, rgba(255,255,255,0.015) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255,255,255,0.015) 1px, transparent 1px);
            background-size: 24px 24px;
        }"""

new_grid_bg = """        .grid-bg {
            background-image: 
                radial-gradient(1px 1px at 20px 30px, rgba(255,255,255,0.8), transparent),
                radial-gradient(1px 1px at 40px 70px, rgba(255,255,255,0.8), transparent),
                radial-gradient(1px 1px at 50px 160px, rgba(255,255,255,0.8), transparent),
                radial-gradient(1.5px 1.5px at 90px 40px, rgba(255,255,255,1), transparent),
                radial-gradient(1.5px 1.5px at 130px 80px, rgba(255,255,255,1), transparent),
                radial-gradient(2px 2px at 160px 120px, rgba(255,255,255,0.5), transparent),
                radial-gradient(1px 1px at 180px 180px, rgba(255,255,255,0.8), transparent);
            background-repeat: repeat;
            background-size: 200px 200px;
        }"""

content = content.replace(old_grid_bg, new_grid_bg)

with open(filepath, "w") as f:
    f.write(content)

print("Updated index.html successfully.")
