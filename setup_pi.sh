#!/bin/bash
# Smart Classroom Gadget - Automated Setup Script
# Run this on your Raspberry Pi: cd gadget-python && chmod +x setup_pi.sh && ./setup_pi.sh

# 1. Interactive Checks
echo "-------------------------------------------------------"
echo "🔍 Checking system state..."

# Check if service is active
SERVICE_STATUS=$(sudo systemctl is-active smart_classroom.service)
if [ "$SERVICE_STATUS" == "active" ]; then
    echo "⚠️  WARNING: Smart Classroom Service is currently RUNNING."
    read -p "Do you want to STOP the service to proceed with setup? (y/n): " confirm_stop
    if [[ ! $confirm_stop =~ ^[Yy]$ ]]; then
        echo "❌ Setup cancelled by user."
        exit 1
    fi
    echo "🛑 Stopping service..."
    sudo systemctl stop smart_classroom.service
fi

# Confirm Re-deployment
read -p "Do you want to proceed with FULL RE-DEPLOYMENT? (y/n): " confirm_deploy
if [[ ! $confirm_deploy =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled."
    exit 0
fi

# 2. Setup Logging
LOG_FILE="setup_log.txt"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "-------------------------------------------------------"
echo "🚀 Starting Smart Classroom Gadget Setup: $(date)"
echo "📝 Full log will be saved to: $(pwd)/$LOG_FILE"
echo "-------------------------------------------------------"

# 3. Update and Install System Dependencies
echo "📦 Step 1: Installing system dependencies..."
sudo apt-get update
# We install python3-opencv from apt because building it via pip on RPi is extremely slow/fails.
# libatlas-base-dev and libportaudio2 are required for numpy and sounddevice.
sudo apt-get install -y python3-venv python3-pip python3-opencv libatlas-base-dev libportaudio2

# 4. Setup Directory Structure
echo "📍 Step 2: Setting up directory structure..."
INSTALL_DIR=$(pwd)
echo "   Base Directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/config"

# 5. Create Virtual Environment with System Site Packages
# This allows us to use the 'cv2' and other system-provided AI/Vision libraries.
echo "🐍 Step 3: Creating Python virtual environment..."
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 6. Install Python Packages
echo "pip: Installing requirements..."
pip install --upgrade pip
# We EXCLUDE onnxruntime here as we now use cv2.dnn for high-performance vision on RPi.
# Pillow is required for image processing in the Vision Engine.
pip install sounddevice requests pyyaml numpy sherpa-onnx Pillow

# 7. Run Model Setup
echo "📥 Step 4: Downloading/Verifying AI Models..."
python setup_models.py

# 8. Configure config.yaml
# config.yaml is in .gitignore to prevent checking in machine-specific settings or secrets.
echo "⚙️ Step 5: Configuring config.yaml..."
CONFIG_FILE="$INSTALL_DIR/config/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "   Generating default config.yaml..."
    cat <<EOF > "$CONFIG_FILE"
api:
  url: http://10.145.70.89:4000  # Defaulting to your laptop IP
cloud:
  enabled: false
  provider: google_drive
monitoring:
  camera_index: 0
  end_time: '22:00'
  interval_seconds: 5
  snapshot_interval_seconds: 30
  start_time: '08:00'
  transcript_interval_seconds: 25
sherpa:
  model_dir: models/sherpa-onnx-whisper-tiny.en
  sample_rate: 16000
storage:
  captures_dir: data/captures
  known_faces_dir: data/known_faces
  reports_dir: data/reports
EOF
    echo "   ✅ Created $CONFIG_FILE. Please edit it if your IP changes."
else
    echo "   ✅ $CONFIG_FILE already exists. Skipping creation."
fi

# 9. Database Clean/Setup
if [ -f "data/local.db" ]; then
    echo "🧹 Cleaning up legacy database: data/local.db"
    rm "data/local.db"
fi

# 10. Configure systemd service
echo "⚙️ Step 6: Configuring auto-start service..."
SERVICE_FILE="smart_classroom.service"

cat <<EOF > $SERVICE_FILE
[Unit]
Description=Smart Classroom Monitoring Gadget
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
# Run with unbuffered output (-u) so logs appear in real-time in journalctl
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

echo "-------------------------------------------------------"
echo "✅ Setup Complete at $(date)!"
echo "-------------------------------------------------------"
echo "Next Steps:"
echo "1. Run 'sudo systemctl start smart_classroom.service' to begin."
echo "2. Run 'journalctl -u smart_classroom.service -f' to see live activity."
echo "3. Visit the Super Admin Dashboard to activate this device."
echo "-------------------------------------------------------"
