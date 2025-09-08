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
FONT_PATH = os.path.join(project_dir, 'fonts', 'Roboto-Regular.ttf')


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
        font_body = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
        font_small = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
    except IOError:
        font_body, font_small = ImageFont.load_default(), ImageFont.load_default()
    
    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 4

    if not data:
        draw.text((10, y), "No Pi-hole data available.", font=font_body, fill=BLACK)
        return

    queries_data = data.get('queries', {})
    status = data.get('blocking', 'N/A').capitalize()
    blocked = queries_data.get('blocked', 0)
    total = queries_data.get('total', 0)
    percent = queries_data.get('percent_blocked', 0.0)
    
    # --- New Top Stats ---
    latest_blocked = data.get('recent_blocked', 'N/A')
    top_ad = data.get('top_blocked', 'N/A')
    top_domain = data.get('top_domain', 'N/A')
    top_client = data.get('top_client', 'N/A')

    draw.text((10, y), f"Status: {status}", font=font_body, fill=BLACK)
    y += line_height + 4

    # --- Percentage Bar ---
    bar_x, bar_y = 10, y
    bar_width, bar_height = width - 20, 15
    draw.text((bar_x, bar_y), "Pi-holed:", font=font_small, fill=BLACK)
    bar_y += FONT_SIZE_SMALL + 2

    # Draw bar border
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=BLACK, fill=WHITE)
    # Calculate and draw filled portion
    fill_width = int(bar_width * (percent / 100.0))
    if fill_width > 0:
        draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=BLACK)
    
    # Text below bar
    bar_text = f"{int(blocked):,} of {int(total):,} queries ({percent:.1f}%)"
    text_bbox = draw.textbbox((0,0), bar_text, font=font_small)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text((bar_x + (bar_width - text_width) // 2, bar_y + bar_height + 2), bar_text, font=font_small, fill=BLACK)
    y = bar_y + bar_height + FONT_SIZE_SMALL + 10 # Update Y position

    # --- Draw Top Stats ---
    draw.text((10, y), f"Latest:   {latest_blocked}", font=font_small, fill=BLACK)
    y += line_height
    draw.text((10, y), f"Top Ad:   {top_ad}", font=font_small, fill=BLACK)
    y += line_height
    draw.text((10, y), f"Top Dmn:  {top_domain}", font=font_small, fill=BLACK)
    y += line_height
    draw.text((10, y), f"Top Clnt: {top_client}", font=font_small, fill=BLACK)

def draw_system_info_screen(draw, width, height, data, header_bottom_y):
    """Draws the Raspberry Pi system info screen."""
    try:
        font_body = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
    except IOError:
        font_body = ImageFont.load_default()
    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 7
    if not data:
        draw.text((10, y), "No system data available.", font=font_body, fill=BLACK)
        return

    system_data = data.get('system', {})
    hostname = data.get('node_name', 'N/A')
    # Safely get IP address
    ip_address = data.get('iface', {}).get('v4', {}).get('addr', 'N/A')

    cpu_load = system_data.get('cpu', {}).get('load', {}).get('percent', [0.0])[0]
    mem_percent = system_data.get('memory', {}).get('ram', {}).get('%used', 0.0)
    cpu_temp = data.get('sensors', {}).get('cpu_temp', 0.0)
    uptime_seconds = system_data.get('uptime', 0)

    draw.text((10, y), f"Host: {hostname} ({ip_address})", font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), f"CPU Load: {cpu_load:.1f}%", font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), f"Memory:   {mem_percent:.1f}%", font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), f"CPU Temp: {cpu_temp:.1f}°C", font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), f"Uptime:   {format_uptime(uptime_seconds)}", font=font_body, fill=BLACK)

def draw_version_screen(draw, width, height, data, header_bottom_y):
    """Draws the component versions screen, indicating available updates."""
    try:
        font_body = ImageFont.truetype(FONT_PATH, FONT_SIZE_BODY)
        font_small = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
    except IOError:
        font_body, font_small = ImageFont.load_default(), ImageFont.load_default()
    
    y = header_bottom_y + 10
    line_height = FONT_SIZE_BODY + 10
    any_updates = False

    # Gracefully handle if the entire 'version' key is missing or null
    version_data = data.get('version')
    if not version_data:
        draw.text((10, y), "Version data not available.", font=font_body, fill=BLACK)
        return
        
    def format_version(component_name, comp_data):
        nonlocal any_updates
        # Gracefully handle if a component (e.g., 'core') is missing or null
        if not comp_data:
            return f"{component_name}: N/A"

        local = comp_data.get('local', {}).get('version', 'N/A')
        remote = comp_data.get('remote', {}).get('version', 'N/A')
        
        update_available = False
        # Only compare versions if both are valid strings
        if local != 'N/A' and remote != 'N/A':
            # Use the robust numeric comparison function
            if compare_versions(remote, local) > 0:
                update_available = True

        if update_available:
            any_updates = True
        
        display_str = f"{local}{'**' if update_available else ''}"
        return f"{component_name}: {display_str.ljust(10)}"

    # Safely get each component dictionary, which might be None
    draw.text((10, y), format_version("Pi-hole", version_data.get('core')), font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), format_version("Web UI ", version_data.get('web')), font=font_body, fill=BLACK)
    y += line_height
    draw.text((10, y), format_version("FTL    ", version_data.get('ftl')), font=font_body, fill=BLACK)
    
    if any_updates:
        y += line_height + 5
        draw.text((10, y), "** Update available", font=font_small, fill=BLACK)

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
    args = parser.parse_args()

    log_level = getattr(logging, args.level, logging.INFO)
    # Conditionally enable rich tracebacks only for DEBUG level
    show_tracebacks = (args.level == 'DEBUG')

    show_tracebacks = True #temp

    logger = setup_logging(
        show_locals=True,
        logfile=args.logfile,
        level=log_level,
        rich_tracebacks=show_tracebacks
    )

    
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
                header_end_y = draw_header(draw, width, header_logo_image)
                
                screens[current_screen_index](draw, width, height, padd_data, header_end_y)
                
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


