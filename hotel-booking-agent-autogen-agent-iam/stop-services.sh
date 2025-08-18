#!/bin/bash

# Stop Services Script - Companion to start-services.sh
# This script stops all services started by start-services.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_status "Stopping Hotel Booking Application Services"
echo "=========================================="

# Function to stop service by PID file
stop_service() {
    local service_name=$1
    local pid_file="logs/${service_name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            print_status "Stopping $service_name service (PID: $pid)..."
            kill $pid
            sleep 2
            
            # Force kill if still running
            if ps -p $pid > /dev/null 2>&1; then
                print_warning "Force killing $service_name service..."
                kill -9 $pid 2>/dev/null || true
            fi
            
            print_success "$service_name service stopped"
        else
            print_warning "$service_name service was not running"
        fi
        rm -f "$pid_file"
    else
        print_warning "No PID file found for $service_name service"
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    local service_name=$2
    local pid=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pid" ]; then
        print_status "Killing $service_name on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null || true
        print_success "$service_name stopped"
    fi
}

# Stop services using PID files
stop_service "backend"
stop_service "assistant_agent"
stop_service "staff_management_agent" 
stop_service "frontend"

# Fallback: kill processes on known ports
print_status "Cleaning up any remaining processes on service ports..."
kill_port 8001 "API service"
kill_port 8000 "Assistant Agent service"
kill_port 8002 "Staff Management Agent service"
kill_port 3000 "Frontend service"

# Clean up log files (optional)
read -p "Do you want to clear log files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Clearing log files..."
    rm -f logs/*.log
    print_success "Log files cleared"
fi

print_success "All services stopped successfully!"
