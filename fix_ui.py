import re

with open("webapp/app.js", "r") as f:
    content = f.read()

# Helper function to wrap password inputs
def wrap_password_input(match):
    full_input = match.group(0)
    id_match = re.search(r'id="([^"]+)"', full_input)
    if not id_match:
        return full_input
    input_id = id_match.group(1)
    
    # We only care about auth passwords
    if input_id not in ['login-password', 'reg-password', 'reg-password-confirm', 'reset-password', 'reset-password-confirm']:
        return full_input
        
    # Replace px-4 with pl-4 pr-12
    new_input = full_input.replace('px-4', 'pl-4 pr-12')
    
    wrapper = f"""<div class="relative w-full">
                                    {new_input}
                                    <button type="button" onclick="togglePasswordVisibility('{input_id}', this)" class="absolute right-0 top-0 h-full px-3 flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>"""
    # Fix indentation based on original
    return wrapper

# Replace all password inputs
content = re.sub(r'<input[^>]*type="password"[^>]*>', wrap_password_input, content)

# Add togglePasswordVisibility function if not exists
if "function togglePasswordVisibility" not in content:
    js_func = """
window.togglePasswordVisibility = function(inputId, btnElement) {
    const input = document.getElementById(inputId);
    const icon = btnElement.querySelector('span');
    if (input.type === 'password') {
        input.type = 'text';
        icon.innerText = 'visibility_off';
    } else {
        input.type = 'password';
        icon.innerText = 'visibility';
    }
};
"""
    content += js_func

with open("webapp/app.js", "w") as f:
    f.write(content)

with open("web_api/email_service.py", "r") as f:
    email_content = f.read()

email_content = email_content.replace('"from": SMTP_SENDER_EMAIL or "Metaverse Sherpa <alerts@metaversesherpa.io>",', '"from": "Metaverse Sherpa Bot Alerts <" + (SMTP_SENDER_EMAIL or "alerts@metaversesherpa.io") + ">",')

with open("web_api/email_service.py", "w") as f:
    f.write(email_content)
    
print("Done!")
