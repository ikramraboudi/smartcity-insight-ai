#!/bin/bash
echo "====================================================================="
echo " SmartCity Insight AI - Backend Django Channels & REST API (8000)"
echo "====================================================================="
cd "$(dirname "$0")"

if [ -f "./venv/bin/activate" ]; then
    source ./venv/bin/activate
fi

python3 -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
