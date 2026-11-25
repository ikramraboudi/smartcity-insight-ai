#!/bin/bash
echo "====================================================================="
echo " SmartCity Insight AI - Frontend React Unifié (Port 5173)"
echo "====================================================================="
cd "$(dirname "$0")/frontend"

LAN_IP=$(hostname -I | awk '{print $1}')
echo "🌐 Local URL : http://localhost:5173"
echo "🌐 LAN URL   : http://${LAN_IP}:5173  <-- Open this on PC 2 & PC 3"
echo "====================================================================="

npm run dev -- --host 0.0.0.0 --port 5173
