#!/bin/bash
# Stop and Disable Smart Classroom Service (for development)

echo "🛑 Stopping Smart Classroom service..."
sudo systemctl stop smart_classroom.service

echo "🔌 Disabling auto-start on boot..."
sudo systemctl disable smart_classroom.service

echo "✅ IOT service is now OFF and won't start automatically."
echo "You can now run 'python main.py' manually for development."
