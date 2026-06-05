import re

with open('app.js', 'r') as f:
    content = f.read()

func_match = re.search(r'(function renderSettingsView\(\) \{.*?\n\})', content, re.DOTALL)
if not func_match:
    print("Function not found")
    exit(1)

func_content = func_match.group(1)

def extract_section(start_comment_regex, end_regex):
    match = re.search(start_comment_regex + r'.*?' + end_regex, func_content, re.DOTALL)
    if match:
        return match.group(0)
    print(f"Failed to find {start_comment_regex}")
    return ""

premium_status = extract_section(r'<!-- Premium Status & Renew Option -->', r'</section>\n')
bot_status = extract_section(r'<!-- Bot Status Panel \(Gated to Premium Users Only\) -->', r'</section>\n\s*` : \'\'}')
connected_exchanges = extract_section(r'<!-- Connected Exchanges Summary -->', r'</section>\n\s*` : \'\'}')
connect_wizard = extract_section(r'<!-- Connect Exchange Wizard \(Premium Only\) -->', r'</section>\n\s*` : \'\'}')
telegram_sync = extract_section(r'<!-- Telegram Sync -->', r'</section>\n')
algo_strategies = extract_section(r'<!-- Algorithmic Strategies Dropdowns -->', r'</section>\n')
risk_sizing = extract_section(r'<!-- Risk Sizing Slider -->', r'</section>\n')
email_notif = extract_section(r'<!-- Email Notifications Setting -->', r'</section>\n')
browser_notif = extract_section(r'<!-- Browser Notifications Setting -->', r'</section>\n')
privacy_mode = extract_section(r'<!-- Privacy Mode Setting -->', r'</section>\n')
premium_plan = extract_section(r'<!-- Premium Plan & Referral Buttons -->', r'</section>\n')
admin_gifting = extract_section(r'<!-- Admin Gifting Center -->', r'</section>\n\s*` : \'\'}')

left_col = f"""
                <!-- LEFT COLUMN -->
                <div class="space-y-section-gap flex flex-col">
                    {premium_status}
                    {connected_exchanges}
                    {connect_wizard}
                    {telegram_sync}
                    {premium_plan}
                </div>
"""

right_col = f"""
                <!-- RIGHT COLUMN -->
                <div class="space-y-section-gap flex flex-col">
                    {bot_status}
                    {algo_strategies}
                    {risk_sizing}
                    {email_notif}
                    {browser_notif}
                    {privacy_mode}
                    {admin_gifting}
                </div>
"""

new_grid_content = f"""<div class="grid grid-cols-1 lg:grid-cols-2 gap-section-gap items-start">
{left_col}
{right_col}
            </div>"""

start_tag = r'<div class="grid grid-cols-1 lg:grid-cols-2 gap-section-gap items-start">'
end_tag = r'<!-- Logout Link -->'
old_grid_content = re.search(start_tag + r'.*?' + end_tag, func_content, re.DOTALL)

if old_grid_content:
    new_func = func_content.replace(old_grid_content.group(0), new_grid_content + '\n\n            ' + end_tag.replace('\\', ''))
    
    # Also need to remove the extra </div> that was left behind above the logout button, since new_grid_content has its own closing </div>
    # Let's just do a string replace on the specific part:
    new_func = new_func.replace('<!-- Logout Link -->\n            </div>\n            <button onclick="handleLogout()"', '<!-- Logout Link -->\n            <button onclick="handleLogout()"')

    new_app = content.replace(func_content, new_func)
    with open('app.js', 'w') as f:
        f.write(new_app)
    print("Successfully replaced layout!")
else:
    print("Could not find the grid block regex")

