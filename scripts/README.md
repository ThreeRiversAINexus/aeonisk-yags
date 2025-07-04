# Aeonisk Service Management Scripts

This directory contains scripts to manage the Aeonisk game services smoothly.

## 🚀 Quick Start

```bash
# Start all services
task start

# Stop all services
task stop

# Check service status
task status

# View logs
task logs
```

## 📋 Available Scripts

### start-services.sh
Starts all required services (PostgreSQL, Redis, ChromaDB) and ensures they're healthy before proceeding.

```bash
bash scripts/start-services.sh
# or
task start
```

### stop-services.sh
Gracefully stops all services.

```bash
bash scripts/stop-services.sh
# or
task stop
```

### init-databases.sh
Initializes the required databases. This is automatically called by start-services.sh but can be run manually if needed.

```bash
bash scripts/init-databases.sh
# or
task db:init
```

### diagnose-connections.sh
Helps diagnose connection issues by checking logs, configurations, and running processes.

```bash
bash scripts/diagnose-connections.sh
# or
task diagnose
```

## 🗄️ Database Information

The system uses two databases for compatibility:
- **aeonisk_game** - Primary database for the game
- **aeonisk** - Legacy database for backward compatibility

Both databases are created automatically to prevent connection errors.

## 🔧 Troubleshooting

### Services won't start
1. Check if containers already exist: `podman ps -a`
2. Remove old containers: `task clean`
3. Try starting again: `task start`

### Database connection errors
1. Run diagnosis: `task diagnose`
2. Check logs: `task logs`
3. Reinitialize databases: `task db:init`

### Complete reset
If you need to start fresh (WARNING: This deletes all data):
```bash
task clean:all
task start
```

## 🔗 Service URLs

When running, services are available at:
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`
- **ChromaDB**: `http://localhost:8000`

## 📝 Task Commands

View all available tasks:
```bash
task
```

Common tasks:
- `task start` - Start all services
- `task stop` - Stop all services
- `task restart` - Restart all services
- `task status` - Check service status
- `task logs` - View service logs
- `task db:psql` - Connect to PostgreSQL
- `task db:redis` - Connect to Redis CLI
- `task diagnose` - Diagnose connection issues