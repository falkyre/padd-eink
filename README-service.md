# **PADD e-Ink Systemd Service**

This guide explains how to install and manage the padd-eink application as a systemd service, ensuring it starts automatically on boot and runs reliably.

## **Step 1: Customize the Service File**

Before installing, you must edit the padd-eink.service file to match your system's configuration.

1. **Find your uv path:** Run the following command in your terminal to find the absolute path to the uv executable:  
   which uv

   The output will be something like /home/pi/.local/bin/uv or /usr/local/bin/uv.  
2. **Find your project path:** Navigate to your project directory and run pwd:  
   cd /path/to/your/padd-eink  
   pwd

   The output will be the absolute path, for example, /home/pi/padd-eink.  
3. **Edit padd-eink.service:** Open the service file and replace the placeholder paths with the values you found above.  
   * Replace /path/to/your/padd-eink with your project's absolute path.  
   * Replace /path/to/your/uv with the absolute path to your uv executable.

## **Step 2: Install the Service**

1. **Copy the file:** Place the customized padd-eink.service file into the systemd system directory.  
   sudo cp padd-eink.service /etc/systemd/system/padd-eink.service

2. **Set permissions:** Ensure the file has the correct permissions.  
   sudo chmod 644 /etc/systemd/system/padd-eink.service

3. **Reload systemd:** Tell systemd to scan for new or changed unit files.  
   sudo systemctl daemon-reload

## **Step 3: Enable and Start the Service**

1. **Enable the service:** This command links the service to the startup process, ensuring it will launch automatically every time you boot your Raspberry Pi.  
   sudo systemctl enable padd-eink.service

2. **Start the service:** You can start the service immediately without needing to reboot.  
   sudo systemctl start padd-eink.service

## **Managing the Service**

Here are the essential commands for managing your padd-eink service.

* **Check Status:** To see if the service is running, view its logs, and check for errors:  
  sudo systemctl status padd-eink.service

  *To view the full logs, use:*  
  sudo journalctl \-u padd-eink.service \-f

  *(Press Ctrl+C to exit the log view)*  
* **Stop the Service:**  
  sudo systemctl stop padd-eink.service

* **Restart the Service:**  
  sudo systemctl restart padd-eink.service

* **Disable the Service:** To prevent the service from starting on boot:  
  sudo systemctl disable padd-eink.service  

