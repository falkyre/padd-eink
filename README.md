# **PADD e-Ink Display**

An e-ink display for Pi-hole v6 statistics, designed for a Waveshare 2.7-inch e-Paper display on a Raspberry Pi. It provides at-a-glance stats for your Pi-hole server in a low-power format.

## **Features**

* **Three Screens:** Cycles through Pi-hole stats, system vitals, and component versions.  
* **GPIO Button Control:** Four buttons allow for manual refresh and screen selection.  
* **Grayscale Splash Screen:** A 4-color grayscale splash screen on startup.  
* **Modern API:** Uses the new Pi-hole v6 API for data fetching.  
* **Configurable Logging:** Command-line options for log level and file output.  
* **Clean Project Structure:** Managed with uv for easy dependency and environment handling.

## **Hardware Requirements**

* Raspberry Pi (any model with GPIO pins)  
* Waveshare 2.7inch e-Paper HAT (V2)  
* An SD card with Raspberry Pi OS

## **Software Setup with uv**

This guide assumes you have a fresh installation of Raspberry Pi OS with SSH enabled or are working from the desktop.

### **1\. Install uv**

uv is an extremely fast Python package installer and resolver. Install it on your Raspberry Pi with this command:

curl \-LsSf \[https://astral.sh/uv/install.sh\](https://astral.sh/uv/install.sh) | sh

After installation, you may need to source your profile file for uv to be in your PATH:

source \~/.profile  
\# or source \~/.bashrc

### **2\. Set Up the Project**

First, create the project directory and navigate into it.

mkdir \~/padd-eink-display  
cd \~/padd-eink-display

Next, create the necessary subdirectories for the source code, fonts, and images.

mkdir \-p src/padd\_eink fonts images

Now, place the project files (pyproject.toml, README.md, .gitignore, and the main script) into this directory structure. The final layout should look like this:

```
padd-eink-display/  
├── .env  
├── .gitignore  
├── fonts/  
│   ├── DejaVuSans.ttf  
│   └── DejaVuSans-Bold.ttf  
├── images/  
│   ├── Pihole-eInk.jpg  
│   └── black-hole.png  
├── pyproject.toml  
├── README.md  
└── src/  
    └── padd\_eink/  
        └── __main__.py
```

### **3\. Create a Virtual Environment and Install Dependencies**

Use uv to create a virtual environment for the project.

uv venv

This will create a .venv directory. Now, use uv to install all the project dependencies listed in pyproject.toml into this environment.

uv sync

### **4\. Configure Your Pi-hole Credentials**

Create a .env file in the root of the padd-eink-display directory:

nano .env

Add your Pi-hole's IP address and API token to this file:

\# Your Pi-hole's IP address  
PIHOLE\_IP="192.168.1.10"

\# Your Pi-hole API Token (found in Settings \-\> API)  
API\_TOKEN="YOUR\_LONG\_API\_TOKEN\_HERE"

Save the file by pressing Ctrl+X, then Y, then Enter.

### **5\. Add Fonts and Images**

* **Fonts:** Copy the DejaVuSans.ttf and DejaVuSans-Bold.ttf files into the fonts directory. You can usually find these on your Raspberry Pi at /usr/share/fonts/truetype/dejavu/.  
* **Images:** Place your Pihole-eInk.jpg (for the splash screen) and black-hole.png (for the header) into the images directory.

## **Running the Application**

To run the display, use uv run. This command executes a command within the project's virtual environment.

uv run python \-m padd\_eink

The display will initialize, show the splash screen for 10 seconds, and then begin cycling through the data screens.

### **Command-Line Options**

You can customize the application's behavior with the following options:

* \-l LEVEL, \--level LEVEL: Set the logging level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.  
* \-f LOGFILE, \--logfile LOGFILE: Write logs to a specific file.  
* \-s, \--secure: Connect to Pi-hole using HTTPS instead of HTTP.  
* \-t, \--traceback: Force enable detailed error tracebacks for all log levels.

**Example (running with DEBUG logging to a file):**

uv run python \-m padd\_eink \--level DEBUG \--logfile display.log  
