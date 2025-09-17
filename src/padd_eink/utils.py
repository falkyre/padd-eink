import io
import qrcode
import lastversion


def check_padd_eink_version(current_version, output_format="tui"):
    """
    Checks for a new version of PADD-eInk from the GitHub repository.

    Args:
        current_version (str): The current version of the script.
        output_format (str): The format of the output string ('tui' or 'eink').

    Returns:
        str: A formatted string indicating the version status.
    """
    checkmark = "✓"
    repo = "falkyre/padd-eink"
    try:
        latest_version = lastversion.latest(repo, output_format='version', pre=False)
        
        # lastversion.latest returns a Version object, convert to string for compare_versions
        latest_version_str = str(latest_version)

        if compare_versions(latest_version_str, current_version) > 0:
            # New version available
            if output_format == "tui":
                return f"[bold]PADD-eInk:[/bold]	v{latest_version_str} [bold red]**[/bold red]"
            else: # eink
                return f"PADD-eInk:         v{latest_version_str} **"
        else:
            # Up to date
            if output_format == "tui":
                return f"[bold]PADD-eInk:[/bold]	v{current_version} {checkmark}"
            else: # eink
                return f"PADD-eInk:             v{current_version} {checkmark}"
    except Exception:
        # Handle errors (e.g., no internet connection)
        # Return current version without checkmark or stars
        if output_format == "tui":
            return f"[bold]PADD-eInk:[/bold]	v{current_version} ?"
        else: # eink
            return f"PADD-eInk:               v{current_version} ?"


def format_uptime(seconds):
    """Converts seconds into a human-readable Xd Yh Zm format."""
    try:
        secs = int(seconds)
        days = secs // (24 * 3600)
        secs %= 24 * 3600
        hours = secs // 3600
        secs %= 3600
        minutes = secs // 60
        return f"{days}d {hours}h {minutes}m"
    except (ValueError, TypeError):
        return "N/A"


def compare_versions(version1, version2):
    """Compares two version strings numerically."""
    try:
        v1_clean = version1.lstrip("vV")
        v2_clean = version2.lstrip("vV")
        v1_parts = [int(part) for part in v1_clean.split(".")]
        v2_parts = [int(part) for part in v2_clean.split(".")]
    except (ValueError, AttributeError):
        return 0
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    for i in range(max_len):
        if v1_parts[i] > v2_parts[i]:
            return 1
        if v1_parts[i] < v2_parts[i]:
            return -1
    return 0


def generate_ascii_bar(percent: float, total_width: int = 50) -> str:
    """Generates a colored ASCII progress bar string for Rich."""
    filled_count = int(total_width * (percent / 100))
    empty_count = total_width - filled_count

    filled_part = "■" * filled_count
    empty_part = "□" * empty_count  # Using space for empty part

    # Use Rich markup for background colors
    bar_filled = f"[bold red]{filled_part}[/bold red]"
    bar_empty = f"[bold green]{empty_part}[/bold green]"

    return f"{bar_filled}{bar_empty}"


def heatmap_generator(value1, value2=None):
    """
    Generates a heatmap color string based on a percentage.

    The percentage can be provided directly or calculated from two values.

    Args:
        value1 (int or float): If value2 is not provided, this is treated as the
                               percentage. Otherwise, it's the numerator.
        value2 (int or float, optional): The denominator for calculating the
                                         percentage. Defaults to None.

    Returns:
        str: A string representing the color ('green', 'yellow', or 'red').
             Returns an error string if division by zero occurs.
    """
    load = 0
    if value2 is None:
        # If one number is provided, use it as the percentage
        load = round(value1)
    else:
        # If two numbers are provided, calculate the percentage
        if value2 == 0:
            return "Error: Division by zero"
        load = round((value1 / value2) * 100)

    # Color logic based on the percentage
    if load < 75:
        return "lime"
    elif load < 90:
        return "yellow"
    else:
        return "red"


def generate_qrascii(pihole_url: str):
    # Create a QR code object
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,  # Smaller box size for console output
        border=4,
    )

    # Add data to the QR code
    qr.add_data(pihole_url)
    qr.make(fit=True)
    f = io.StringIO()
    qr.print_ascii(out=f)
    f.seek(0)
    qrstr = f.read()
    # Print the QR code to the console
    return qrstr
