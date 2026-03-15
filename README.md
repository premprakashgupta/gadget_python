# Smart Classroom Gadget - IOT Monitoring

This project transforms a Raspberry Pi into an automated classroom monitoring device.

## 🚀 One-Click Setup
If you are on a new Raspberry Pi, run this command once to install everything (Dependencies, Virtual Environment, and AI Models):
```bash
chmod +x setup_pi.sh
./setup_pi.sh
```

## 🎮 How to Run

### 1. Manual Run (Development)
To run the project manually on your laptop or Pi:
```bash
python run.py
```
*Note: This automatically handles virtual environment activation and model checks.*

### 2. IOT Mode (Automatic Startup)
The project is configured to start automatically when the Pi boots. You can control this using the following scripts:

- **Turn OFF IOT Service**:
  ```bash
  ./stop_iot.sh
  ```
  *(Stops the program and disables auto-start—use this for development)*

- **Turn ON IOT Service**:
  ```bash
  ./start_iot.sh
  ```
  *(Re-enables auto-start and starts the monitoring system immediately)*

## 📂 Key Files
- `setup_pi.sh`: The automated installer for Raspberry Pi.
- `run.py`: The main entry point for manual execution.
- `config/config.yaml`: Configuration (API IP, timings, camera index).
- `data/gadget_local.db`: Local database buffer for logs.

## 📝 Logs
- **Setup Logs**: Check `setup_log.txt` if the installer fails.
- **System Logs**: Run `journalctl -u smart_classroom.service -f` to see live activity of the background service.
