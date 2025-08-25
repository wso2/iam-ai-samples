#!/bin/bash

# Start Services Script - Non-Docker Alternative to docker-compose
# This script starts all services locally without Docker

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        return 1
    else
        return 0
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    local pid=$(lsof -ti:$port)
    if [ ! -z "$pid" ]; then
        print_warning "Killing process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null || true
        sleep 2
    fi
}

print_status "Starting Hotel Booking Application Services"
echo "=========================================="

# Check prerequisites
print_status "Checking prerequisites..."

if ! command_exists python3; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

if ! command_exists pip3; then
    print_error "pip3 is required but not installed"
    exit 1
fi

if ! command_exists node; then
    print_error "Node.js is required but not installed"
    exit 1
fi

if ! command_exists npm; then
    print_error "npm is required but not installed"
    exit 1
fi

if ! command_exists git; then
    print_error "git is required but not installed"
    exit 1
fi

if ! command_exists poetry; then
    print_status "Poetry will be installed as part of the setup process"
fi

# Check and kill processes on required ports
print_status "Checking ports..."
if ! check_port 8001; then
    print_warning "Port 8001 is in use"
    kill_port 8001
fi

if ! check_port 8000; then
    print_warning "Port 8000 is in use"
    kill_port 8000
fi

if ! check_port 3000; then
    print_warning "Port 3000 is in use"
    kill_port 3000
fi

if ! check_port 8002; then
    print_warning "Port 8002 is in use"
    kill_port 8002
fi

# Create log directory
LOG_DIR="./logs"
mkdir -p $LOG_DIR

# Install and start Backend service
print_status "Setting up Backend service..."
cd backend
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment for Backend..."
    python3 -m venv venv
fi

print_status "Activating virtual environment and installing dependencies..."
source venv/bin/activate

# Install additional dependencies found in Dockerfile
print_status "Upgrading pip..."
pip install --upgrade pip

# Install remaining requirements (excluding asgardeo packages)
print_status "Installing Python dependencies..."
pip install -r requirements.txt

print_status "Starting Backend service on port 8001..."
export PYTHONPATH=$(pwd)
nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 > ../logs/backend.log 2>&1 &
API_PID=$!
echo $API_PID > ../logs/backend.pid
deactivate
cd ..

# Install and start Assistant Agent service
print_status "Setting up Assistant Agent service..."
cd assistant-agent
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment for Assistant Agent..."
    python3 -m venv venv
fi

print_status "Activating virtual environment and installing dependencies..."
source venv/bin/activate

# Install additional dependencies found in Dockerfile
print_status "Upgrading pip..."
pip install --upgrade pip

# Install remaining requirements
pip install -r requirements.txt

print_status "Starting Assistant Agent service on port 8000..."
export PYTHONPATH=$(pwd)
nohup uvicorn app.service:app --reload --host 0.0.0.0 --port 8000 > ../logs/assistant_agent.log 2>&1 &
AGENT_PID=$!
echo $AGENT_PID > ../logs/assistant_agent.pid
deactivate
cd ..

# Install and start Staff Management Agent service
print_status "Setting up Staff Management Agent service..."
cd staff-management-agent
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment for Staff Management Agent..."
    python3 -m venv venv
fi

print_status "Activating virtual environment and installing dependencies..."
source venv/bin/activate

# Install additional dependencies found in Dockerfile
print_status "Upgrading pip..."
pip install --upgrade pip

# Install remaining requirements
pip install -r requirements.txt

print_status "Starting Staff Management Agent service on port 8002..."
export PYTHONPATH=$(pwd)
nohup uvicorn app.service:app --reload --host 0.0.0.0 --port 8002 > ../logs/staff_management_agent.log 2>&1 &
AGENT_PID=$!
echo $AGENT_PID > ../logs/staff_management_agent.pid
deactivate
cd ..

# Install and start Frontend service
print_status "Setting up Frontend service..."
cd frontend

if [ ! -d "node_modules" ]; then
    print_status "Installing npm dependencies..."
    npm install
fi

print_status "Starting Frontend service on port 3000..."
export REACT_APP_API_URL=http://localhost:8001
nohup npm start > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../logs/frontend.pid
cd ..

# Wait for services to start
print_status "Waiting for services to start..."
sleep 5

# Check if services are running
print_status "Checking service status..."

if check_port 8001; then
    print_error "API service failed to start on port 8001"
    print_error "Check logs: tail -f logs/api.log"
else
    print_success "API service started on http://localhost:8001"
fi

if check_port 8000; then
    print_error "Assistant Agent service failed to start on port 8000"
    print_error "Check logs: tail -f logs/assistant_agent.log"
else
    print_success "Assistant Agent service started on http://localhost:8000"
fi

if check_port 8002; then
    print_error "Staff Management Agent service failed to start on port 8002"
    print_error "Check logs: tail -f logs/staff_management_agent.log"
else
    print_success "Staff Management Agent service started on http://localhost:8002"
fi

if check_port 3000; then
    print_error "Frontend service failed to start on port 3000"
    print_error "Check logs: tail -f logs/frontend.log"
else
    print_success "Frontend service started on http://localhost:3000"
fi

echo ""
print_success "All services started successfully!"
echo "=========================================="
echo "Access your application:"
echo "  Frontend: http://localhost:3000"
echo "  API:      http://localhost:8001"
echo "  Assistant Agent:    http://localhost:8000"
echo "  Staff Management Agent: http://localhost:8002"
echo ""
echo "To stop all services, run: ./stop-services.sh"
echo "To view logs: tail -f logs/[service].log"
echo ""
echo "Service PIDs saved in logs/ directory"
