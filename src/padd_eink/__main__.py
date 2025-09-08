#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import sys
import os
import time
import logging
import argparse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps

# --- Library Imports ---
from gpiozero import Button 
from dotenv import load_dotenv
from pihole6api import PiHole6Client
from richcolorlog import setup_logging
import epaper

# --- Configuration ---
# Load environment variables from .env file in the project's root directory
project_dir = os.path.join(os.path.dirname(__file__), '..', '..')
load_dotenv(dotenv_path=os.path.join(project_dir, '.env'))

PIHOLE_IP = os.getenv("PIHOLE_IP")
API_TOKEN = os.getenv("API_TOKEN")

# --- Logging Setup ---
# Logger is configured in the main() function based on command-line args.
logger = None

# Display Configuration
SPLASH_SCREEN_DURATION_SECONDS = 10
SCREEN_AUTO_ROTATE_INTERVAL_SECONDS = 20
INFO_REFRESH_INTERVAL_SECONDS = 60 * 2

# GPIO Pin Configuration (BCM numbering)
KEY1_PIN = 5
KEY2_PIN = 6
KEY3_PIN = 13
KEY4_PIN = 19
# Debounce time for gpiozero is in seconds
BUTTON_DEBOUNCE_S = 0.3

# --- Paths (Updated to use subdirectories) ---
LOGO_PATH = os.path.join(project_dir, 'images', 'Pihole-eInk.jpg')
HEADER_LOGO_PATH = os.path.join(project_dir, 'images', 'black-hole.png')
# Switched to DejaVuSans for better character support (including checkmarks)
FONT_PATH = os.path.join(project_dir, 'fonts', 'DejaVuSans.ttf')
FONT_BOLD_PATH = os.path.join(project_dir, 'fonts', 'DejaVuSans-Bold.ttf')


# --- Constants ---
WHITE = 255
BLACK = 0
FONT_SIZE_HEADER_TITLE = 18
FONT_SIZE_HEADER_DATE = 14
FONT_SIZE_BODY = 15
FONT_SIZE_SMALL = 12

# --- Globals ---
pihole = None
padd_data = {}
last_data_refresh_time = 0
current_screen_index = 0
force_redraw = True

# --- Helper Functions ---
def format_uptime(seconds):
    """Converts seconds into a human-readable Xd Yh Zm format."""
    try:
        secs = int(seconds)
        days = secs // (24 * 3600)
        secs %= (24 * 3600)
        hours = secs // 3600
        secs %= 3600
        minutes = secs // 60
        return f"{days}d {hours}h {minutes}m"
    except (ValueError, TypeError):
        return "N/A"

def compare_versions(version1, version2):
    """
    Compares two version strings numerically.
    Returns:
     1 if version1 > version2
    -1 if version1 < version2
     0 if version1 == version2
    """
    try:
        # Strip leading 'v' or 'V' and split into components
        v1_clean = version1.lstrip('vV')
        v2_clean = version2.lstrip('vV')
        
        v1_parts = [int(part) for part in v1_clean.split('.')]
        v2_parts = [int(part) for part in v2_clean.split('.')]
    except (ValueError, AttributeError):
        # Handle cases where conversion fails (e.g., non-numeric parts)
        return 0 # Treat as equal if format is invalid

    # Pad the shorter version list with zeros for correct comparison
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))

    # Compare part by part
    for i in range(max_len):
        if v1_parts[i] > v2_parts[i]:
            return 1
        if v1_parts[i] < v2_parts[i]:
            return -1

    return 0 # Versions are equal


# --- Data Fetching ---
def refresh_data():
    """Fetches PADD summary data from the Pi-hole v6 API."""
    global last_data_refresh_time, padd_data
    current_time = time.time()
    if current_time - last_data_refresh_time > INFO_REFRESH_INTERVAL_SECONDS or not padd_data:
        logger.info("Refreshing data from Pi-hole API...")
        try:
            padd_data = pihole.get_padd_summary(full=True)
            last_data_refresh_time = current_time
            logger.info("Data refresh complete.")
        except Exception as e:
            logger.error(f"Failed to get data from Pi-hole: {e}")
            padd_data = {}

