import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "results", "stock_strategy_infographic.png")

def create_infographic():
    print("🏔️  Creating Stock Strategy Infographic...")
    
    # 1. Canvas Settings (High-Res 1200 x 1600)
    width, height = 1200, 1600
    img = Image.new("RGBA", (width, height), (18, 18, 18, 255)) # Dark base
    draw = ImageDraw.Draw(img)
    
    # 2. Draw subtle premium gradient glow in corners
    # We will simulate glows by drawing large transparent blurred circles
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    
    # Neon Green Glow (Top Right)
    glow_draw.ellipse([width - 300, -300, width + 500, 500], fill=(57, 255, 20, 15))
    # Neon Blue Glow (Bottom Left)
    glow_draw.ellipse([-400, height - 600, 400, height + 400], fill=(0, 229, 255, 18))
    
    # Blur the glows for a super premium modern look
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(150))
    img = Image.alpha_composite(img, glow_layer)
    draw = ImageDraw.Draw(img)
    
    # 3. Load Fonts (Mac/Linux compatible)
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "Arial"
    ]
    
    def find_font(size, bold=False):
        for path in font_paths:
            try:
                # On macOS Helvetica has multiple faces in .ttc, index 1 or bold works
                if "Helvetica" in path and bold:
                    return ImageFont.truetype(path, size, index=1)
                return ImageFont.truetype(path, size)
            except:
                continue
        return ImageFont.load_default()

    font_brand = find_font(24, bold=True)
    font_title = find_font(56, bold=True)
    font_subtitle = find_font(32)
    font_section = find_font(36, bold=True)
    font_body = find_font(24)
    font_body_bold = find_font(24, bold=True)
    font_stat_val = find_font(64, bold=True)
    font_stat_lbl = find_font(20, bold=True)

    # 4. Header Branding
    # Brand line
    draw.text((80, 70), "SHERPA ALGORITHMIC SUITE", font=font_brand, fill=(0, 229, 255, 255))
    
    # Title
    draw.text((80, 110), "SHERPA VELOCITY PULLBACK", font=font_title, fill=(255, 255, 255, 255))
    
    # Subtitle
    draw.text((80, 180), "US Equities Swing Strategy (Daily)", font=font_subtitle, fill=(180, 180, 180, 255))
    
    # Separator Line
    draw.line([(80, 240), (width - 80, 240)], fill=(60, 60, 60, 255), width=2)
    
    # 5. Core Philosophy Card (Block 1)
    philosophy_y = 280
    # Background card
    draw.rounded_rectangle([80, philosophy_y, width - 80, philosophy_y + 180], radius=15, fill=(28, 28, 28, 200), outline=(0, 229, 255, 40), width=2)
    draw.text((110, philosophy_y + 30), "STRATEGY PHILOSOPHY", font=font_brand, fill=(0, 229, 255, 255))
    
    philosophy_text = (
        "The Sherpa Velocity Pullback (SVP) algorithm targets high-velocity momentum extensions in megacap\n"
        "US equities (NASDAQ/NYSE top 40). It assumes that when institutional giants experience short-term,\n"
        "oversold pullback cycles during robust, verified uptrends, they present high-win-rate swing opportunities."
    )
    draw.text((110, philosophy_y + 75), philosophy_text, font=font_body, fill=(220, 220, 220, 255), spacing=8)
    
    # 6. Technical Setup & Indicators (Block 2)
    setup_y = 490
    draw.rounded_rectangle([80, setup_y, width - 80, setup_y + 330], radius=15, fill=(28, 28, 28, 200), outline=(57, 255, 20, 40), width=2)
    draw.text((110, setup_y + 30), "TECHNICAL INDICATORS & SIGNAL GENERATION", font=font_brand, fill=(57, 255, 20, 255))
    
    # Trend Rule
    draw.text((110, setup_y + 85), "1. Robust Trend Gating:", font=font_body_bold, fill=(255, 255, 255, 255))
    draw.text((360, setup_y + 85), "Daily Close > EMA(200)  AND  SuperTrend(10, 3) is UP", font=font_body, fill=(200, 200, 200, 255))
    draw.text((110, setup_y + 120), "• Purpose:", font=font_body_bold, fill=(150, 150, 150, 255))
    draw.text((215, setup_y + 120), "Restricts execution strictly to strong, long-term institutional market uptrends.", font=font_body, fill=(180, 180, 180, 255))
    
    # Trigger Rule
    draw.text((110, setup_y + 175), "2. Velocity Pullback Trigger:", font=font_body_bold, fill=(255, 255, 255, 255))
    draw.text((430, setup_y + 175), "Wilder RSI (4-Period) < 26", font=font_body, fill=(200, 200, 200, 255))
    draw.text((110, setup_y + 210), "• Purpose:", font=font_body_bold, fill=(150, 150, 150, 255))
    draw.text((215, setup_y + 210), "Identifies highly localized, temporary exhaustion pullbacks ripe for immediate snapbacks.", font=font_body, fill=(180, 180, 180, 255))
    
    # Asset Basket
    draw.text((110, setup_y + 265), "3. Target Basket:", font=font_body_bold, fill=(255, 255, 255, 255))
    draw.text((290, setup_y + 265), "40 High-Liquidity Megacaps (AAPL, MSFT, GOOGL, NVDA, AMZN, etc.)", font=font_body, fill=(200, 200, 200, 255))
    
    # 7. Risk Management & Exits (Block 3)
    risk_y = 850
    draw.rounded_rectangle([80, risk_y, width - 80, risk_y + 330], radius=15, fill=(28, 28, 28, 200), outline=(255, 255, 255, 20), width=2)
    draw.text((110, risk_y + 30), "RISK CONTROLS & DYNAMIC BRACKET EXITS (1.6x MARGIN ACCOUNT)", font=font_brand, fill=(255, 255, 255, 255))
    
    # Sizing
    draw.text((110, risk_y + 85), "• Capital Sizing:", font=font_body_bold, fill=(0, 229, 255, 255))
    draw.text((285, risk_y + 85), "2.0% Risk of total equity per trade (strictly calculated using daily ATR).", font=font_body, fill=(200, 200, 200, 255))
    
    # Take Profit
    draw.text((110, risk_y + 135), "• Take Profit (TP):", font=font_body_bold, fill=(57, 255, 20, 255))
    draw.text((300, risk_y + 135), "Bracket order set automatically at entry price + (4.8 * ATR) [1.6 R:R].", font=font_body, fill=(200, 200, 200, 255))
    
    # Stop Loss
    draw.text((110, risk_y + 185), "• Stop Loss (SL):", font=font_body_bold, fill=(255, 50, 50, 255))
    draw.text((290, risk_y + 185), "Bracket order set automatically at entry price - (3.0 * ATR).", font=font_body, fill=(200, 200, 200, 255))
    
    # Dynamic Exits
    draw.text((110, risk_y + 235), "• Dynamic Time Exits:", font=font_body_bold, fill=(255, 235, 59, 255))
    draw.text((345, risk_y + 235), "Exits immediately at market open if yesterday's closed candle has:", font=font_body, fill=(200, 200, 200, 255))
    draw.text((130, risk_y + 275), "- Crossed above daily Wilder RSI(4) > 75 (dynamic profit-taking exit).", font=font_body_bold, fill=(220, 220, 220, 255))
    
    # 8. Audited Performance Metrics (Block 4)
    perf_y = 1210
    draw.rounded_rectangle([80, perf_y, width - 80, perf_y + 230], radius=15, fill=(18, 30, 22, 200), outline=(57, 255, 20, 60), width=2)
    
    # Metric Sub-boxes
    box_w = (width - 160) // 4
    
    def draw_stat(idx, val, label, color):
        x_center = 80 + (idx * box_w) + (box_w // 2)
        y_val = perf_y + 80
        y_lbl = perf_y + 155
        draw.text((x_center, y_val), val, font=font_stat_val, fill=color, anchor="mm")
        draw.text((x_center, y_lbl), label, font=font_stat_lbl, fill=(180, 180, 180, 255), anchor="mm")
        
        # Vertical divider line
        if idx < 3:
            draw.line([(80 + (idx+1)*box_w, perf_y + 40), (80 + (idx+1)*box_w, perf_y + 190)], fill=(60, 60, 60, 100), width=1)
            
    draw_stat(0, "+102.3%", "TOTAL RETURN", (57, 255, 20, 255))
    draw_stat(1, "70.2%", "WIN RATE", (255, 255, 255, 255))
    draw_stat(2, "22.7%", "MAX DRAWDOWN", (255, 100, 100, 255))
    draw_stat(3, "0.42", "TRADES / DAY", (0, 229, 255, 255))
    
    # Performance Header Text
    draw.text((width // 2, perf_y + 35), "VERIFIED 5-YEAR HISTORICAL BACKTEST METRICS (2021-2026)", font=font_brand, fill=(200, 200, 200, 255), anchor="mm")
    
    # 9. Bottom Footer
    footer_text = "METAVERSE SHERPA © 2026 | SECURED DUAL-ASSET ALGORITHMIC EXECUTION ENGINE"
    draw.text((width // 2, height - 60), footer_text, font=font_brand, fill=(100, 100, 100, 255), anchor="mm")
    
    # 10. Save and Output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    img.save(OUTPUT_PATH, "PNG")
    img.close()
    print(f"✅ Infographic created successfully and saved at: {OUTPUT_PATH}")

if __name__ == "__main__":
    create_infographic()
