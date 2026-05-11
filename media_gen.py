from PIL import Image, ImageDraw, ImageFont
import os

# Path to the CLEAN background image
BG_PATH = "/Users/johngiles/.gemini/antigravity/brain/37bf787e-4046-4151-a19d-af587714554a/pnl_card_bg_pro_1778508170393.png"

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=False, pnl_usdt=0):
    """
    Generates a minimalist, high-impact PnL share card.
    """
    if not os.path.exists(BG_PATH):
        return None
        
    img = Image.open(BG_PATH).convert("RGBA")
    # Resize to a consistent 1024x1024 if needed, though background is 1200x800
    # Let's keep original aspect ratio but use fixed positions
    draw = ImageDraw.Draw(img)
    
    # Try to load a clean font, fallback to default
    try:
        # Common path for macOS
        font_main = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 70)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 45)
        font_massive = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 180)
    except:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_massive = ImageFont.load_default()

    # Colors
    color_green = (0, 230, 118, 255) if roe >= 0 else (255, 23, 68, 255)
    color_white = (255, 255, 255, 255)
    
    # 1. Draw Symbol (Centered horizontally)
    sym_text = f"{symbol.split(':')[0]} PERP"
    w = draw.textlength(sym_text, font=font_main)
    draw.text(((img.width - w) / 2, 180), sym_text, font=font_main, fill=color_white)
    
    # 2. Draw Side & Leverage (Below Symbol)
    side_text = f"{side.upper()} 20X"
    w_side = draw.textlength(side_text, font=font_sub)
    draw.text(((img.width - w_side) / 2, 270), side_text, font=font_sub, fill=color_green)
    
    # 3. Draw MASSIVE ROE (Dead Center)
    roe_text = f"{roe:+.2f}%"
    w_roe = draw.textlength(roe_text, font=font_massive)
    draw.text(((img.width - w_roe) / 2, 380), roe_text, font=font_massive, fill=color_green)
    
    # 4. Draw PnL USDT (if not hidden, smaller at bottom)
    if not hide_dollars:
        pnl_text = f"+${pnl_usdt:,.2f} USDT" if pnl_usdt >= 0 else f"-${abs(pnl_usdt):,.2f} USDT"
        w_pnl = draw.textlength(pnl_text, font=font_main)
        draw.text(((img.width - w_pnl) / 2, 600), pnl_text, font=font_main, fill=color_white)
    
    # 5. Add Brand Footer (Optional, very subtle)
    footer = "METAVERSE SHERPA TRADING"
    w_f = draw.textlength(footer, font=font_sub)
    draw.text(((img.width - w_f) / 2, 720), footer, font=font_sub, fill=(100, 100, 100, 150))
    
    # Save result
    save_path = f"pnl_card_{symbol.replace('/', '_').replace(':', '_')}.png"
    img.save(save_path)
    return save_path
