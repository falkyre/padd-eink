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
import qrcode
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar
from textual.containers import VerticalScroll, Container
from textual import work


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
BUTTON_HOLD_S = 5 # Time in seconds to hold for QR code

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

# --- Globals for e-Ink Mode ---
padd_data = {}
last_data_refresh_time = 0
current_screen_index = 0
force_redraw = True
qrcode_mode_active = False # New state for QR code screen

# --- Helper Functions (used by both modes) ---
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
    """Compares two version strings numerically."""
    try:
        v1_clean = version1.lstrip('vV')
        v2_clean = version2.lstrip('vV')
        v1_parts = [int(part) for part in v1_clean.split('.')]
        v2_parts = [int(part) for part in v2_clean.split('.')]
    except (ValueError, AttributeError):
        return 0
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    for i in range(max_len):
        if v1_parts[i] > v2_parts[i]: return 1
        if v1_parts[i] < v2_parts[i]: return -1
    return 0

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

def generate_ascii_bar(percent: float, total_width: int = 50) -> str:
    """Generates a colored ASCII progress bar string for Rich."""
    filled_count = int(total_width * (percent / 100))
    empty_count = total_width - filled_count
    
    filled_part = "■" * filled_count
    empty_part = "□" * empty_count # Using space for empty part
    
    # Use Rich markup for background colors
    bar_filled = f"[bold red]{filled_part}[/bold red]"
    bar_empty= f"[bold green]{empty_part}[/bold green]"
   
    return f"{bar_filled}{bar_empty}"

# --- Textual TUI Widgets ---
class PiHoleStats(Static):
    """A widget to display Pi-hole statistics."""

    def on_mount(self) -> None:
        """Set the border title when the widget is mounted."""
        self.border_title = "Pi-hole Stats"
        self.styles.border = ("heavy","white")
        self.styles.border_title_align = "center"

    def update_content(self, padd_data: dict) -> None:
        """Formats and updates the widget's content."""
        if padd_data.get("error"):
            self.update(f"[bold red]{padd_data['error']}[/]")
            return
        if not padd_data:
            self.update("No Pi-hole data available.")
            return

        data = padd_data
        queries = data.get('queries', {})
        percent_blocked = queries.get('percent_blocked', 0.0)
        
        # Generate the ASCII bar
        ascii_bar = generate_ascii_bar(percent_blocked, total_width=40)
        
        lines = [
            f"[bold]Blocking:[/bold]   {data.get('gravity_size', 0):,}",
            f"[bold]Piholed:[/bold]    {ascii_bar} {percent_blocked:.1f}%",
            f"[bold]Queries:[/bold]    {queries.get('blocked', 0):,} of {queries.get('total', 0):,}",
            f"[bold]Latest:[/bold]     {data.get('recent_blocked', 'N/A')}",
            f"[bold]Top Ad:[/bold]     {data.get('top_blocked', 'N/A')}",
            f"[bold]Top Domain:[/bold] {data.get('top_domain', 'N/A')}",
            f"[bold]Top Client:[/bold] {data.get('top_client', 'N/A')}",
            f"[bold]Clients:[/bold]    {data.get('active_clients', 0)}"
        ]
        self.update("\n".join(lines))

class SystemStats(Static):
    """A widget to display system statistics."""
    
    def on_mount(self) -> None:
        self.border_title = "System Stats"
        self.styles.border = ("panel","blue")
        self.styles.border_title_align = "center"
        
    def update_content(self, padd_data: dict) -> None:
        if not padd_data or padd_data.get("error"):
            self.update("") # Clear on error
            return

        data = padd_data
        system = data.get('system', {})
        lines = [
            f"[bold]Host:[/bold]       {data.get('node_name', 'N/A')} ({data.get('iface', {}).get('v4', {}).get('addr', 'N/A')})",
            f"[bold]CPU Load:[/bold]   {system.get('cpu', {}).get('load', {}).get('percent', [0.0])[0]:.1f}%",
            f"[bold]Memory:[/bold]     {system.get('memory', {}).get('ram', {}).get('%used', 0.0):.1f}%",
            f"[bold]CPU Temp:[/bold]   {data.get('sensors', {}).get('cpu_temp', 0.0):.1f}°C",
            f"[bold]Uptime:[/bold]     {format_uptime(system.get('uptime', 0))}"
        ]
        self.update("\n".join(lines))
        
