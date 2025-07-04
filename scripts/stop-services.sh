#!/bin/bash

echo "🛑 Stopping Aeonisk Services..."
echo "================================"

# Stop services gracefully
echo "📦 Stopping containers..."
podman compose down

# Optional: Remove volumes (uncomment if you want to reset data)
# echo "🗑️  Removing volumes..."
# podman compose down -v

echo ""
echo "✅ All services stopped successfully!"
echo ""
echo "💡 To restart services: bash scripts/start-services.sh"
echo "💡 To remove all data: podman compose down -v"