from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import gc

# Path to your official logo - Looking for it in the images/ folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "images", "metaverse-bot-logo.png")

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=True, pnl_usdt=0, user_id=""):
    """
    Generates a professional PnL card using the brand logo as the background.
    """
    if not os.path.exists(LOGO_PATH):
        print(f"❌ Error: Logo not found at {LOGO_PATH}")
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        # Standard paths for Linux (Ubuntu) and Mac
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "Arial"
        ]
        
        def find_font(size):
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except: continue
            return ImageFont.load_default()

        font_main = find_font(60)
        font_sub = find_font(40)
        font_massive = find_font(140)
        font_handle = find_font(30)
    except:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

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
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    save_filename = f"pnl_card_{user_id}_{clean_sym.replace('/', '_')}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    # Save as JPEG with optimized quality to save RAM/Space
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    # CRITICAL: Close all image objects to release RAM
    base_img.close()
    overlay.close()
    combined.close()
    rgb_final.close()
    gc.collect() # Force garbage collection
    
    return save_path

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
        # Standard paths for Linux (Ubuntu) and Mac
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "Arial"
        ]
        
        def find_font(size):
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except: continue
            return ImageFont.load_default()

        font_main = find_font(60)
        font_sub = find_font(45)
        font_massive = find_font(100)
        font_handle = find_font(30)
    except:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

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
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    save_filename = f"stats_card_{user_id}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    # Save as JPEG with optimized quality to save RAM/Space
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    # CRITICAL: Close all image objects to release RAM
    base_img.close()
    overlay.close()
    combined.close()
    rgb_final.close()
    gc.collect() # Force garbage collection
    
    return save_path

def generate_audit_card(pnl_pct, win_rate, max_dd, total_trades, period_text):
    """
    Generates a professional 3-year performance audit certificate.
    """
    if not os.path.exists(LOGO_PATH):
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "Arial"
        ]
        
        def find_font(size):
            for path in font_paths:
                try: return ImageFont.truetype(path, size)
                except: continue
            return ImageFont.load_default()

        font_main = find_font(50)
        font_sub = find_font(35)
        font_massive = find_font(90)
        font_handle = find_font(30)
    except:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

    color_neon = (0, 255, 150, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    # 1. Header
    draw_text_shadow((margin_x, margin_y), "3-YEAR PERFORMANCE AUDIT", font=font_main, fill=color_white)
    draw_text_shadow((margin_x, margin_y + 80), period_text, font=font_sub, fill=(200, 200, 200, 255))
    
    # 2. Massive PnL
    draw_text_shadow((margin_x, base_img.height - 450), f"TOTAL PNL: {pnl_pct:+.1f}%", font=font_massive, fill=color_neon)
    
    # 3. Stats Block
    draw_text_shadow((margin_x, base_img.height - 280), f"Verified Win Rate: {win_rate:.1f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 220), f"Max Drawdown: {max_dd:.1f}%", font=font_sub, fill=(255, 100, 100, 255))
    draw_text_shadow((margin_x, base_img.height - 160), f"Total Trades Audited: {total_trades}", font=font_sub, fill=color_white)
    
    handle_text = "@metaversesherpa_trading_bot"
    w_h = draw.textlength(handle_text, font=font_handle)
    draw.text((base_img.width - w_h - 20, base_img.height - 50), handle_text, font=font_handle, fill=(255, 255, 255, 180))
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    save_path = os.path.join("pnl_cards", "portfolio_audit_card.png")
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    gc.collect()
    
    return save_path
