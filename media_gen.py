from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

# Path to your official logo
LOGO_PATH = "/Users/johngiles/.gemini/antigravity/brain/37bf787e-4046-4151-a19d-af587714554a/media__1778508286364.png"

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=True, pnl_usdt=0, user_id=""):
    """
    Generates a professional PnL card using the brand logo as the background.
    Places info in the top left corner.
    """
    if not os.path.exists(LOGO_PATH):
        return None
        
    # Open logo and ensure it's a good size for sharing
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    # If the image is small, let's upscale it for quality
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # Create a dark overlay for the top left area to make text pop
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Try to load fonts
    try:
        font_main = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        font_massive = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 140)
        font_handle = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_massive = ImageFont.load_default()
        font_handle = ImageFont.load_default()

    # Colors
    color_neon = (0, 255, 150, 255) if roe >= 0 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    # Text Margin
    margin_x = 50
    margin_y = 50
    
    # Helper for drop shadow to make text pop on ANY background
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    # 1. Draw Symbol (Top Left)
    clean_sym = symbol.split(':')[0]
    draw_text_shadow((margin_x, margin_y), f"{clean_sym} PERP", font=font_main, fill=color_white)
    
    # 2. Draw Side & Leverage (Below Symbol)
    draw_text_shadow((margin_x, margin_y + 80), f"{side.upper()} 20X", font=font_sub, fill=color_neon)
    
    # 3. Draw MASSIVE ROE (Now Bottom Left for better contrast)
    roe_text = f"{roe:+.2f}%"
    draw_text_shadow((margin_x, base_img.height - 220), roe_text, font=font_massive, fill=color_neon)
    
    # 4. Draw PnL USDT (If not hidden, below ROE)
    if not hide_dollars:
        pnl_text = f"+${pnl_usdt:,.2f} USDT" if pnl_usdt >= 0 else f"-${abs(pnl_usdt):,.2f} USDT"
        draw_text_shadow((margin_x, base_img.height - 80), pnl_text, font=font_sub, fill=color_white)
    
    # 5. Draw Bot Handle (Bottom Right)
    handle_text = "@metaversesherpa_trading_bot"
    w_h = draw.textlength(handle_text, font=font_handle)
    draw.text((base_img.width - w_h - 20, base_img.height - 50), handle_text, font=font_handle, fill=(255, 255, 255, 180))
    
    # Combine logo with overlay
    combined = Image.alpha_composite(base_img, overlay)
    
    # Save result with UNIQUE user_id
    save_filename = f"pnl_card_{user_id}_{clean_sym.replace('/', '_')}.png"
    combined.convert("RGB").save(save_filename, "JPEG", quality=95)
    return save_filename