class PiHoleVersions(Container):
    """A widget to display component versions and a refresh progress bar."""

    def compose(self) -> ComposeResult:
        """Create child widgets for the container."""
        yield Static("Loading...", id="version-text")
        yield ProgressBar(total=100, show_eta=False, show_percentage = False, name= "next refresh", id="refresh-progress")

    def on_mount(self) -> None:
        self.border_title = "Component Versions"
        self.styles.border = ("round","green")
        self.styles.border_title_align = "center"

    def update_content(self, padd_data: dict) -> None:
        version_text_widget = self.query_one("#version-text")
        if not padd_data or padd_data.get("error"):
            version_text_widget.update("") # Clear on error
            return

        version_data = padd_data.get('version')
        if not version_data:
            version_text_widget.update("Version data not available.")
            return

        any_updates = False
        checkmark = "\u2713"
        lines = []

        components = {"Pi-hole": "core", "Web UI": "web", "FTL": "ftl"}
        for name, key in components.items():
            comp_data = version_data.get(key)
            if not comp_data:
                lines.append(f"[bold]{name}:[/bold]\tN/A")
                continue
            
            local = comp_data.get('local', {}).get('version', 'N/A')
            remote = comp_data.get('remote', {}).get('version', 'N/A')
            
            status_str = ""
            if local != 'N/A' and remote != 'N/A' and compare_versions(remote, local) > 0:
                any_updates = True
                status_str = f"{local}[bold red]**[/bold red]"
            else:
                status_str = f"{local} {checkmark}" if local != 'N/A' else "N/A"
            lines.append(f"[bold]{name}:[/bold]\t{status_str}")

        if any_updates:
            lines.append("\n[bold red]** Update available[/bold red]")
        else:
            lines.append(f"\n[bold green]{checkmark} {checkmark} SYSTEM IS HEALTHY {checkmark} {checkmark}[/bold green]")

        version_text_widget.update("\n".join(lines))


# --- Textual TUI Application (Main App Class) ---
class PADD_TUI(App):
    """A Textual TUI for Pi-hole statistics."""

    BINDINGS = [
        ("r", "refresh", "Refresh Data"),
        ("q", "quit", "Quit"),
    ]

    TUI_REFRESH_INTERVAL = 60

    def __init__(self, pihole_client):
        super().__init__()
        self.pihole = pihole_client
        self.countdown = self.TUI_REFRESH_INTERVAL

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(name="PADD-eInk Terminal Mode")
        with VerticalScroll(id="main-container"):
            yield PiHoleStats("Loading...")
            yield SystemStats("Loading...")
            yield PiHoleVersions() # Container doesn't need initial content
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.run_update_worker()
        self.set_interval(self.TUI_REFRESH_INTERVAL, self.run_update_worker)
        self.set_interval(1, self.tick_progress_bar) # Timer for progress bar

    def tick_progress_bar(self) -> None:
        """Updates the progress bar every second."""
        self.countdown -= 1
        progress = (self.countdown / self.TUI_REFRESH_INTERVAL) * 100
        self.query_one(ProgressBar).progress = progress

    def run_update_worker(self) -> None:
        """Initiates the background data fetching worker and resets countdown."""
        self.countdown = self.TUI_REFRESH_INTERVAL # Reset countdown on refresh
        self.update_data()

    @work(thread=True, exclusive=True)
    def update_data(self) -> None:
        """Fetches new data and updates the widgets from a background thread."""
        logger.info("TUI: Refreshing data in worker...")
        try:
            padd_data = self.pihole.get_padd_summary(full=True)
            
            # Call the update methods on each custom widget
            self.call_from_thread(self.query_one(PiHoleStats).update_content, padd_data)
            self.call_from_thread(self.query_one(SystemStats).update_content, padd_data)
            self.call_from_thread(self.query_one(PiHoleVersions).update_content, padd_data)
            
            logger.info("TUI: Display updated by worker.")
        except Exception as e:
            error_message = f"Error fetching data: {e}"
            logger.error(error_message)
            self.call_from_thread(self.query_one(PiHoleStats).update_content, {"error": error_message})


    def action_refresh(self) -> None:
        """Called when the user presses the 'r' key."""
        # Update widgets to show a refreshing message
        self.query_one(PiHoleStats).update("Refreshing...")
        self.query_one(SystemStats).update("Refreshing...")
        self.query_one(PiHoleVersions).query_one("#version-text").update("Refreshing...")
        self.run_update_worker()

    def action_quit(self) -> None:
        """Called when the user presses the 'q' key."""
        self.exit()

