# Raspberry Pi Quick Start & Deployment Guide

This guide explains how to easily deploy this project on any new Raspberry Pi.

## 1. Prerequisites
- **OS**: Raspberry Pi OS (Raspbian 11 or 12).
- **Environment**: Ensure you have Python 3 installed (standard on most versions).

## 2. Easy Setup (One-Step Script)

1. **Clone the project**:
   ```bash
   git clone git@github.com:premprakashgupta/gadget_python.git gadget-python
   cd gadget-python
   ```

2. **Run the Automated Setup**:
   This script will install system dependencies, create a virtual environment, and download all required AI models.
   ```bash
   chmod +x setup_pi.sh
   ./setup_pi.sh
   ```

3. **Configure the Backend**:
   Edit `config/config.yaml` to point to your laptop or server IP:
   ```yaml
   api:
     url: http://<YOUR_LAPTOP_IP>:4000
   ```

4. **Start the Service**:
   ```bash
   sudo systemctl start smart_classroom.service
   ```

---

## 3. SSH Key Management (No-Password Login)

To "remove" the need for typing a password every time (Passwordless Login), follow these steps.

### A. How to set up Passwordless Login
Run this **from your laptop** (Windows/Mac/Linux) to send your digital "key" to the Pi:
```powershell
# In Windows PowerShell:
ssh-keygen -t rsa  # Press enter through all prompts if you don't have a key yet
ssh-copy-id raspberrypi@raspberrypi.local
```
*Now you can login with just `ssh raspberrypi@raspberrypi.local`!*

### B. How to remove SSH Key Login (Go back to Passwords)
If you want to remove the authorized keys for security reasons:
1. Log in to your Pi.
2. Run this to clear the authorized keys file:
   ```bash
   rm ~/.ssh/authorized_keys
   ```
*This will "remove" the key login and force the Pi to ask for a password again.*

---

## 4. Useful Commands
- **Check if it's running**: `sudo systemctl status smart_classroom.service`
- **See live activity logs**: `journalctl -u smart_classroom.service -f`
- **Restart the system**: `sudo systemctl restart smart_classroom.service`
- **Stop the system**: `sudo systemctl stop smart_classroom.service`
