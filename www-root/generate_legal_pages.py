import os
import re

index_path = "/Users/johngiles/projects/metaversesherpa/index.html"
with open(index_path, "r") as f:
    html = f.read()

# Extract head and nav (everything up to </nav>)
head_match = re.search(r'(.*?</nav>)', html, re.DOTALL)
head_content = head_match.group(1)

# Extract footer (everything from <!-- Footer --> to the end)
footer_match = re.search(r'(<!-- Footer -->.*)', html, re.DOTALL)
footer_content = footer_match.group(1)

# Update the links in the footer_content to point to actual files instead of '#'
footer_content = footer_content.replace('href="#" class="text-on-surface-variant hover:text-primary transition-colors">Risk Disclosure', 'href="risk-disclosure.html" class="text-gray-400 hover:text-white transition-colors">Risk Disclosure')
footer_content = footer_content.replace('href="#" class="text-on-surface-variant hover:text-primary transition-colors">Privacy Policy', 'href="privacy-policy.html" class="text-gray-400 hover:text-white transition-colors">Privacy Policy')
footer_content = footer_content.replace('class="flex flex-wrap gap-x-8 gap-y-4 text-xs font-label-caps"', 'class="flex flex-wrap gap-x-8 gap-y-4 text-sm"')
footer_content = footer_content.replace('class="text-on-surface-variant hover:text-primary transition-colors"', 'class="text-gray-400 hover:text-white transition-colors"')


def create_page(filename, title, content):
    page_html = f"""{head_content}
    <main class="flex-grow pt-32 pb-24 px-8 max-w-4xl mx-auto">
        <h1 class="text-3xl font-bold text-white mb-8">{title}</h1>
        <div class="text-gray-400 space-y-6 leading-relaxed">
            {content}
        </div>
    </main>
    {footer_content}
"""
    # Fix the links in the page's own nav to go back to index.html#sections
    page_html = page_html.replace('href="#', 'href="index.html#')
    
    with open(f"/Users/johngiles/projects/metaversesherpa/{filename}", "w") as f:
        f.write(page_html)

risk_content = """
<p>Trading stocks, options, cryptocurrencies, and other financial instruments involves a high degree of risk and may not be suitable for all investors. Past performance of any trading system or methodology is not necessarily indicative of future results.</p>
<p>Metaverse Sherpa provides algorithmic trading tools and portfolio analytics for informational and educational purposes only. We are not registered financial advisors. By using this platform, you acknowledge that you are solely responsible for your own investment decisions and any resulting financial losses.</p>
<p>Hypothetical or simulated performance results have certain inherent limitations. Unlike an actual performance record, simulated results do not represent actual trading. No representation is being made that any account will or is likely to achieve profits or losses similar to those shown.</p>
"""

privacy_content = """
<p>At Metaverse Sherpa, we take your privacy seriously. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you visit our website or use our trading bot services.</p>
<h2 class="text-xl font-bold text-white mt-8 mb-4">1. Information We Collect</h2>
<p>We may collect personal information such as your name, email address, and wallet addresses when you register for an account or contact us. We also automatically collect certain information about your device and usage patterns.</p>
<h2 class="text-xl font-bold text-white mt-8 mb-4">2. How We Use Your Information</h2>
<p>We use the information we collect to provide and improve our services, process your transactions, send you technical notices and support messages, and communicate with you about products, services, and events.</p>
<h2 class="text-xl font-bold text-white mt-8 mb-4">3. Data Security</h2>
<p>We implement appropriate technical and organizational security measures designed to protect the security of any personal information we process. However, please also remember that we cannot guarantee that the internet itself is 100% secure.</p>
<h2 class="text-xl font-bold text-white mt-8 mb-4">4. Contact Us</h2>
<p>If you have questions or comments about this Privacy Policy, please contact us at metaversesherpa@gmail.com.</p>
"""

create_page("risk-disclosure.html", "Risk Disclosure", risk_content)
create_page("privacy-policy.html", "Privacy Policy", privacy_content)

print("Created risk-disclosure.html and privacy-policy.html")
