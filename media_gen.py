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

_font_cache = {}

def find_brand_font(size):
    if size in _font_cache:
        return _font_cache[size]
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, size)
            _font_cache[size] = font
            return font
        except Exception:
            continue
    default_font = ImageFont.load_default()
    _font_cache[size] = default_font
    return default_font



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

def generate_pnl_card(symbol, side, roe, entry, mark, hide_dollars=True, pnl_usdt=0, user_id="", bot_username="metaversesherpa_trading_bot", ref_link=None):
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
        font_main = find_brand_font(60)
        font_sub = find_brand_font(40)
        font_massive = find_brand_font(140)
        font_handle = find_brand_font(25)
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
    if not ref_link:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    
    # Add QR code to bottom right
    combined = add_qr_code(combined, ref_link, size=160)
    
    save_filename = f"pnl_card_{user_id}_{clean_sym.replace('/', '_')}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    # gc.collect()
    
    return save_path

def generate_stats_card(overall_pnl, daily_pnl, win_rate, total_trades, user_id="", bot_username="metaversesherpa_trading_bot", ref_link=None, title_text="TRADING PERFORMANCE"):
    """
    Generates a professional performance summary card.
    """
    import time
    t0 = time.time()
    if not os.path.exists(LOGO_PATH):
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    t_font = time.time()
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font_main = find_brand_font(60)
        font_sub = find_brand_font(45)
        font_massive = find_brand_font(100)
        font_handle = find_brand_font(25)
    except Exception as fe:
        font_main = font_sub = font_massive = font_handle = ImageFont.load_default()

    t_draw = time.time()
    color_neon = (0, 255, 150, 255) if win_rate >= 50 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 200), offset=(3, 3)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    margin_x = 50
    margin_y = 50
    
    draw_text_shadow((margin_x, margin_y), title_text, font=font_main, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 380), f"Win Rate: {win_rate:.1f}%", font=font_massive, fill=color_neon)
    draw_text_shadow((margin_x, base_img.height - 200), f"Realized PnL: {overall_pnl:+.2f}%", font=font_sub, fill=color_white)
    draw_text_shadow((margin_x, base_img.height - 140), f"Total Trades: {total_trades}", font=font_sub, fill=color_white)
    
    if not ref_link:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    
    t_qr = time.time()
    combined = add_qr_code(combined, ref_link, size=160)
    
    t_save = time.time()
    save_filename = f"stats_card_{user_id}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    # gc.collect()
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
        font_main = find_brand_font(50)
        font_sub = find_brand_font(35)
        font_massive = find_brand_font(70)
        font_handle = find_brand_font(25)
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
    rgb_final.save(save_path, "JPEG", quality=85)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    # gc.collect()
    
    return save_path