# --- e-Ink Drawing Functions ---
def draw_splash_screen(epd, logo_image, width, height):
    logger.info("Displaying 4-gray splash screen...")
    image = Image.new('L', (width, height), 255)
    draw = ImageDraw.Draw(image)
    if logo_image:
        logo_w, logo_h = logo_image.size
        pos_x = (width - logo_w) // 2
        pos_y = (height - logo_h) // 2
        image.paste(logo_image.convert('L'), (pos_x, pos_y))
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
        draw.bitmap((logo_x, logo_y), header_logo_thumb.convert('1'), fill=BLACK)
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

def draw_qrcode_screen(draw, width, height, url):
    try:
        font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE_BODY)
    except IOError:
        font_regular, font_bold = ImageFont.load_default(), ImageFont.load_default()
    
    title_text = "Pi-Hole Admin"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_bold)
    title_width, title_height = title_bbox[2], title_bbox[3]
    title_y = 4
    draw.text(((width - title_width) / 2, title_y), title_text, font=font_bold, fill=BLACK)

    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('1')
    qr_pos_x = (width - qr_img.size[0]) // 2
    qr_pos_y = title_y + title_height + 10
    draw.bitmap((qr_pos_x, qr_pos_y), qr_img, fill=BLACK)

    instruction_text = "Hold key 1 button to close"
    inst_bbox = draw.textbbox((0, 0), instruction_text, font=font_regular)
    inst_width = inst_bbox[2]
    inst_y = qr_pos_y + qr_img.size[1] + 5
    draw.text(((width - inst_width) / 2, inst_y), instruction_text, font=font_regular, fill=BLACK)

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
    line_height_small = FONT_SIZE_SMALL + 4

    if not data:
        draw.text((10, y), "No Pi-hole data available.", font=font_small, fill=BLACK)
        return

    # --- Get all required data points with fallbacks ---
    queries_data = data.get('queries', {})
    blocked = queries_data.get('blocked', 0)
    total = queries_data.get('total', 0)
    percent = queries_data.get('percent_blocked', 0.0)
    gravity_size = data.get('gravity_size', 0)
    
    # --- Line 1: Blocking Info ---
    blocking_label = "Blocking:"
    blocking_value = f"{int(gravity_size):,}"
    draw.text((10, y), blocking_label, font=font_small_bold, fill=BLACK)
    value_bbox = draw.textbbox((0,0), blocking_value, font=font_small)
    value_width = value_bbox[2] - value_bbox[0]
    draw.text((right_align_x - value_width, y), blocking_value, font=font_small, fill=BLACK)
    y += line_height_small

    # --- Line 2: Piholed Percentage Bar and Text (New Layout) ---
    piholed_label = "Piholed:"
    draw.text((10, y), piholed_label, font=font_small_bold, fill=BLACK)

    piholed_label_bbox = draw.textbbox((0,0), piholed_label, font=font_small_bold)
    piholed_label_width = piholed_label_bbox[2] - piholed_label_bbox[0]
    
    # Position the text immediately after the label
    bar_text = f" {int(blocked):,} of {int(total):,} ({percent:.1f}%)"
    draw.text((10 + piholed_label_width, y), bar_text, font=font_small, fill=BLACK)
    
    bar_text_bbox = draw.textbbox((0,0), bar_text, font=font_small)
    bar_text_width = bar_text_bbox[2] - bar_text_bbox[0]

    bar_height = 15
    bar_y = y - 2
    
    # Bar starts after the label and the text
    bar_x = 10 + piholed_label_width + bar_text_width + 5 # 5px gap
    
    # Bar width is the remaining space
    bar_width = width - bar_x - 10 # 10px right margin
    
    if bar_width > 10:
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=BLACK, fill=WHITE)
        fill_width = int(bar_width * (percent / 100.0))
        if fill_width > 0:
            draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=BLACK)
    else:
        logger.warning("Not enough horizontal space for percentage bar.")

    y += bar_height # Move y down for next section

    # --- Draw Top Stats with new formatting ---
    top_stats = {
        "Latest:": data.get('recent_blocked', 'N/A'),
        "Top Ad:": data.get('top_blocked', 'N/A'),
        "Top Domain:": data.get('top_domain', 'N/A'),
        "Top Client:": data.get('top_client', 'N/A'),
        "Clients:": f"{data.get('active_clients')}"
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
    
    system_data = data.get('system', {})
    stats_to_draw = {
        "Host:": f"{data.get('node_name', 'N/A')} ({data.get('iface', {}).get('v4', {}).get('addr', 'N/A')})",
        "CPU Load:": f"{system_data.get('cpu', {}).get('load', {}).get('percent', [0.0])[0]:.1f}%",
        "Memory:": f"{system_data.get('memory', {}).get('ram', {}).get('%used', 0.0):.1f}%",
        "CPU Temp:": f"{data.get('sensors', {}).get('cpu_temp', 0.0):.1f}°C",
        "Uptime:": format_uptime(system_data.get('uptime', 0))
    }
    for label, value in stats_to_draw.items():
        draw.text((10, y), label, font=font_bold, fill=BLACK)
        value_bbox = draw.textbbox((0, 0), value, font=font_regular)
        draw.text((right_align_x - value_bbox[2], y), value, font=font_regular, fill=BLACK)
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
    

# --- e-Ink GPIO Button Handlers ---
def handle_short_press(button_pin):
    global current_screen_index, force_redraw, qrcode_mode_active
    if qrcode_mode_active: return
    logger.info(f"Short press detected on GPIO {button_pin}")
    if button_pin == KEY2_PIN: current_screen_index = 0
    elif button_pin == KEY3_PIN: current_screen_index = 1
    elif button_pin == KEY4_PIN: current_screen_index = 2
    force_redraw = True

def handle_refresh_press():
    global last_data_refresh_time, force_redraw, qrcode_mode_active
    if qrcode_mode_active: return
    logger.info("Short press detected on refresh button.")
    last_data_refresh_time = 0
    force_redraw = True

def handle_qrcode_toggle():
    global qrcode_mode_active, force_redraw
    logger.info("Long press detected, toggling QR code mode.")
    qrcode_mode_active = not qrcode_mode_active
    force_redraw = True

# --- Main Dispatcher & e-Ink Runner ---
def run_eink_display(pihole_client, pihole_url):
    """Initializes and runs the e-Ink display loop."""
    global padd_data, force_redraw, current_screen_index, last_data_refresh_time, qrcode_mode_active, pihole
    pihole = pihole_client
    epd = None
    try:
        epd = epaper.epaper('epd2in7_V2').EPD()
        epd.init()
        epd.Clear()
        epd.Init_4Gray()
        logger.info("EPD Initialized in 4-Gray mode.")
        width, height = epd.height, epd.width
        logger.info(f"Screen dimensions set to {width}x{height}")

        splash_logo_image = Image.open(LOGO_PATH) if os.path.exists(LOGO_PATH) else None
        header_logo_image = Image.open(HEADER_LOGO_PATH) if os.path.exists(HEADER_LOGO_PATH) else None

        draw_splash_screen(epd, splash_logo_image, width, height)
        time.sleep(10)
        
        epd.init()
        epd.Clear()

        button1 = Button(KEY1_PIN, pull_up=True, bounce_time=0.3, hold_time=5)
        button2, button3, button4 = Button(KEY2_PIN, pull_up=True, bounce_time=0.3), Button(KEY3_PIN, pull_up=True, bounce_time=0.3), Button(KEY4_PIN, pull_up=True, bounce_time=0.3)
        button1.when_pressed, button1.when_held = handle_refresh_press, handle_qrcode_toggle
        button2.when_pressed, button3.when_pressed, button4.when_pressed = lambda: handle_short_press(KEY2_PIN), lambda: handle_short_press(KEY3_PIN), lambda: handle_short_press(KEY4_PIN)
        
        screens = [draw_pihole_stats_screen, draw_system_info_screen, draw_version_screen]
        num_screens = len(screens)
        last_screen_rotate_time = time.time()

        while True:
            if not qrcode_mode_active and time.time() - last_screen_rotate_time > 20:
                current_screen_index = (current_screen_index + 1) % num_screens
                force_redraw = True
                last_screen_rotate_time = time.time()

            if force_redraw:
                image = Image.new('1', (width, height), WHITE)
                draw = ImageDraw.Draw(image)
                if qrcode_mode_active:
                    draw_qrcode_screen(draw, width, height, pihole_url)
                else:
                    refresh_data()
                    logger.info(f"Drawing screen {current_screen_index + 1}/{num_screens}...")
                    header_bottom_y = draw_header(draw, width, header_logo_image)
                    screens[current_screen_index](draw, width, height, padd_data, header_bottom_y)
                    
                epd.display(epd.getbuffer(image))
                logger.info("EPD display updated.")
                force_redraw = False
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Exit signal received.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in e-Ink mode: {e}", exc_info=True)
    finally:
        if epd:
            epd.Clear()
            epd.sleep()

def main():
    global logger
    parser = argparse.ArgumentParser(description="Run the PADD e-Ink display.")
    parser.add_argument('-T', '--tui', action='store_true', default=False, help='Run in terminal UI mode instead of e-Ink display.')
    parser.add_argument('-l', '--level', type=str.upper, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level (default: INFO)')
    parser.add_argument('-f', '--logfile', type=str, default=None, help='Specify a file to write logs to')
    parser.add_argument('-s', '--secure', action='store_true', default=False, help='Connect to Pi-hole using HTTPS')
    parser.add_argument('-t', '--traceback', action='store_true', default=False, help='Force enable rich tracebacks')
    args = parser.parse_args()

    logger = setup_logging(level=getattr(logging, args.level), logfile=args.logfile, rich_tracebacks=args.traceback)
    
    if not PIHOLE_IP or not API_TOKEN:
        logger.critical("PIHOLE_IP and/or API_TOKEN not found in .env file.")
        sys.exit(1)

    protocol = "https" if args.secure else "http"
    pihole_url = f"{protocol}://{PIHOLE_IP}/admin/"
    pihole_client = PiHole6Client(f"{protocol}://{PIHOLE_IP}", API_TOKEN)
    logger.info(f"Connecting to Pi-hole at {protocol}://{PIHOLE_IP}")

    if args.tui:
        app = PADD_TUI(pihole_client=pihole_client)
        app.run()
    else:
        run_eink_display(pihole_client=pihole_client, pihole_url=pihole_url)

if __name__ == "__main__":
    main()


