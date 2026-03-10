# Raspberry Pi Deployment Guide

To ensure the monitoring gadget starts automatically whenever the Raspberry Pi is turned on, follow these steps:

## 1. Prepare the Environment

> [!TIP]
> **Use Raspberry Pi OS (64-bit)** for the best performance and compatibility with AI models like ONNX and Sherpa.

First, update your system and install necessary vision and audio dependencies:
```bash
sudo apt-get update
sudo apt-get install -y libatlas-base-dev libopenjp2-7 libtiff5 libv4l-dev libjpeg-dev zlib1g-dev libportaudio2
```

## 2. Clone and Setup
Move the `gadget-python` folder to `/home/pi/classroom_monitoring/`.

Create a virtual environment and install requirements:
```bash
cd /home/pi/classroom_monitoring/gadget-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configuration
Edit `config/config.yaml` to set your:
- `api_url`: Your central Node.js server address.
- `school_id`: The ID of this school.
- `device_secret`: The secret key obtained from the Super Admin portal.

## 4. Install Auto-Start Service (systemd)

Copy the provided service file and enable it:
```bash
sudo cp smart_classroom.service /etc/systemd/system/smart_classroom.service
sudo systemctl daemon-reload
sudo systemctl enable smart_classroom.service
sudo systemctl start smart_classroom.service
```

## 5. How it Works on Startup
1. **Boot**: Raspberry Pi powers on and connects to the internet.
2. **Service Initiation**: `systemd` detects the enabled `smart_classroom.service` and executes it.
3. **Internal Check**: The script waits until 09:00 AM (as per config) to start the camera.
4. **Auto-Restart**: If the script crashes or the camera is temporarily unplugged, the service will automatically try to restart every 10 seconds.
5. **Logs**: You can check the live status using:
   ```bash
   journalctl -u smart_classroom.service -f
   ```
