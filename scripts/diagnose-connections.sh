#!/bin/bash

echo "🔍 Diagnosing Database Connections..."
echo "===================================="

# Check PostgreSQL logs for connection attempts
echo ""
echo "📋 Recent PostgreSQL connection attempts:"
echo "----------------------------------------"
podman logs aeonisk-postgres --tail 20 | grep -E "FATAL|ERROR|database" || echo "No recent errors found"

# Check running processes on host
echo ""
echo "🔧 Checking for processes that might be connecting:"
echo "-------------------------------------------------"
# Look for node, python, or other processes that might be connecting
ps aux | grep -E "node|npm|python|drizzle|migrate" | grep -v grep || echo "No relevant processes found"

# Check for any environment files
echo ""
echo "📄 Environment files found:"
echo "-------------------------"
find . -name ".env*" -type f 2>/dev/null | head -10

# Check database configuration in various files
echo ""
echo "🔗 Database configurations found:"
echo "-------------------------------"
grep -r "DATABASE_URL\|DB_\|database:" . \
  --include="*.env*" \
  --include="*.yml" \
  --include="*.yaml" \
  --include="*.json" \
  --include="*.ts" \
  --include="*.js" \
  --exclude-dir=node_modules \
  --exclude-dir=.git \
  2>/dev/null | grep -v "aeonisk_game" | head -20

# Check if any migrations are trying to run
echo ""
echo "📦 Checking for database migration configurations:"
echo "-----------------------------------------------"
find . -name "*migrate*" -o -name "*migration*" | grep -v node_modules | head -10

echo ""
echo "💡 Diagnosis complete. Check the output above for any misconfigurations."