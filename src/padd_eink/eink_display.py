import os
import time
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import qrcode

from . import format_uptime, compare_versions, check_padd_eink_version

# --- Constants ---
WHITE = 255
BLACK = 0
FONT_SIZE_HEADER_TITLE = 18
FONT_SIZE_HEADER_DATE = 14
FONT_SIZE_BODY = 15
FONT_SIZE_SMALL = 12

# GPIO Pin Configuration (BCM numbering)
KEY1_PIN = 5
KEY2_PIN = 6
KEY3_PIN = 13
KEY4_PIN = 19
# Debounce time for gpiozero is in seconds
BUTTON_DEBOUNCE_S = 0.3
BUTTON_HOLD_S = 5  # Time in seconds to hold for QR code

project_dir = os.path.join(os.path.dirname(__file__), "..", "..")
# --- Paths (Updated to use subdirectories) ---
LOGO_PATH = os.path.join(project_dir, "images", "Pihole-eInk.jpg")
HEADER_LOGO_PATH = os.path.join(project_dir, "images", "black-hole-2.png")
# Switched to DejaVuSans for better character support (including checkmarks)
FONT_PATH = os.path.join(project_dir, "fonts", "DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(project_dir, "fonts", "DejaVuSans-Bold.ttf")

logger = logging.getLogger(__name__)

# --- Globals for e-Ink Mode ---
padd_data = {}
last_data_refresh_time = 0
current_screen_index = 0
force_redraw = True
qrcode_mode_active = False  # New state for QR code screen
connection_failed_at_boot = False


# --- e-Ink Drawing Functions ---
def draw_splash_screen(epd, logo_image, width, height):
    logger.info("Displaying 4-gray splash screen...")
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    if logo_image:
        logo_w, logo_h = logo_image.size
        pos_x = (width - logo_w) // 2
        pos_y = (height - logo_h) // 2
        image.paste(logo_image.convert("L"), (pos_x, pos_y))
    epd.display_4Gray(epd.getbuffer_4Gray(image))


def draw_header(draw, width, header_logo_img):
    try:
        font_title = ImageFont.truetype(FONT_PATH, FONT_SIZE_HEADER_TITLE)
        font_date = ImageFont.truetype(FONT_PATH, FONT_SIZE_HEADER_DATE)
    except IOError:
        font_title, font_date = ImageFont.load_default(), ImageFont.load_default()

    logo_x, logo_y = 5, 5
    title_x = logo_x
    if header_logo_img:
        header_logo_thumb = header_logo_img.copy()
        header_logo_thumb.thumbnail((40, 40))
        draw.bitmap((logo_x, logo_y), header_logo_thumb.convert("1"), fill=BLACK)
        title_x += header_logo_thumb.width + 10
    draw.text((title_x, logo_y), "Pi-hole Stats", font=font_title, fill=BLACK)
    now = datetime.now()
    date_text = now.strftime("%a, %b %d")
    time_text = now.strftime("%H:%M")
    date_y = logo_y + FONT_SIZE_HEADER_TITLE + 3
    draw.text((title_x, date_y), date_text, font=font_date, fill=BLACK)
    time_bbox = draw.textbbox((0, 0), time_text, font=font_date)
    time_width = time_bbox[2] - time_bbox[0]
    draw.text((width - time_width - 5, date_y), time_text, font=font_date, fill=BLACK)
    line_y = date_y + FONT_SIZE_HEADER_DATE + 5
    draw.line([(0, line_y), (width, line_y)], fill=BLACK, width=1)
    return line_y


def draw_qrcode_screen(draw, width, height, url):
    try:
        font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
    except IOError:
        font_regular, font_bold = ImageFont.load_default(), ImageFont.load_default()

    title_text = "Pi-Hole Admin"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_bold)
    title_width, title_height = title_bbox[2], title_bbox[3]
    title_y = 3
    draw.text(((width - title_width) / 2, title_y), title_text, font=font_bold, fill=BLACK)

    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
    qr_pos_x = (width - qr_img.size[0]) // 2
    qr_pos_y = title_y + title_height + 10
    draw.bitmap((qr_pos_x, qr_pos_y), qr_img, fill=BLACK)

    instruction_text = "Hold key 1 button to close"
    inst_bbox = draw.textbbox((0, 0), instruction_text, font=font_regular)
    inst_width = inst_bbox[2]
    inst_y = qr_pos_y + qr_img.size[1] + 4
    draw.text(
        ((width - inst_width) / 2, inst_y), instruction_text, font=font_regular, fill=BLACK
    )


