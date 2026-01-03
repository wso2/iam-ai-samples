# Hotel Booking Application Setup Guide

This guide provides instructions for setting up and running the Hotel Booking Application using either Docker or native installation scripts.

## Architecture

The application consists of four main services:
- **Backend** (Port 8001): FastAPI service for hotel booking API
- **Assistant Agent** (Port 8000): Guest-facing AI agent for room search and booking
- **Staff Management Agent** (Port 8002): Background agent for staff optimization
- **Frontend** (Port 3000): React application for user interface

## Prerequisites

### For Docker Setup
- Docker
- Docker Compose

### For Native Setup
- Python 3.11+
- Node.js 16+
- npm
- git
- pip3

## Option 1: Docker Setup (Recommended)

### Quick Start
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Individual Service Management
```bash
# Start specific service
docker-compose up backend

# Rebuild and start
docker-compose up --build

# View service logs
docker-compose logs backend
docker-compose logs assistant-agent
docker-compose logs staff-management-agent
docker-compose logs frontend
```

## Option 2: Native Setup (Without Docker)

### Quick Start
```bash
# Make scripts executable (first time only)
chmod +x start-services.sh stop-services.sh

# Start all services
./start-services.sh

# Stop all services
./stop-services.sh
```

### What the Script Does

The `start-services.sh` script will:

1. **Check Prerequisites**: Verifies Python 3, Node.js, npm, and git are installed
2. **Port Management**: Kills any existing processes on ports 3000, 8000, 8001
3. **Backend Service Setup**:
   - Creates Python virtual environment in `backend/venv`
   - Installs uvicorn and poetry
   - Installs Python dependencies from `requirements.txt`
   - Starts FastAPI server on port 8001
4. **AI Agents Service Setup**:
   - Creates Python virtual environment in `ai-agents/venv`
   - Installs uvicorn and poetry
   - Clones and builds Asgardeo packages from GitHub
   - Installs Python dependencies from `requirements.txt`
   - Starts FastAPI server on port 8000
5. **Frontend Setup**:
   - Installs npm dependencies
   - Starts React development server on port 3000

### Manual Service Management

#### Backend Service
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install 'uvicorn[standard]' poetry
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

#### Assistant Agent Service
```bash
cd assistant-agent
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
uvicorn app.service:app --reload --host 0.0.0.0 --port 8000
```

#### Staff Management Agent Service
```bash
cd staff-management-agent
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
uvicorn app.service:app --reload --host 0.0.0.0 --port 8002
```

#### Frontend
```bash
cd frontend
npm install
npm start
```

## Accessing the Application

Once services are running, access:
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8001
- **AI Agents Service**: http://localhost:8000

## Logs and Monitoring

### Docker
```bash
# View all logs
docker-compose logs

# Follow logs for specific service
docker-compose logs -f backend
docker-compose logs -f assistant-agent
docker-compose logs -f staff-management-agent
docker-compose logs -f frontend

# View container status
docker-compose ps
```

### Native Script
```bash
# View logs (created by start-services.sh)
tail -f logs/backend.log
tail -f logs/assistant_agent.log
tail -f logs/staff_management_agent.log
tail -f logs/frontend.log

# View all logs
tail -f logs/*.log

# Check running processes
ps aux | grep uvicorn
ps aux | grep node
```
