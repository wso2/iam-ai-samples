@echo off
REM MCP Inspector Launcher for IT MCP Server
REM Step 1: Start MCP server in SSE mode
REM Step 2: Open Inspector UI in browser manually

echo ============================================================
echo  MCP Inspector Launcher - IT MCP Server
echo ============================================================
echo.

REM Add Python Scripts to PATH
set "PYTHON_SCRIPTS=%APPDATA%\Python\Python314\Scripts"
set "PATH=%PYTHON_SCRIPTS%;C:\Python314\Scripts;%PATH%"

REM Step 1: Start MCP server in SSE mode in a new window
echo [1/2] Starting IT MCP Server in SSE mode on port 8010...
start "IT MCP Server (SSE)" cmd /k "cd /d "%~dp0" && python src\mcp\it_mcp_server.py --transport sse --port 8010"

REM Wait for server to start
echo Waiting for MCP server to start...
timeout /t 4 /nobreak >nul

REM Step 2: Open Inspector UI (without passing server URL - configure in UI)
echo [2/2] Opening MCP Inspector UI...
echo.
echo ============================================================
echo  IMPORTANT: When Inspector opens in browser:
echo  1. Change Transport to "SSE"  
echo  2. Set URL to: http://localhost:8010/sse
echo  3. Click "Connect"
echo ============================================================
echo.

start "" "http://localhost:6274"
npx -y @modelcontextprotocol/inspector

pause
