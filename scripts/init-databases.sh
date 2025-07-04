#!/bin/bash
set -e

echo "🚀 Initializing Aeonisk databases..."

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until podman exec aeonisk-postgres pg_isready -U aeonisk > /dev/null 2>&1; do
  echo -n "."
  sleep 1
done
echo " ✅ PostgreSQL is ready!"

# Create both databases to avoid connection errors
echo "📦 Creating databases..."

# Create aeonisk_game database (primary)
podman exec aeonisk-postgres psql -U aeonisk -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'aeonisk_game'" | grep -q 1 || \
  podman exec aeonisk-postgres createdb -U aeonisk aeonisk_game && echo "✅ Created aeonisk_game database"

# Create aeonisk database (for legacy compatibility)
podman exec aeonisk-postgres psql -U aeonisk -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'aeonisk'" | grep -q 1 || \
  podman exec aeonisk-postgres createdb -U aeonisk aeonisk && echo "✅ Created aeonisk database (legacy)"

# Verify databases exist
echo "🔍 Verifying databases..."
podman exec aeonisk-postgres psql -U aeonisk -d postgres -c "\l" | grep aeonisk

echo "✨ Database initialization complete!"