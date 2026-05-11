from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

# Path to your official logo
LOGO_PATH = "/Users/johngiles/.gemini/antigravity/brain/37bf787e-4046-4151-a19d-af587714554a/media__1778508286364.png"

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=True, pnl_usdt=0, user_id=""):
    """
    Generates a professional PnL card using the brand logo as the background.
    """
    if not os.path.exists(LOGO_PATH):
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
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

    color_neon = (0, 255, 150, 255) if roe >= 0 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    # 1. Symbol
    clean_sym = symbol.split(':')[0]
    draw_text_shadow((margin_x, margin_y), f"{clean_sym} PERP", font=font_main, fill=color_white)
    
    # 2. Side
    draw_text_shadow((margin_x, margin_y + 80), f"{side.upper()} 20X", font=font_sub, fill=color_neon)
    
    # 3. ROE (Bottom Left)
    roe_text = f"{roe:+.2f}%"
    draw_text_shadow((margin_x, base_img.height - 220), roe_text, font=font_massive, fill=color_neon)
    
    # 4. PnL (If not hidden)
    if not hide_dollars:
        pnl_text = f"+${pnl_usdt:,.2f} USDT" if pnl_usdt >= 0 else f"-${abs(pnl_usdt):,.2f} USDT"
        draw_text_shadow((margin_x, base_img.height - 80), pnl_text, font=font_sub, fill=color_white)
    
    handle_text = "@metaversesherpa_trading_bot"
    w_h = draw.textlength(handle_text, font=font_handle)
    draw.text((base_img.width - w_h - 20, base_img.height - 50), handle_text, font=font_handle, fill=(255, 255, 255, 180))
    
    combined = Image.alpha_composite(base_img, overlay)
    save_filename = f"pnl_card_{user_id}_{clean_sym.replace('/', '_')}.png"
    combined.convert("RGB").save(save_filename, "JPEG", quality=95)
    return save_filename

def generate_stats_card(overall_pnl, daily_pnl, win_rate, total_trades, user_id=""):
    """
    Generates a professional performance summary card.
    """
    if not os.path.exists(LOGO_PATH):
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font_main = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 45)
        font_massive = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 100)
        font_handle = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_massive = ImageFont.load_default()
        font_handle = ImageFont.load_default()

    color_neon = (0, 255, 150, 255) if overall_pnl >= 0 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    # 1. Header (Top Left)
    draw_text_shadow((margin_x, margin_y), "TRADING PERFORMANCE", font=font_main, fill=color_white)
    
    # 2. Overall PnL (Massive, Bottom Left for better contrast)
    draw_text_shadow((margin_x, base_img.height - 380), f"Overall: {overall_pnl:+.2f}%", font=font_massive, fill=color_neon)
    
    # 3. Stats Block (Stacked above Handle)
    draw_text_shadow((margin_x, base_img.height - 240), f"Daily PnL: {daily_pnl:+.2f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 180), f"Win Rate: {win_rate:.1f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 120), f"Total Trades: {total_trades}", font=font_sub, fill=color_white)
    
    # 4. Handle
    handle_text = "@metaversesherpa_trading_bot"
    w_h = draw.textlength(handle_text, font=font_handle)
    draw.text((base_img.width - w_h - 20, base_img.height - 50), handle_text, font=font_handle, fill=(255, 255, 255, 180))
    
    combined = Image.alpha_composite(base_img, overlay)
    save_filename = f"stats_card_{user_id}.png"
    combined.convert("RGB").save(save_filename, "JPEG", quality=95)
    return save_filename
