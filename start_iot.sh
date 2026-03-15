#!/bin/bash
# Enable and Start Smart Classroom Service

echo "🔌 Enabling auto-start on boot..."
sudo systemctl enable smart_classroom.service

echo "🚀 Starting Smart Classroom service..."
sudo systemctl start smart_classroom.service

echo "✅ IOT service is now ON and will start automatically on boot."
