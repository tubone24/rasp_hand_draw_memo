#!/bin/bash
# Install the necessary dependencies
python -m pip install --upgrade pip
pip install poetry
poetry install

# Register the service
cp etc/systemd/system/drawing-app.service /etc/systemd/system/kiosk.service
systemctl daemon-reload
systemctl enable kiosk.service
systemctl restart kiosk.service

# # Register shortcut
cp Desktop/drawing_app.desktop /home/pi/Desktop/drawing_app.desktop
cp Desktop/stop_kiosk.desktop /home/pi/Desktop/stop_kiosk.desktop