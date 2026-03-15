#!/bin/bash
# Smart Classroom Gadget - Automated Setup Script
# Run this on your Raspberry Pi: cd gadget-python && chmod +x setup_pi.sh && ./setup_pi.sh

echo "🚀 Starting Smart Classroom Gadget Setup (Optimized for RPi)..."

# 1. Update and Install System Dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
# We install python3-opencv from apt because building it via pip on RPi is extremely slow/fails.
sudo apt-get install -y python3-venv python3-pip python3-opencv libatlas-base-dev libportaudio2

# 2. Setup Directory Structure
INSTALL_DIR=$(pwd)
echo "📍 Base Directory: $INSTALL_DIR"

# 3. Create Virtual Environment with System Site Packages
# This allows us to use the 'cv2' installed via apt-get
echo "🐍 Creating virtual environment (using system-site-packages for OpenCV)..."
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 4. Install Python Packages
echo "pip: Installing requirements..."
pip install --upgrade pip
# We EXCLUDE onnxruntime here as we now use cv2.dnn for inference
pip install sounddevice requests pyyaml numpy sherpa-onnx

# 5. Run Model Setup
echo "📥 Downloading AI Models..."
python setup_models.py

# 6. Configure systemd service
echo "⚙️ Configuring auto-start service..."
SERVICE_FILE="smart_classroom.service"

cat <<EOF > $SERVICE_FILE
[Unit]
Description=Smart Classroom Monitoring Gadget
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
# Run with unbuffered output to see logs in journalctl immediately
ExecStart=$INSTALL_DIR/.venv/bin/python -u main.py
Restart=always
RestartSec=10
StandardOutput=inherit
StandardError=inherit

[Install]
WantedBy=multi-user.target
EOF

sudo cp $SERVICE_FILE /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smart_classroom.service

echo "✅ Setup Complete!"
echo "-------------------------------------------------------"
echo "Next Steps:"
echo "1. Edit $INSTALL_DIR/config/config.yaml and set your laptop's IP."
echo "2. Run 'sudo systemctl start smart_classroom.service'."
echo "3. Run 'journalctl -u smart_classroom.service -f' to see logs."
echo "-------------------------------------------------------"
