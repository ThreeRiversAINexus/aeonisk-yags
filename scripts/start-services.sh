#!/bin/bash
set -e

echo "🎮 Starting Aeonisk Services..."
echo "================================"

# Function to check if a container is running
is_running() {
  podman ps --format "{{.Names}}" | grep -q "^$1$"
}

# Function to check if a container exists (running or stopped)
container_exists() {
  podman ps -a --format "{{.Names}}" | grep -q "^$1$"
}

# Start services with podman compose
echo "🐳 Starting containers with podman compose..."
podman compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."

# Wait for PostgreSQL
echo -n "  PostgreSQL: "
until podman exec aeonisk-postgres pg_isready -U aeonisk > /dev/null 2>&1; do
  echo -n "."
  sleep 1
done
echo " ✅"

# Wait for Redis
echo -n "  Redis: "
until podman exec aeonisk-redis redis-cli ping > /dev/null 2>&1; do
  echo -n "."
  sleep 1
done
echo " ✅"

# Wait for ChromaDB
echo -n "  ChromaDB: "
until curl -s http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; do
  echo -n "."
  sleep 1
done
echo " ✅"

# Initialize databases
echo ""
echo "📦 Initializing databases..."
bash scripts/init-databases.sh

# Display service status
echo ""
echo "📊 Service Status:"
echo "=================="
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep aeonisk || true

echo ""
echo "✨ All services are up and running!"
echo ""
echo "🔗 Service URLs:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo "  - ChromaDB: http://localhost:8000"
echo ""
echo "💡 To view logs: podman compose logs -f [service-name]"
echo "💡 To stop services: podman compose down"