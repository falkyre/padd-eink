PADD e-Ink Display
A PADD-inspired, button-controlled e-ink display for Pi-hole v6 statistics, designed to run on a Raspberry Pi with a Waveshare 2.7inch e-Paper HAT (V2).

Features
Multiple Screens: Rotates through Pi-hole stats, system stats, and component versions.

GPIO Button Control: Four buttons allow for manual refresh and direct screen selection.

Grayscale Splash Screen: Displays a 4-color grayscale logo on startup.

Modern API: Uses the new Pi-hole v6 API for all data fetching.

Secure Configuration: Credentials are kept out of the code in a .env file.

CLI Tool: Can be installed and run as a system command (padd-eink).

Customizable Logging: Control log level and output file via command-line options.

HTTPS Support: Optional secure connection to the Pi-hole API.

Hardware Requirements
Raspberry Pi (any model with GPIO pins)

Waveshare 2.7inch e-Paper HAT (V2)

An installed and running Pi-hole instance (v6 or newer)

Project Structure
padd-eink/
├── src/
│   └── padd_eink/
│       └── __main__.py       # The main application script
├── fonts/
│   └── DejaVuSans.ttf        # The font for the display
├── images/
│   ├── Pihole-eInk.jpg     # Grayscale splash screen logo
│   └── black-hole.png      # 1-bit B&W header logo
├── .env                        # Your local configuration (create this)
├── .gitignore
├── pyproject.toml              # Project definition and dependencies
└── README.md                   # This file

Setup and Installation
1. Install uv
If you don't have uv, install it first. It's a very fast Python package installer and resolver.

curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
source $HOME/.cargo/env

2. Clone or Create the Project
Clone this repository or create the directory structure and files as shown above.

3. Prepare Environment and Assets
Create .env file: In the project's root directory (padd-eink/), create a file named .env and add your Pi-hole's details:

PIHOLE_IP="192.18.1.10"
API_TOKEN="YOUR_LONG_API_TOKEN_HERE"

Add Fonts and Logos:

Create a fonts directory in the project root and place your font file (e.g., DejaVuSans.ttf) inside it.

Create an images directory in the project root and place your Pihole-eInk.jpg (grayscale) and black-hole.png (1-bit B&W) images inside it.

4. Create a Virtual Environment and Install Dependencies
From the project's root directory, use uv to create a virtual environment and install the required packages.

# Create a virtual environment named .venv
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install the project and its dependencies in editable mode
uv pip install -e .

(Note: You may also need to install the Waveshare libraries manually if they are not available on PyPI. Follow the manufacturer's instructions.)

Usage
Once installed, you can run the display from anywhere on your system (as long as the virtual environment is active) using the padd-eink command.

Basic Usage (Defaults to INFO logging, HTTP connection):

padd-eink

Command-Line Options:

--level or -l: Set the logging level. Options: DEBUG, INFO, WARNING, ERROR, CRITICAL.

--logfile or -f: Specify a file to write logs to.

--secure or -s: Use HTTPS to connect to the Pi-hole API.

Examples:

# Run with DEBUG logging
padd-eink --level DEBUG

# Run and save logs to a file
padd-eink --logfile /var/log/padd_display.log

# Connect to Pi-hole using HTTPS
padd-eink --secure

# Combine options
padd-eink -l DEBUG -f output.log -s

Publishing to PyPI (Optional)
Install Build Tools:

uv pip install build twine

Build the Package:

python -m build

This will create a dist/ directory with the build artifacts.

Upload to PyPI:
You'll need an account on PyPI.

twine upload dist/*

