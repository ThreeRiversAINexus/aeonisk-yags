#!/bin/bash

echo "🔍 Checking Prerequisites for Aeonisk..."
echo "======================================="

# Track if all prerequisites are met
all_good=true

# Function to check if a command exists
check_command() {
    local cmd=$1
    local name=$2
    local install_hint=$3
    
    if command -v "$cmd" &> /dev/null; then
        echo "✅ $name is installed: $(command -v "$cmd")"
        if [[ "$cmd" == "podman" ]]; then
            echo "   Version: $(podman --version)"
        fi
    else
        echo "❌ $name is NOT installed"
        echo "   Install hint: $install_hint"
        all_good=false
    fi
}

# Check required tools
echo ""
echo "📦 Checking required tools:"
echo "--------------------------"
check_command "podman" "Podman" "Visit https://podman.io/getting-started/installation"
check_command "task" "Task (taskfile)" "Visit https://taskfile.dev/installation/"
check_command "curl" "curl" "sudo apt install curl (Ubuntu) or brew install curl (macOS)"

# Check podman compose
echo ""
echo "🐳 Checking Podman Compose:"
echo "--------------------------"
if podman compose version &> /dev/null; then
    echo "✅ Podman Compose is available"
else
    echo "❌ Podman Compose is NOT available"
    echo "   This might be available as 'podman-compose' instead"
    all_good=false
fi

# Check if podman service is running (on Linux with systemd)
echo ""
echo "🔧 Checking Podman service:"
echo "--------------------------"
if command -v systemctl &> /dev/null; then
    if systemctl is-active --quiet podman.socket; then
        echo "✅ Podman socket is active"
    else
        echo "⚠️  Podman socket is not active (this might be okay depending on your setup)"
        echo "   To start: sudo systemctl start podman.socket"
    fi
else
    echo "ℹ️  Not using systemd, skipping podman socket check"
fi

# Check ports availability
echo ""
echo "🔌 Checking port availability:"
echo "-----------------------------"
for port in 5432 6379 8000; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  Port $port is already in use"
        echo "   Process using it: $(lsof -Pi :$port -sTCP:LISTEN 2>/dev/null | tail -1)"
        all_good=false
    else
        echo "✅ Port $port is available"
    fi
done

# Summary
echo ""
echo "======================================="
if $all_good; then
    echo "✅ All prerequisites are met! You can run: task start"
else
    echo "❌ Some prerequisites are missing or there are conflicts."
    echo "   Please resolve the issues above before starting services."
fi
echo ""