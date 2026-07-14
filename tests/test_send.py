import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
photo_path = os.path.join(BASE_DIR, "assets", "premium_infographic.png")
print("Photo Path:", photo_path)
print("Exists?", os.path.exists(photo_path))
