#!/bin/bash
echo "====================================================================="
echo " SmartCity Insight AI - Backend Django Channels & REST API (8000)"
echo "====================================================================="
cd "$(dirname "$0")"

# Load local .env if present (gitignored, keeps API keys out of git)
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Ensure PostgreSQL & Redis are running
./run_db.sh || exit 1

if [ -f "./venv/bin/activate" ]; then
    source ./venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
fi

# Enable PostgreSQL + Redis Cache by default for multi-PC shared mode
# Use InMemoryChannelLayer (USE_REDIS=False) since single Daphne process serves all clients
# (avoids channels_redis 4.3.0 + redis 8.1.0 idle socket TimeoutError)
export USE_POSTGRES=${USE_POSTGRES:-True}
export USE_REDIS=${USE_REDIS:-False}
export USE_REDIS_CACHE=${USE_REDIS_CACHE:-True}
export DB_NAME=${DB_NAME:-smartcity_db}
export DB_USER=${DB_USER:-smartcity_user}
export DB_PASSWORD=${DB_PASSWORD:-smartcity_pass}
export DB_HOST=${DB_HOST:-127.0.0.1}
export DB_PORT=${DB_PORT:-5432}

echo "🔄 Applying database migrations on PostgreSQL..."
python3 manage.py migrate --noinput || exit 1

LAN_IP=$(hostname -I | awk '{print $1}')
echo "🚀 Backend listening on http://0.0.0.0:8000 (LAN: http://${LAN_IP}:8000)"
python3 -m daphne -b 0.0.0.0 -p 8000 config.asgi:application