def draw_pihole_stats_screen(draw, width, height, data, header_bottom_y,__version__):
    """Draws the main Pi-hole statistics screen."""
    try:
        font_small = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
        font_small_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_SMALL)
    except IOError:
        logger.warning("Could not load custom small fonts, using defaults.")
        font_small = ImageFont.load_default()
        font_small_bold = font_small

    y = header_bottom_y + 10
    right_align_x = width - 10
    line_height_small = FONT_SIZE_SMALL + 4

    if not data:
        draw.text((10, y), "No Pi-hole data available.", font=font_small, fill=BLACK)
        return

    queries_data = data.get("queries", {})
    blocked = queries_data.get("blocked", 0)
    total = queries_data.get("total", 0)
    percent = queries_data.get("percent_blocked", 0.0)
    gravity_size = data.get("gravity_size", 0)

    blocking_label = "Blocking:"
    blocking_value = f"{int(gravity_size):,}"
    draw.text((10, y), blocking_label, font=font_small_bold, fill=BLACK)
    value_bbox = draw.textbbox((0, 0), blocking_value, font=font_small)
    value_width = value_bbox[2] - value_bbox[0]
    draw.text((right_align_x - value_width, y), blocking_value, font=font_small, fill=BLACK)
    y += line_height_small

    piholed_label = "Piholed:"
    draw.text((10, y), piholed_label, font=font_small_bold, fill=BLACK)

    piholed_label_bbox = draw.textbbox((0, 0), piholed_label, font=font_small_bold)
    piholed_label_width = piholed_label_bbox[2] - piholed_label_bbox[0]

    bar_text = f" {int(blocked):,} of {int(total):,} ({percent:.1f}%)"
    draw.text((10 + piholed_label_width, y), bar_text, font=font_small, fill=BLACK)

    bar_text_bbox = draw.textbbox((0, 0), bar_text, font=font_small)
    bar_text_width = bar_text_bbox[2] - bar_text_bbox[0]

    bar_height = 15
    bar_y = y - 2

    bar_x = 10 + piholed_label_width + bar_text_width + 5

    bar_width = width - bar_x - 10

    if bar_width > 10:
        draw.rectangle(
            [bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
            outline=BLACK,
            fill=WHITE,
        )
        fill_width = int(bar_width * (percent / 100.0))
        if fill_width > 0:
            draw.rectangle(
                [bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=BLACK
            )
    else:
        logger.warning("Not enough horizontal space for percentage bar.")

    y += bar_height

    top_stats = {
        "Latest:": "N/A" if (latest := data.get("recent_blocked")) is None else latest,
        "Top Ad:": "N/A" if (ad := data.get("top_blocked")) is None else ad,
        "Top Domain:": "N/A" if (domain := data.get("top_domain")) is None else domain,
        "Top Client:": "N/A" if (client := data.get("top_client")) is None else client,
        "Clients:": "N/A"
        if (clients := data.get("active_clients")) is None
        else f"{clients}",
    }

    for label, value in top_stats.items():
        draw.text((10, y), label, font=font_small_bold, fill=BLACK)

        value_bbox = draw.textbbox((0, 0), value, font=font_small)
        value_width = value_bbox[2] - value_bbox[0]
        draw.text((right_align_x - value_width, y), value, font=font_small, fill=BLACK)

        y += line_height_small


def draw_system_info_screen(draw, width, height, data, header_bottom_y,__version__):
    try:
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
        font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
    except IOError:
        font_bold, font_regular = ImageFont.load_default(), ImageFont.load_default()
    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 7
    right_align_x = width - 10
    if not data:
        draw.text((10, y), "No system data available.", font=font_regular, fill=BLACK)
        return

    system_data = data.get("system", {})
    stats_to_draw = {
        "Host:": f"{data.get('node_name', 'N/A')} ({data.get('iface', {}).get('v4', {}).get('addr', 'N/A')})",
        "CPU Load:": f"{system_data.get('cpu', {}).get('load', {}).get('percent', [0.0])[0]:.1f}%",
        "Memory:": f"{system_data.get('memory', {}).get('ram', {}).get('%used', 0.0):.1f}%",
        "CPU Temp:": f"{data.get('sensors', {}).get('cpu_temp', 0.0):.1f}°C",
        "Uptime:": format_uptime(system_data.get("uptime", 0)),
    }
    for label, value in stats_to_draw.items():
        draw.text((10, y), label, font=font_bold, fill=BLACK)
        value_bbox = draw.textbbox((0, 0), value, font=font_regular)
        draw.text(
            (right_align_x - value_bbox[2], y), value, font=font_regular, fill=BLACK
        )
        y += line_height


def draw_version_screen(draw, width, height, data, header_bottom_y, __version__):
    """Draws the component versions screen, indicating available updates."""
    try:
        font_body = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
        font_body_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
        font_small_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_SMALL)
    except IOError:
        logger.warning("Could not load custom fonts for version screen, using defaults.")
        font_body = ImageFont.load_default()
        font_body_bold = font_body
        font_small_bold = ImageFont.load_default()

    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 10
    any_updates = False
    checkmark = "✓"  # Unicode for checkmark
    right_align_x = width - 10

    # PADD-eInk version
    padd_eink_version_line = check_padd_eink_version(__version__, output_format='eink')
    if "**" in padd_eink_version_line:
        any_updates = True
    
    # Use a raw string or escape the tab character properly
    parts = padd_eink_version_line.split('\t')
    padd_eink_label = parts[0]
    padd_eink_version_str = parts[1].strip() if len(parts) > 1 else ''

    draw.text((10, y), padd_eink_label, font=font_body_bold, fill=BLACK)
    version_bbox = draw.textbbox((0, 0), padd_eink_version_str, font=font_body)
    version_width = version_bbox[2] - version_bbox[0] + 3
    draw.text(
        (right_align_x - version_width, y), padd_eink_version_str, font=font_body, fill=BLACK
    )
    y += line_height

    version_data = data.get("version")
    if not version_data:
        draw.text((10, y), "Version data not available.", font=font_body, fill=BLACK)
        return

    def get_version_status(comp_data):
        """Returns a tuple: (display_string, has_update_bool)"""
        if not comp_data:
            return ("N/A", False)

        local = comp_data.get("local", {}).get("version", "N/A")
        remote = comp_data.get("remote", {}).get("version", "N/A")

        update_available = False
        if local != "N/A" and remote != "N/A":
            if compare_versions(remote, local) > 0:
                update_available = True

        if update_available:
            display_str = f"  {local}**"
        else:
            display_str = f"  {local} {checkmark}" if local != "N/A" else "N/A"

        return (display_str, update_available)

    component_names = {
        "Pi-hole:": version_data.get("core"),
        "Web UI:": version_data.get("web"),
        "FTL:": version_data.get("ftl"),
    }

    for name, comp_data in component_names.items():
        version_str, has_update = get_version_status(comp_data)
        if has_update:
            any_updates = True

        draw.text((10, y), name, font=font_body_bold, fill=BLACK)

        version_bbox = draw.textbbox((0, 0), version_str, font=font_body)
        version_width = version_bbox[2] - version_bbox[0]
        draw.text(
            (right_align_x - version_width, y), version_str, font=font_body, fill=BLACK
        )

        y += line_height

    y += 5
    if any_updates:
        status_text = "** Update available"
    else:
        status_text = f"{checkmark} {checkmark} SYSTEM IS HEALTHY {checkmark} {checkmark}"

    text_bbox = draw.textbbox((0, 0), status_text, font=font_small_bold)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text(
        ((width - text_width) / 2, y), status_text, font=font_small_bold, fill=BLACK
    )


def draw_connection_failed_screen(draw, width, height, header_bottom_y, pihole_ip):
    """Draws the screen indicating a failure to connect to Pi-hole."""
    try:
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
        font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
    except IOError:
        font_bold, font_regular = ImageFont.load_default(), ImageFont.load_default()

    y = header_bottom_y + 20
    line_height = FONT_SIZE_BODY + 5

    line1_text = "UNABLE TO CONNECT"
    line1_bbox = draw.textbbox((0, 0), line1_text, font=font_bold)
    line1_width = line1_bbox[2] - line1_bbox[0]
    draw.text(((width - line1_width) / 2, y), line1_text, font=font_bold, fill=BLACK)
    y += line_height

    line2_text = f"to {pihole_ip}"
    line2_bbox = draw.textbbox((0, 0), line2_text, font=font_bold)
    line2_width = line2_bbox[2] - line2_bbox[0]
    draw.text(((width - line2_width) / 2, y), line2_text, font=font_bold, fill=BLACK)
    y += line_height + 10

    line3_text = "Is PiHole OK?"
    line3_bbox = draw.textbbox((0, 0), line3_text, font=font_regular)
    line3_width = line3_bbox[2] - line3_bbox[0]
    draw.text(((width - line3_width) / 2, y), line3_text, font=font_regular, fill=BLACK)


# --- e-Ink GPIO Button Handlers ---
def handle_short_press(button_pin):
    global current_screen_index, force_redraw, qrcode_mode_active
    if qrcode_mode_active:
        return
    logger.info(f"Short press detected on GPIO {button_pin}")
    if button_pin == KEY2_PIN:
        current_screen_index = 0
    elif button_pin == KEY3_PIN:
        current_screen_index = 1
    elif button_pin == KEY4_PIN:
        current_screen_index = 2
    force_redraw = True


def handle_refresh_press(pihole_client_creator, pihole_auth, api_token):
    global last_data_refresh_time, force_redraw, qrcode_mode_active, connection_failed_at_boot, pihole
    if qrcode_mode_active:
        return
    logger.info("Short press detected on refresh button.")
    last_data_refresh_time = 0
    force_redraw = True
    if connection_failed_at_boot:
        pihole = pihole_client_creator(pihole_auth, api_token)
        if pihole:
            connection_failed_at_boot = False  # Allow retry


def handle_qrcode_toggle():
    global qrcode_mode_active, force_redraw
    logger.info("Long press detected, toggling QR code mode.")
    qrcode_mode_active = not qrcode_mode_active
    force_redraw = True


# --- Data Fetching ---
def refresh_data(pihole):
    """Fetches PADD summary data from the Pi-hole v6 API."""
    global last_data_refresh_time, padd_data
    current_time = time.time()
    if current_time - last_data_refresh_time > 120 or not padd_data:
        logger.info("Refreshing data from Pi-hole API...")
        try:
            padd_data = pihole.get_padd_summary(full=True)
            last_data_refresh_time = current_time
            logger.info("Data refresh complete.")
        except Exception as e:
            logger.error(f"Failed to get data from Pi-hole: {e}")
            padd_data = {}


# --- Main Dispatcher & e-Ink Runner ---
def run_eink_display(
    pihole_client,
    pihole_url,
    pihole_auth,
    api_token,
    pihole_client_creator,
    splash_duration,
    rotate_interval,
    __version__,
):
    """Initializes and runs the e-Ink display loop."""
    from gpiozero import Button
    import epaper

    global padd_data, force_redraw, current_screen_index, last_data_refresh_time, qrcode_mode_active, pihole, connection_failed_at_boot
    pihole = pihole_client
    epd = None
    try:
        epd = epaper.epaper("epd2in7_V2").EPD()
        epd.init()
        epd.Clear()
        epd.Init_4Gray()
        logger.info("EPD Initialized in 4-Gray mode.")
        width, height = epd.height, epd.width
        logger.info(f"Screen dimensions set to {width}x{height}")

        splash_logo_image = Image.open(LOGO_PATH) if os.path.exists(LOGO_PATH) else None
        header_logo_image = (
            Image.open(HEADER_LOGO_PATH) if os.path.exists(HEADER_LOGO_PATH) else None
        )

        draw_splash_screen(epd, splash_logo_image, width, height)
        time.sleep(splash_duration)

        if not padd_data:
            logger.info("Attempting initial connection to Pi-hole...")
            for i in range(3):
                refresh_data(pihole)
                if padd_data:
                    break
                logger.warning(
                    f"Initial connection attempt {i+1}/3 failed. Retrying in 5 seconds..."
                )
                time.sleep(5)

            if not padd_data:
                logger.error("Could not connect to Pi-hole after 3 attempts.")
                connection_failed_at_boot = True
                force_redraw = True

        epd.init()
        epd.Clear()

        button1 = Button(
            KEY1_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S, hold_time=BUTTON_HOLD_S
        )
        button2, button3, button4 = (
            Button(KEY2_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S),
            Button(KEY3_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S),
            Button(KEY4_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S),
        )
        button1.when_pressed = lambda: handle_refresh_press(
            pihole_client_creator, pihole_auth, api_token
        )
        button1.when_held = handle_qrcode_toggle
        button2.when_pressed, button3.when_pressed, button4.when_pressed = (
            lambda: handle_short_press(KEY2_PIN),
            lambda: handle_short_press(KEY3_PIN),
            lambda: handle_short_press(KEY4_PIN),
        )

        screens = [draw_pihole_stats_screen, draw_system_info_screen, draw_version_screen]
        num_screens = len(screens)
        last_screen_rotate_time = time.time()

        while True:
            if (
                not qrcode_mode_active
                and not connection_failed_at_boot
                and time.time() - last_screen_rotate_time > rotate_interval
            ):
                current_screen_index = (current_screen_index + 1) % num_screens
                force_redraw = True
                last_screen_rotate_time = time.time()

            if force_redraw:
                image = Image.new("1", (width, height), WHITE)
                draw = ImageDraw.Draw(image)

                if connection_failed_at_boot:
                    header_bottom_y = draw_header(draw, width, header_logo_image)
                    draw_connection_failed_screen(
                        draw, width, height, header_bottom_y, pihole_auth.split("//")[1]
                    )
                elif qrcode_mode_active:
                    draw_qrcode_screen(draw, width, height, pihole_url)
                else:
                    refresh_data(pihole)
                    logger.info(
                        f"Drawing screen {current_screen_index + 1}/{num_screens}..."
                    )
                    header_bottom_y = draw_header(draw, width, header_logo_image)
                    screens[current_screen_index](
                        draw, width, height, padd_data, header_bottom_y, __version__
                    )

                epd.display(epd.getbuffer(image))
                logger.info("EPD display updated.")
                force_redraw = False

            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Exit signal received.")
        if pihole_client is not None:
            pihole_client.close_session()
    except Exception as e:
        logger.error(f"An unexpected error occurred in e-Ink mode: {e}", exc_info=True)
    finally:
        if epd:
            epd.Clear()
            epd.sleep()
