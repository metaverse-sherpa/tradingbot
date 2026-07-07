"""
Centralized legal disclaimer constants for all signal delivery surfaces.
Import from here to ensure consistent NFA language across email, Telegram, and web.
"""

# Short disclaimer for Telegram messages (plain text with basic HTML tags)
NFA_SHORT_TEXT = (
    "\n⚠️ <i>Not financial advice. Past performance does not guarantee "
    "future results. Trade at your own risk.</i>"
)

# Short disclaimer for Telegram messages using Markdown parse mode
NFA_SHORT_MARKDOWN = (
    "\n⚠️ _Not financial advice. Past performance does not guarantee "
    "future results. Trade at your own risk._"
)

# Medium disclaimer HTML block for email footers
NFA_MEDIUM_HTML = """
<p style="font-size: 10px; color: rgba(255, 255, 255, 0.35); line-height: 1.5; margin: 15px 0 0 0; text-align: center;">
    ⚠️ Disclaimer: The information provided by Metaverse Sherpa, including trade signals, strategies, and performance data, is for educational and informational purposes only. It does not constitute financial, investment, or trading advice. Past performance is not indicative of future results. Always do your own research and consult with a qualified financial advisor before making any investment decisions. You are solely responsible for your own trading decisions and any resulting gains or losses.
</p>
"""

# Medium disclaimer plain text for web UI (React)
NFA_MEDIUM_TEXT = (
    "⚠️ Disclaimer: The information provided by Metaverse Sherpa, including "
    "trade signals, strategies, and performance data, is for educational and "
    "informational purposes only. It does not constitute financial, investment, "
    "or trading advice. Past performance is not indicative of future results. "
    "Always do your own research and consult with a qualified financial advisor "
    "before making any investment decisions. You are solely responsible for your "
    "own trading decisions and any resulting gains or losses."
)
