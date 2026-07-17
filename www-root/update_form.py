import re

filepath = "/Users/johngiles/projects/metaversesherpa/index.html"
with open(filepath, "r") as f:
    html = f.read()

# 1. Update form tags to FormSubmit
html = html.replace(
    '<form class="space-y-6">',
    '<form class="space-y-6" action="https://formsubmit.co/metaversesherpa@gmail.com" method="POST">'
)

# 2. Update Names and Placeholders
html = html.replace('IDENTIFIER [NAME]', 'Your Name')
html = html.replace('placeholder="_enter_name" type="text" required', 'name="name" placeholder="John Doe" type="text" required')

html = html.replace('CONTACT [EMAIL]', 'Email Address')
html = html.replace('placeholder="_enter_email" type="email" required', 'name="email" placeholder="you@example.com" type="email" required')

html = html.replace('ENTITY CLASSIFICATION', 'Who are you representing?')
html = html.replace('<select class="input-terminal', '<select name="entity" class="input-terminal')

html = html.replace('STRATEGIC OBJECTIVE', 'How can we help you?')
html = html.replace('placeholder="_describe_objectives" required', 'name="message" placeholder="Tell us about your project..." required')

html = html.replace('TRANSMIT REQUEST', 'Send Message')

# 3. Update button to match gradient theme
old_btn = 'bg-transparent border border-secondary text-secondary hover:bg-secondary/10 font-label-caps text-xs py-4 rounded transition-colors flex justify-center items-center gap-2 uppercase tracking-wider'
new_btn = 'bg-gradient-to-r from-secondary to-tertiary text-white font-bold rounded-xl shadow-lg hover:shadow-secondary/25 transition-all hover:-translate-y-0.5 py-4 flex justify-center items-center gap-2 text-xs uppercase tracking-wider'
html = html.replace(old_btn, new_btn)

# 4. Update Footer Logo
old_footer_logo = '<img src="https://lh3.googleusercontent.com/aida-public/AB6AXuCeFw4UWcGnXNh8L0fqCiA6LrgVT472mj1YXt-18hJvZQQXka7hFZGOvN9PJX9DNhd-7wePS7H7wBvKYUvH9UJLdsho8pyTxc-lfV5O_tt2Q_tK3F2z0aFfvNxfVAZo_486hlilr60-WEk8Y75KX-6VW2pyXqyoxIO-Rku0XuabD4fYYH_lkuJwdvt37I8yhP1HgjOYWO_SJwhJ6ZGqvcIMM6s26Zz2sF404MsrWBOYLEY-nNDW4hreZYdZYrAReeiKrXDxWLPUvZKU" alt="Metaverse Sherpa Logo" class="h-10 w-auto">'
new_footer_logo = '<img src="images/favicon.svg" alt="Metaverse Sherpa Logo" class="w-8 h-8">'
html = html.replace(old_footer_logo, new_footer_logo)

# Add FormSubmit configuration inputs
hidden_inputs = """
                        <input type="hidden" name="_subject" value="New Contact from Metaverse Sherpa Website!">
                        <input type="hidden" name="_captcha" value="false">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
"""
html = html.replace('<div class="grid grid-cols-1 sm:grid-cols-2 gap-6">', hidden_inputs)

with open(filepath, "w") as f:
    f.write(html)
print("Updated form successfully.")
