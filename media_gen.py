from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import gc

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False
    print("⚠️ Warning: 'qrcode' library not found. QR codes will be skipped.")

# Path to your official logo - Looking for it in the images/ folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "images", "metaverse-bot-logo.png")

def add_qr_code(base_img, link, size=180):
    """
    Generates a QR code for the link and overlays it onto the base image.
    """
    if not HAS_QR:
        return base_img
        
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(link)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Create a small white border for the QR code to make it pop
        border_size = 5
        bg = Image.new("RGBA", (size + border_size*2, size + border_size*2), (255, 255, 255, 255))
        bg.paste(qr_img, (border_size, border_size), qr_img)
        
        # Paste onto bottom right with some margin
        pos = (base_img.width - bg.width - 40, base_img.height - bg.height - 40)
        base_img.paste(bg, pos, bg)
        return base_img
    except Exception as e:
        print(f"⚠️ Error generating QR code: {e}")
        return base_img

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=True, pnl_usdt=0, user_id="", bot_username="metaversesherpa_trading_bot"):
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
        font_handle = find_font(25)
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
    
    # 5. Referral QR and Link
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    
    # Add QR code to bottom right
    combined = add_qr_code(combined, ref_link, size=160)
    
    save_filename = f"pnl_card_{user_id}_{clean_sym.replace('/', '_')}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    gc.collect()
    
    return save_path

def generate_stats_card(overall_pnl, daily_pnl, win_rate, total_trades, user_id="", bot_username="metaversesherpa_trading_bot"):
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
        font_handle = find_font(25)
    except:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

    color_neon = (0, 255, 150, 255) if overall_pnl >= 0 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    draw_text_shadow((margin_x, margin_y), "TRADING PERFORMANCE", font=font_main, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 380), f"Overall: {overall_pnl:+.2f}%", font=font_massive, fill=color_neon)
    draw_text_shadow((margin_x, base_img.height - 240), f"Daily PnL: {daily_pnl:+.2f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 180), f"Win Rate: {win_rate:.1f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 120), f"Total Trades: {total_trades}", font=font_sub, fill=color_white)
    
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    combined = add_qr_code(combined, ref_link, size=160)
    
    save_filename = f"stats_card_{user_id}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    gc.collect()
    
    return save_path

def generate_audit_card(pnl_pct, win_rate, max_dd, total_trades, avg_trades_day, period_text, bot_username="metaversesherpa_trading_bot"):
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
        font_massive = find_font(70)
        font_handle = find_font(25)
    except:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

    color_neon = (0, 255, 150, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    draw_text_shadow((margin_x, margin_y), "3-YEAR PERFORMANCE AUDIT", font=font_main, fill=color_white)
    draw_text_shadow((margin_x, margin_y + 80), period_text, font=font_sub, fill=(200, 200, 200, 255))
    draw_text_shadow((margin_x, base_img.height - 450), f"TOTAL PNL: {pnl_pct:+.1f}%", font=font_massive, fill=color_neon)
    draw_text_shadow((margin_x, base_img.height - 310), f"Verified Win Rate: {win_rate:.1f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 260), f"Max Drawdown: {max_dd:.1f}%", font=font_sub, fill=(255, 100, 100, 255))
    draw_text_shadow((margin_x, base_img.height - 210), f"Total Trades Audited: {total_trades}", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 160), f"Avg Trades/Day: {avg_trades_day:.2f}", font=font_sub, fill=color_white)
    
    ref_link = f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    combined = add_qr_code(combined, ref_link, size=160)
    
    save_path = os.path.join("pnl_cards", "portfolio_audit_card.png")
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85, optimize=True)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    gc.collect()
    
    return save_path