# --- Drawing Functions ---
def draw_splash_screen(epd, logo_image, width, height):
    """Displays a centered logo on the screen for the splash screen using 4-gray mode."""
    logger.info("Displaying 4-gray splash screen...")
    image = Image.new('L', (width, height), 255) # Grayscale canvas
    draw = ImageDraw.Draw(image)

    if logo_image:
        if logo_image.mode != 'L':
            logo_image = logo_image.convert('L')
        logo_w, logo_h = logo_image.size
        pos_x = (width - logo_w) // 2
        pos_y = (height - logo_h) // 2
        image.paste(logo_image, (pos_x, pos_y))

    else:
        try:
            font = ImageFont.truetype(FONT_PATH, FONT_SIZE_HEADER_TITLE)
        except IOError:
            font = ImageFont.load_default()
            logger.warning(f"Font not found at {FONT_PATH}, using default.")
        msg = "PADD e-Ink Display"
        text_bbox = draw.textbbox((0, 0), msg, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        draw.text(((width - text_width) / 2, (height - text_height) / 2), msg, font=font, fill=0)
    
    epd.display_4Gray(epd.getbuffer_4Gray(image))

def draw_header(draw, width, header_logo_img):
    """Draws the common header on the image."""
    try:
        font_title = ImageFont.truetype(FONT_PATH, FONT_SIZE_HEADER_TITLE)
        font_date = ImageFont.truetype(FONT_PATH, FONT_SIZE_HEADER_DATE)
    except IOError:
        font_title, font_date = ImageFont.load_default(), ImageFont.load_default()
        logger.warning(f"Font not found at {FONT_PATH}, using default.")

    logo_x, logo_y = 5, 5
    title_x = logo_x
    if header_logo_img:
        if header_logo_img.mode != '1':
           header_logo_img  = header_logo_img.convert('1')
           header_logo_img = ImageOps.invert(header_logo_img)
        header_logo_thumb = header_logo_img.copy()
        header_logo_thumb.thumbnail((40, 40))
        draw.bitmap((logo_x, logo_y), header_logo_thumb, fill=BLACK)
        title_x += header_logo_thumb.width + 10

    draw.text((title_x, logo_y), "Pi-hole Stats", font=font_title, fill=BLACK)
    now = datetime.now()
    date_text = now.strftime("%a, %b %d")
    time_text = now.strftime("%H:%M")
    date_y = logo_y + FONT_SIZE_HEADER_TITLE + 3
    draw.text((title_x, date_y), date_text, font=font_date, fill=BLACK)
    
    time_bbox = draw.textbbox((0,0), time_text, font=font_date)
    time_width = time_bbox[2] - time_bbox[0]
    draw.text((width - time_width - 5, date_y), time_text, font=font_date, fill=BLACK)

    line_y = date_y + FONT_SIZE_HEADER_DATE + 5
    draw.line([(0, line_y), (width, line_y)], fill=BLACK, width=1)
    return line_y

def draw_pihole_stats_screen(draw, width, height, data, header_bottom_y):
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

    if not data:
        draw.text((10, y), "No Pi-hole data available.", font=font_small, fill=BLACK)
        return

    # --- Get all required data points with fallbacks ---
    queries_data = data.get('queries', {})
    blocked = queries_data.get('blocked', 0)
    total = queries_data.get('total', 0)
    percent = queries_data.get('percent_blocked', 0.0)
    gravity_size = data.get('gravity_size', 0)
    active_clients = data.get('active_clients', 0)
    
    # --- Line 1: Blocking Info and Percentage Bar ---
    # Draw "Blocking:" in bold
    blocking_label = "Blocking:"
    draw.text((10, y), blocking_label, font=font_small_bold, fill=BLACK)
    
    # Calculate width of bold label to position the next part
    blocking_label_bbox = draw.textbbox((0,0), blocking_label, font=font_small_bold)
    blocking_label_width = blocking_label_bbox[2] - blocking_label_bbox[0]
    
    # Draw the rest of the prefix in regular font
    prefix_remainder = f" {int(gravity_size):,} Piholed: "
    draw.text((10 + blocking_label_width, y), prefix_remainder, font=font_small, fill=BLACK)

    # Calculate total width of the full prefix to position the bar
    prefix_remainder_bbox = draw.textbbox((0,0), prefix_remainder, font=font_small)
    prefix_total_width = blocking_label_width + (prefix_remainder_bbox[2] - prefix_remainder_bbox[0])

    # Position the bar immediately after the text
    bar_height = 15
    bar_x = 10 + prefix_total_width
    bar_y = y - 2 # Vertically align bar with text
    
    bar_width = width - bar_x - 10

    if bar_width > 10:
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=BLACK, fill=WHITE)
        fill_width = int(bar_width * (percent / 100.0))
        if fill_width > 0:
            draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=BLACK)
    else:
        logger.warning("Not enough horizontal space to draw the percentage bar.")
        bar_width = 0

    # --- Line 2: Text below the bar (shifted left) ---
    y = bar_y + bar_height + 2
    bar_text = f"{int(blocked):,} of {int(total):,} ({percent:.1f}%)"
    text_bbox = draw.textbbox((0,0), bar_text, font=font_small)
    text_width = text_bbox[2] - text_bbox[0]

    if bar_width > 0:
        # Shift left by 5 pixels from the centered position
        draw.text((bar_x + (bar_width - text_width) // 2 - 5, y), bar_text, font=font_small, fill=BLACK)
    
    y += FONT_SIZE_SMALL + 10 # Update Y position for the next section

    # --- Draw Top Stats with new formatting ---
    line_height_small = FONT_SIZE_SMALL + 4
    top_stats = {
        "Latest:": data.get('recent_blocked', 'N/A'),
        "Top Ad:": data.get('top_blocked', 'N/A'),
        "Top Dmn:": data.get('top_domain', 'N/A'),
        "Top Clnt:": f"{data.get('top_client', 'N/A')} [Tot Clnts: {active_clients}]"
    }

    for label, value in top_stats.items():
        # Draw bold label on the left
        draw.text((10, y), label, font=font_small_bold, fill=BLACK)

        # Draw right-aligned value
        value_bbox = draw.textbbox((0,0), value, font=font_small)
        value_width = value_bbox[2] - value_bbox[0]
        draw.text((right_align_x - value_width, y), value, font=font_small, fill=BLACK)
        
        y += line_height_small


def draw_system_info_screen(draw, width, height, data, header_bottom_y):
    """Draws the Raspberry Pi system info screen with bold labels and right-aligned values."""
    try:
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
        font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
    except IOError:
        logger.warning(f"Bold or regular font not found, using default.")
        font_bold = ImageFont.load_default()
        font_regular = ImageFont.load_default()

    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 7
    right_align_x = width - 10

    if not data:
        draw.text((10, y), "No system data available.", font=font_regular, fill=BLACK)
        return

    # --- Prepare data ---
    system_data = data.get('system', {})
    hostname = data.get('node_name', 'N/A')
    ip_address = data.get('iface', {}).get('v4', {}).get('addr', 'N/A')
    cpu_load = system_data.get('cpu', {}).get('load', {}).get('percent', [0.0])[0]
    mem_percent = system_data.get('memory', {}).get('ram', {}).get('%used', 0.0)
    cpu_temp = data.get('sensors', {}).get('cpu_temp', 0.0)
    uptime_seconds = system_data.get('uptime', 0)

    # --- Create a dictionary of labels and values to draw ---
    stats_to_draw = {
        "Host:": f"{hostname} ({ip_address})",
        "CPU Load:": f"{cpu_load:.1f}%",
        "Memory:": f"{mem_percent:.1f}%",
        "CPU Temp:": f"{cpu_temp:.1f}°C",
        "Uptime:": format_uptime(uptime_seconds)
    }

    # --- Drawing Loop ---
    for label, value in stats_to_draw.items():
        # Draw bold label on the left
        draw.text((10, y), label, font=font_bold, fill=BLACK)

        # Calculate position for and draw right-aligned value
        value_bbox = draw.textbbox((0, 0), value, font=font_regular)
        value_width = value_bbox[2] - value_bbox[0]
        draw.text((right_align_x - value_width, y), value, font=font_regular, fill=BLACK)
        
        y += line_height


def draw_version_screen(draw, width, height, data, header_bottom_y):
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
    checkmark = "\u2713" # Unicode for checkmark

    version_data = data.get('version')
    if not version_data:
        draw.text((10, y), "Version data not available.", font=font_body, fill=BLACK)
        return
        
    def get_version_status(comp_data):
        """Returns a tuple: (display_string, has_update_bool)"""
        if not comp_data:
            return ("N/A", False)

        local = comp_data.get('local', {}).get('version', 'N/A')
        remote = comp_data.get('remote', {}).get('version', 'N/A')
        
        update_available = False
        if local != 'N/A' and remote != 'N/A':
            if compare_versions(remote, local) > 0:
                update_available = True

        if update_available:
            display_str = f"{local}**"
        else:
            display_str = f"{local} {checkmark}" if local != 'N/A' else "N/A"
        
        return (display_str, update_available)

    component_names = {
        "Pi-hole:": version_data.get('core'),
        "Web UI:": version_data.get('web'),
        "FTL:": version_data.get('ftl')
    }
    right_align_x = width - 10

    for name, comp_data in component_names.items():
        version_str, has_update = get_version_status(comp_data)
        if has_update:
            any_updates = True

        # Draw bold label on the left
        draw.text((10, y), name, font=font_body_bold, fill=BLACK)
        
        # Draw right-aligned version string in regular font
        version_bbox = draw.textbbox((0, 0), version_str, font=font_body)
        version_width = version_bbox[2] - version_bbox[0]
        draw.text((right_align_x - version_width, y), version_str, font=font_body, fill=BLACK)
        
        y += line_height
    
    # --- Display status message at the bottom ---
    y += 5
    if any_updates:
        status_text = "** Update available"
    else:
        status_text = f"{checkmark} {checkmark} SYSTEM IS HEALTHY {checkmark} {checkmark}"

    # Center the status message using the bold small font
    text_bbox = draw.textbbox((0, 0), status_text, font=font_small_bold)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text(((width - text_width) / 2, y), status_text, font=font_small_bold, fill=BLACK)


# --- GPIO Button Handlers (gpiozero style) ---
def handle_button_press(button_pin):
    """Generic handler for all button presses."""
    global current_screen_index, force_redraw, last_data_refresh_time
    logger.info(f"Button press detected on GPIO {button_pin}")

    if button_pin == KEY1_PIN:      # Refresh
        last_data_refresh_time = 0
    elif button_pin == KEY2_PIN:    # Pi-hole Stats
        current_screen_index = 0
    elif button_pin == KEY3_PIN:    # System Stats
        current_screen_index = 1
    elif button_pin == KEY4_PIN:    # Version Stats
        current_screen_index = 2
    force_redraw = True

def main():
    global logger, pihole, current_screen_index, force_redraw

    parser = argparse.ArgumentParser(description="Run the PADD e-Ink display.")
    parser.add_argument('-l', '--level', type=str.upper, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level (default: INFO)')
    parser.add_argument('-f', '--logfile', type=str, default=None, help='Specify a file to write logs to (e.g., padd_display.log)')
    parser.add_argument('-s', '--secure', action='store_true', default=False, help='Connect to Pi-hole using HTTPS')
    parser.add_argument('-t', '--traceback', action='store_true', default=False, help='Force enable rich tracebacks for all log levels.')
    args = parser.parse_args()

    log_level = getattr(logging, args.level, logging.INFO)
    # Use the --traceback flag to override the default behavior
    show_tracebacks = args.traceback

    logger = setup_logging(
        show_locals=True,
        logfile=args.logfile,
        level=log_level,
        rich_tracebacks=show_tracebacks
    )

    logger.info(f"Show tracebacks is {show_tracebacks}")

    
    if not PIHOLE_IP or not API_TOKEN:
        logger.error("PIHOLE_IP and/or API_TOKEN not found in .env file.")
        sys.exit(1)

    protocol = "https" if args.secure else "http"
    pihole = PiHole6Client(f"{protocol}://{PIHOLE_IP}", API_TOKEN)
    logger.info(f"Attempting to connect to Pi-hole at {protocol}://{PIHOLE_IP}")
    logger.info("Starting PADD e-Ink Display...")
    epd = None

    try:
        epd = epaper.epaper('epd2in7_V2').EPD()

        epd.init()
        epd.Clear()
        epd.Init_4Gray()
        logger.info("EPD Initialized in 4-Gray mode.")

        width = epd.height
        height = epd.width
        logger.info(f"Screen dimensions set to {width}x{height}")

        try:
            splash_logo_image = Image.open(LOGO_PATH)
        except FileNotFoundError:
            splash_logo_image = None
            logger.warning(f"Splash screen logo not found: {LOGO_PATH}")
            
        try:
            header_logo_image = Image.open(HEADER_LOGO_PATH)
        except FileNotFoundError:
            header_logo_image = None
            logger.warning(f"Header logo not found: {HEADER_LOGO_PATH}")

        draw_splash_screen(epd, splash_logo_image, width, height)
        time.sleep(SPLASH_SCREEN_DURATION_SECONDS)
        
        logger.info("Re-initializing EPD in B&W mode for main display...")
        epd.init()
        epd.Clear()

        # Initialize buttons using gpiozero
        logger.info("Initializing GPIO Buttons with gpiozero...")
        button1 = Button(KEY1_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S)
        button2 = Button(KEY2_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S)
        button3 = Button(KEY3_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S)
        button4 = Button(KEY4_PIN, pull_up=True, bounce_time=BUTTON_DEBOUNCE_S)

        # Assign a function to the when_pressed event of each button
        button1.when_pressed = lambda: handle_button_press(KEY1_PIN)
        button2.when_pressed = lambda: handle_button_press(KEY2_PIN)
        button3.when_pressed = lambda: handle_button_press(KEY3_PIN)
        button4.when_pressed = lambda: handle_button_press(KEY4_PIN)
        logger.info("GPIO Buttons Initialized.")
        
        screens = [draw_pihole_stats_screen, draw_system_info_screen, draw_version_screen]
        num_screens = len(screens)
        last_screen_rotate_time = time.time()

        while True:
            if time.time() - last_screen_rotate_time > SCREEN_AUTO_ROTATE_INTERVAL_SECONDS:
                current_screen_index = (current_screen_index + 1) % num_screens
                force_redraw = True
                last_screen_rotate_time = time.time()

            if force_redraw:
                refresh_data()
                
                logger.info(f"Drawing screen {current_screen_index + 1}/{num_screens}...")
                image = Image.new('1', (width, height), WHITE)
                draw = ImageDraw.Draw(image)
                header_bottom_y = draw_header(draw, width, header_logo_image)
                
                screens[current_screen_index](draw, width, height, padd_data, header_bottom_y)
                
                epd.display(epd.getbuffer(image))
                logger.info("EPD display updated.")
                force_redraw = False
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Exit signal received.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up...")
        # No need for GPIO.cleanup(), gpiozero handles it automatically
        if epd:
            epd.Clear()
            epd.sleep()
        logger.info("Script finished.")

if __name__ == "__main__":
    main()


