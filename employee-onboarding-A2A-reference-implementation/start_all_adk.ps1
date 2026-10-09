$host.ui.RawUI.WindowTitle = "Launcher"
$env:PYTHONIOENCODING="utf-8"

Write-Host "Starting A2A Reference Implementation (ADK Version)..." -ForegroundColor Cyan

# 1. Start IT MCP Server (if not already running - usually port 8020)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'IT MCP Server (8020)'; .\.venv\Scripts\python src/mcp/it_mcp_server.py --transport sse --port 8020 }"
Start-Sleep -Seconds 2

# 2. Start HR Agent (8001)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'HR Agent (8001)'; .\.venv\Scripts\python -m agents.hr_agent }"

# 3. Start IT Agent (8002)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'IT Agent (8002)'; .\.venv\Scripts\python -m agents.it_agent }"

# 4. Start Approval Agent (8003)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'Approval Agent (8003)'; .\.venv\Scripts\python -m agents.approval_agent }"

# 5. Start Finance & Payroll Agent (8004)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'Finance & Payroll Agent (8004)'; .\.\.venv\Scripts\python -m agents.payroll_agent }"

# 6. Start NEW Booking Agent ADK (8005)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'Booking Agent ADK (8005)'; .\.\.venv\Scripts\python -m agents.booking_agent_adk }"

# 7. Start Orchestrator (8000) - start after agents are ready
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'Orchestrator (8000)'; .\.\.venv\Scripts\python -m agents.orchestrator }"

# 8. Start Visualizer Server (8200)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& { $host.ui.RawUI.WindowTitle = 'Visualizer Server (8200)'; .\.venv\Scripts\python visualizer_server.py }"

Write-Host "All agents started." -ForegroundColor Green
Write-Host "Orchestrator: http://localhost:8000"
Write-Host "Booking Agent (ADK): http://localhost:8005"
Write-Host "Visualizer: http://localhost:8200"
