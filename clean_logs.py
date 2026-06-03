import re

def clean_media_gen():
    filepath = '/Users/johngiles/projects/tradingbot/media_gen.py'
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove PROFILE lines
    content = re.sub(r'^[ \t]*print\(f?"\[PROFILE\].*?$\n', '', content, flags=re.MULTILINE)
    
    # Remove optimize=True
    content = content.replace(', optimize=True', '')
    
    with open(filepath, 'w') as f:
        f.write(content)

def clean_routes():
    filepath = '/Users/johngiles/projects/tradingbot/web_api/routes_trades.py'
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove CARD DEBUG lines
    content = re.sub(r'^[ \t]*print\(f?"\[CARD DEBUG\].*?$\n', '', content, flags=re.MULTILINE)
    
    with open(filepath, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    clean_media_gen()
    clean_routes()