def generate_trade_progress_box(symbol, side, entry, tp, sl, current, width=1024, return_image=False):
    """
    Generates a premium horizontal progress bar box to be appended below charts.
    """
    height = 200
    # Background: Dark, almost black
    bg_color = (18, 18, 18, 255)
    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    try:
        font_main = find_brand_font(28)
        font_sub = find_brand_font(22)
    except:
        font_main = font_sub = ImageFont.load_default()

    # Calculate ROE
    if entry > 0:
        roe = ((current - entry) / entry * 100) if side.upper() == 'LONG' else ((entry - current) / entry * 100)
    else:
        roe = 0.0
    # Local definitions to bypass bot.config import which triggers slow GCP Secret Manager lookups
    is_stock = lambda s: str(s).upper() and "/" not in str(s).upper() and ":" not in str(s).upper() and "USDT" not in str(s).upper()
    CRYPTO_LEVERAGE = 20.0
    if not is_stock(symbol):
        roe *= CRYPTO_LEVERAGE
    color_neon = (0, 255, 150, 255) if roe >= 0 else (255, 50, 50, 255)
    
    # Progress Bar Geometry
    bar_x_start = 100
    bar_x_end = width - 100
    bar_y = height // 2 + 20
    bar_width = bar_x_end - bar_x_start
    
    # Range: SL to TP
    p_min = min(sl, tp, entry)
    p_max = max(sl, tp, entry)
    p_range = p_max - p_min if p_max > p_min else 1
    
    def get_x(price):
        ratio = (price - p_min) / p_range
        return bar_x_start + int(ratio * bar_width)

    # Draw Main Track
    draw.line([(bar_x_start, bar_y), (bar_x_end, bar_y)], fill=(60, 60, 60, 255), width=4)
    
    # Draw Ticks
    draw.line([(get_x(sl), bar_y - 20), (get_x(sl), bar_y + 20)], fill=(255, 50, 50, 255), width=4)
    draw.line([(get_x(tp), bar_y - 20), (get_x(tp), bar_y + 20)], fill=(0, 200, 83, 255), width=4)
    draw.line([(get_x(entry), bar_y - 10), (get_x(entry), bar_y + 10)], fill=(255, 255, 255, 200), width=2)
    
    # Labels
    draw.text((get_x(sl), bar_y - 60), "SL", font=font_sub, fill=(255, 50, 50, 255), anchor="mm")
    draw.text((get_x(tp), bar_y - 60), "TP", font=font_sub, fill=(0, 200, 83, 255), anchor="mm")
    draw.text((get_x(entry), bar_y + 40), "ENTRY", font=font_sub, fill=(200, 200, 200, 255), anchor="mm")
    
    # SL/TP Percentages
    if entry > 0:
        sl_roe = ((sl - entry) / entry * 100) if side.upper() == 'LONG' else ((entry - sl) / entry * 100)
        tp_roe = ((tp - entry) / entry * 100) if side.upper() == 'LONG' else ((entry - tp) / entry * 100)
    else:
        sl_roe = 0.0
        tp_roe = 0.0
    
    if not is_stock(symbol):
        sl_roe *= CRYPTO_LEVERAGE
        tp_roe *= CRYPTO_LEVERAGE

    draw.text((get_x(sl), bar_y + 40), f"{sl_roe:.1f}%", font=font_sub, fill=(255, 100, 100, 255), anchor="mm")
    draw.text((get_x(tp), bar_y + 40), f"{tp_roe:+.1f}%", font=font_sub, fill=(0, 255, 150, 255), anchor="mm")
    
    # Current Position Dot
    dot_x = get_x(current)
    # Glow effect
    for r in range(15, 0, -2):
        alpha = int(100 * (1 - r/15))
        draw.ellipse([dot_x - r, bar_y - r, dot_x + r, bar_y + r], fill=(color_neon[0], color_neon[1], color_neon[2], alpha))
    draw.ellipse([dot_x - 8, bar_y - 8, dot_x + 8, bar_y + 8], fill=color_neon, outline=(255, 255, 255, 255), width=2)
    
    # ROE Bubble
    roe_text = f"{roe:+.2f}%"
    bbox = draw.textbbox((dot_x, bar_y - 60), roe_text, font=font_main, anchor="mm")
    draw.rounded_rectangle([bbox[0]-10, bbox[1]-5, bbox[2]+10, bbox[3]+5], radius=10, fill=(30, 30, 30, 255), outline=color_neon, width=2)
    draw.text((dot_x, bar_y - 60), roe_text, font=font_main, fill=color_neon, anchor="mm")
    
    # Header
    draw.text((width // 2, 30), "TRADE PROGRESS", font=font_sub, fill=(150, 150, 150, 255), anchor="mm")
    
    if return_image:
        return img

    save_path = os.path.join("pnl_cards", f"progress_{symbol.replace('/', '_')}.png")
    img.save(save_path)
    img.close()
    return save_path


def generate_forward_test_card(strategy_name, pnl_usdt, win_rate, total_trades, wins, losses, user_id="", bot_username="metaversesherpa_trading_bot"):
    """
    Generates a premium forward testing performance card for a specific strategy
    using a professional glassmorphic sidebar layout to prevent text overflow.
    """
    if not os.path.exists(LOGO_PATH):
        return None
        
    base_img = Image.open(LOGO_PATH).convert("RGBA")
    if base_img.width < 1000:
        base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font_header = find_brand_font(24)
        font_label = find_brand_font(22)
        font_val = find_brand_font(44)
        font_val_sub = find_brand_font(36)
    except:
        font_header = font_label = font_val = font_val_sub = ImageFont.load_default()

    color_neon = (0, 255, 150, 255) if pnl_usdt >= 0 else (255, 50, 50, 255)
    color_white = (255, 255, 255, 255)
    
    def draw_text_shadow(pos, text, font, fill, shadow_fill=(0, 0, 0, 220), offset=(2, 2)):
        draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow_fill)
        draw.text(pos, text, font=font, fill=fill)

    # Frosted Glass Side Panel Geometry
    left = 40
    top = 40
    right = 580
    bottom = base_img.height - 40
    
    # Draw glassmorphic background card
    try:
        draw.rounded_rectangle([left, top, right, bottom], radius=24, fill=(10, 15, 30, 210), outline=(255, 255, 255, 40), width=2)
    except AttributeError:
        draw.rectangle([left, top, right, bottom], fill=(10, 15, 30, 210), outline=(255, 255, 255, 40), width=2)
        
    inner_x = left + 35
    inner_y = top + 45
    
    # Target maximum text width (with generous margins) inside the panel
    target_max_width = (right - inner_x) - 45  # ~460px
    
    # 1. Header Title
    draw_text_shadow((inner_x, inner_y), "FORWARD TESTING PERFORMANCE", font=font_header, fill=(170, 195, 240, 255))
    
    # Separator Line
    draw.line([(inner_x, inner_y + 45), (right - 35, inner_y + 45)], fill=(255, 255, 255, 40), width=2)
    
    # 2. Strategy Name (Auto-Scaled)
    strategy_font_size = 28
    font_strategy = None
    strategy_max_width = (right - inner_x) - 120  # ~385px max width for an elegant fit and gorgeous right-side margin
    while strategy_font_size > 14:
        try:
            font_strategy = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", strategy_font_size)
        except:
            font_strategy = find_font(strategy_font_size)
            
        try:
            bbox = draw.textbbox((0, 0), strategy_name.upper(), font=font_strategy)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width = draw.textsize(strategy_name.upper(), font=font_strategy)[0]
            
        if text_width <= strategy_max_width:
            break
        strategy_font_size -= 2
        
    if not font_strategy:
        font_strategy = ImageFont.load_default()
        
    draw_text_shadow((inner_x, inner_y + 75), strategy_name.upper(), font=font_strategy, fill=color_neon)
    
    # Separator Line
    draw.line([(inner_x, inner_y + 175), (right - 35, inner_y + 175)], fill=(255, 255, 255, 40), width=1)
    
    # 3. Cumulative Return Section (Auto-Scaled as percentage return)
    draw_text_shadow((inner_x, inner_y + 210), "CUMULATIVE RETURN", font=font_label, fill=(170, 195, 240, 255))
    pnl_pct = (pnl_usdt / 1000.0) * 100
    pnl_sign = "+" if pnl_pct >= 0 else "-"
    pnl_text = f"{pnl_sign}{abs(pnl_pct):.2f}%"
    
    pnl_font_size = 56
    font_massive = None
    while pnl_font_size > 18:
        try:
            font_massive = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", pnl_font_size)
        except:
            font_massive = find_font(pnl_font_size)
            
        try:
            bbox = draw.textbbox((0, 0), pnl_text, font=font_massive)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width = draw.textsize(pnl_text, font=font_massive)[0]
            
        if text_width <= target_max_width:
            break
        pnl_font_size -= 2
        
    if not font_massive:
        font_massive = ImageFont.load_default()
        
    draw_text_shadow((inner_x, inner_y + 250), pnl_text, font=font_massive, fill=color_neon)
    
    # Separator Line
    draw.line([(inner_x, inner_y + 345), (right - 35, inner_y + 345)], fill=(255, 255, 255, 40), width=1)
    
    # 4. Strategy Stats Block
    stats_y = inner_y + 380
    
    # Win Rate
    draw_text_shadow((inner_x, stats_y), "WIN RATE", font=font_label, fill=(170, 195, 240, 255))
    draw_text_shadow((inner_x, stats_y + 32), f"{win_rate:.1f}%", font=font_val, fill=color_white)
    
    # Total Trades
    draw_text_shadow((inner_x, stats_y + 105), "TOTAL TRADES", font=font_label, fill=(170, 195, 240, 255))
    draw_text_shadow((inner_x, stats_y + 137), f"{total_trades}", font=font_val, fill=color_white)
    
    # Record Wins / Losses
    draw_text_shadow((inner_x, stats_y + 210), "RECORD", font=font_label, fill=(170, 195, 240, 255))
    draw_text_shadow((inner_x, stats_y + 242), f"{wins} Wins | {losses} Losses", font=font_val_sub, fill=color_white)
    
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"
    
    os.makedirs("pnl_cards", exist_ok=True)
    combined = Image.alpha_composite(base_img, overlay)
    combined = add_qr_code(combined, ref_link, size=160)
    
    clean_strat = strategy_name.replace(" ", "_").lower()
    save_filename = f"forward_test_{clean_strat}_{user_id}.png"
    save_path = os.path.join("pnl_cards", save_filename)
    
    rgb_final = combined.convert("RGB")
    rgb_final.save(save_path, "JPEG", quality=85)
    
    base_img.close(); overlay.close(); combined.close(); rgb_final.close()
    # gc.collect()
    
    return save_path
