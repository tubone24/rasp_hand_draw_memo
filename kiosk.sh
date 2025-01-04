#!/bin/bash
#xset s noblank
#xset s off
#xset -dpms

sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' ~/.config/chromium/Default/Preferences
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' ~/.config/chromium/Default/Preferences

/usr/bin/chromium-browser \
  --noerrdialogs \
  --disable-infobars \
  --kiosk \
  --start-maximized \
  --start-fullscreen \
  --window-size=$(xdpyinfo | grep dimensions | awk '{print $2}' | tr 'x' ',') \
  --enable-features=OverlayScrollbar \
  http://localhost:8050