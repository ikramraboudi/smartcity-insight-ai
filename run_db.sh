#!/bin/bash
echo "====================================================================="
echo " SmartCity Insight AI - PostgreSQL/PostGIS (5432) & Redis (6379)"
echo "====================================================================="

DB_NAME=${DB_NAME:-smartcity_db}
DB_USER=${DB_USER:-smartcity_user}
DB_PASSWORD=${DB_PASSWORD:-smartcity_pass}
PG_IMAGE="postgis/postgis:16-3.4"

# Create persistent volumes if needed
docker volume create smartcity_pgdata >/dev/null 2>&1
docker volume create smartcity_redisdata >/dev/null 2>&1

# Upgrade container image to PostGIS if an older non-PostGIS image was used
if [ "$(docker ps -aq -f name=^smartcity_postgres$)" ]; then
    CURRENT_IMG=$(docker inspect -f '{{.Config.Image}}' smartcity_postgres 2>/dev/null)
    if [ "$CURRENT_IMG" != "$PG_IMAGE" ]; then
        echo "🔄 Upgrading smartcity_postgres container to $PG_IMAGE (keeping smartcity_pgdata)..."
        docker rm -f smartcity_postgres >/dev/null 2>&1
    fi
fi

# Start or create PostgreSQL/PostGIS container
if [ "$(docker ps -aq -f name=^smartcity_postgres$)" ]; then
    docker start smartcity_postgres >/dev/null
    echo "✅ PostgreSQL/PostGIS container (smartcity_postgres) started."
else
    docker run -d \
        --name smartcity_postgres \
        --restart unless-stopped \
        -e POSTGRES_DB="$DB_NAME" \
        -e POSTGRES_USER="$DB_USER" \
        -e POSTGRES_PASSWORD="$DB_PASSWORD" \
        -p 127.0.0.1:5432:5432 \
        -v smartcity_pgdata:/var/lib/postgresql/data \
        "$PG_IMAGE"
    echo "✅ PostgreSQL/PostGIS container (smartcity_postgres) created and started."
fi

# Start or create Redis container
if [ "$(docker ps -aq -f name=^smartcity_redis$)" ]; then
    docker start smartcity_redis >/dev/null
    echo "✅ Redis container (smartcity_redis) started."
else
    docker run -d \
        --name smartcity_redis \
        --restart unless-stopped \
        -p 127.0.0.1:6379:6379 \
        -v smartcity_redisdata:/data \
        redis:7-alpine
    echo "✅ Redis container (smartcity_redis) created and started."
fi

echo "⏳ Waiting for PostgreSQL/PostGIS to be ready..."
for i in $(seq 1 30); do
    if docker exec smartcity_postgres pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        echo "✅ PostgreSQL/PostGIS is ready on 127.0.0.1:5432 (DB: $DB_NAME)."
        exit 0
    fi
    sleep 1
done

echo "❌ PostgreSQL/PostGIS did not become ready in time."
exit 1
