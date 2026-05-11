from PIL import Image, ImageDraw, ImageFont
import os

# Path to the background image we generated
BG_PATH = "/Users/johngiles/.gemini/antigravity/brain/37bf787e-4046-4151-a19d-af587714554a/pnl_card_bg_1778507377128.png"

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=False, pnl_usdt=0):
    """
    Generates a stunning PnL share card.
    """
    if not os.path.exists(BG_PATH):
        return None
        
    img = Image.open(BG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    # Try to load a clean font, fallback to default
    try:
        # Common path for macOS
        font_main = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 80)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 160)
    except:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_large = ImageFont.load_default()

    # Colors
    color_neon = (0, 229, 255, 255) # Cyan glow
    color_green = (0, 200, 83, 255) if roe >= 0 else (255, 23, 68, 255)
    color_white = (255, 255, 255, 255)
    
    # Draw Symbol & Side
    draw.text((100, 280), f"{symbol} Perp", font=font_main, fill=color_white)
    side_text = f"{side.upper()} 20X"
    draw.text((100, 380), side_text, font=font_sub, fill=color_green)
    
    # Draw Large ROE
    roe_text = f"{roe:+.2f}%"
    draw.text((100, 480), roe_text, font=font_large, fill=color_green)
    
    # Draw PnL USDT (if not hidden)
    if not hide_dollars:
        pnl_text = f"${pnl_usdt:+.2f} USDT"
        draw.text((100, 650), pnl_text, font=font_main, fill=color_white)
    
    # Draw Entry/Mark at bottom
    draw.text((100, 850), "Entry Price", font=font_sub, fill=(180, 180, 180, 255))
    draw.text((100, 910), f"{entry:.8f}".rstrip('0').rstrip('.'), font=font_main, fill=color_white)
    
    draw.text((600, 850), "Mark Price", font=font_sub, fill=(180, 180, 180, 255))
    draw.text((600, 910), f"{mark:.8f}".rstrip('0').rstrip('.'), font=font_main, fill=color_white)
    
    # Save result
    save_path = f"pnl_card_{symbol.replace('/', '_')}.png"
    img.save(save_path)
    return save_path
