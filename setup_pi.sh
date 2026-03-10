#!/bin/bash

# Smart Classroom Gadget - Automated Setup Script
# Run this on your Raspberry Pi: curl -sSL https://your-server/setup_pi.sh | bash

echo "🚀 Starting Smart Classroom Gadget Setup..."

# 1. Update and Install System Dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libatlas-base-dev libopenjp2-7 libtiff5 libv4l-dev libjpeg-dev zlib1g-dev

# 2. Setup Directory Structure
INSTALL_DIR="/home/$USER/classroom_monitoring/gadget-python"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 3. Create Virtual Environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 4. Install Python Packages
echo "pip: Installing requirements..."
pip install --upgrade pip
pip install opencv-python-headless onnxruntime sherpa-onnx sounddevice requests pyyaml

# 5. Configure systemd service
echo "⚙️ Configuring auto-start service..."
SERVICE_FILE="smart_classroom.service"

cat <<EOF > $SERVICE_FILE
[Unit]
Description=Smart Classroom Monitoring Gadget
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python main.py
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
echo "1. Edit $INSTALL_DIR/config/config.yaml to set your API URL."
echo "2. Run 'sudo systemctl start smart_classroom.service'."
echo "3. Go to the Super Admin Dashboard to activate this device."
echo "-------------------------------------------------------"
