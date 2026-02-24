"""
Finance & Payroll Agent - A2A Agent using CrewAI.

Uses CrewAI to orchestrate payroll registration and expense account setup
via the Payroll API (mounted at /api/payroll/*).

Capabilities:
- register_payroll     : Set up employee salary, grade, pay frequency
- setup_expense_account: Create expense account with spending limits
- get_payroll_summary  : Look up an existing payroll record
"""

import os
import sys
import logging
import asyncio
from typing import Dict, Any, AsyncIterable

import httpx
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

current_dir  = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)
load_dotenv(os.path.join(project_root, '.env'))

from src.config import get_settings
from src.config_loader import load_yaml_config

logger = logging.getLogger(__name__)

PAYROLL_API_BASE = "http://localhost:8004/api/payroll"


class PayrollAgent:
    """
    Finance & Payroll Agent.
    Uses CrewAI with two tools that call the Payroll REST API.
    Required scopes: approval:read, approval:write
    """

    REQUIRED_SCOPES = ["approval:read", "approval:write"]

    def __init__(self, config: dict = None):
        self.config   = config or {}
        self.settings = get_settings()
        app_config    = load_yaml_config()
        agent_cfg     = app_config.get("agents", {}).get("payroll_agent", {})
        self.required_scopes = agent_cfg.get("required_scopes", self.REQUIRED_SCOPES)
        self.openai_api_key  = self.settings.openai_api_key
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=self.openai_api_key,
            temperature=0.1
        )
        logger.info("PayrollAgent initialized (CrewAI mode)")
        logger.info(f"  Required scopes: {self.required_scopes}")
        logger.info(f"  Payroll API: {PAYROLL_API_BASE}")

    async def _call_api(self, method: str, path: str, token: str, json_data: dict = None) -> Dict[str, Any]:
        """Authenticated call to the Payroll API."""
        url = f"{PAYROLL_API_BASE}{path}"
        logger.info(f"[PAYROLL_AGENT] API call: {method} {url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_data,
            )
            if response.status_code >= 400:
                return {"success": False, "error": f"API {response.status_code}: {response.text}"}
            result = response.json()
            if isinstance(result, dict):
                result["success"] = True
            else:
                result = {"success": True, "data": result}
            return result

    async def process_request(self, query: str, token: str = None) -> str:
        """Process a payroll/finance request using CrewAI."""
        if not token:
            return "❌ No token provided. Authentication required."

        # ── Define CrewAI tools (closures capture `self` and `token`) ────────

        @tool("Register Payroll")
        def register_payroll_tool(
            employee_id: str,
            employee_name: str,
            role: str,
            pay_frequency: str = "monthly",
        ) -> str:
            """
            Register a new employee in the payroll system.
            Sets up salary grade (auto-inferred from role), annual salary, and pay schedule.
            Args:
                employee_id: The employee's ID, e.g. EMP-001
                employee_name: The employee's full name
                role: The employee's job title/role, e.g. 'Senior IT Manager'
                pay_frequency: 'monthly' or 'biweekly'
            """
            payload = {
                "employee_id":   employee_id,
                "employee_name": employee_name,
                "role":          role,
                "pay_frequency": pay_frequency,
            }
            logger.info(f"[PAYROLL_AGENT] Registering payroll for {employee_id}")
            result = asyncio.run(self._call_api("POST", "/payroll", token, payload))
            if result.get("success"):
                grade  = result.get("salary_grade", "N/A")
                salary = result.get("annual_salary", 0)
                freq   = result.get("pay_frequency", pay_frequency)
                pid    = result.get("payroll_id", "N/A")
                return (
                    f"✅ Payroll registered!\n"
                    f"   Payroll ID    : {pid}\n"
                    f"   Employee      : {employee_name} ({employee_id})\n"
                    f"   Grade         : {grade}\n"
                    f"   Annual Salary : ${salary:,.0f} {result.get('currency','USD')}\n"
                    f"   Pay Schedule  : {freq.title()}"
                )
            return f"❌ Payroll registration failed: {result.get('error')}"

        @tool("Setup Expense Account")
        def setup_expense_account_tool(
            employee_id: str,
            monthly_limit: float = 1000.0,
        ) -> str:
            """
            Create an expense account for an employee with a monthly spending limit.
            Default categories: travel, meals, equipment, training, misc.
            Args:
                employee_id: The employee's ID, e.g. EMP-001
                monthly_limit: Monthly spending limit in USD (default: 1000)
            """
            payload = {
                "employee_id":   employee_id,
                "monthly_limit": monthly_limit,
            }
            logger.info(f"[PAYROLL_AGENT] Creating expense account for {employee_id}")
            result = asyncio.run(self._call_api("POST", "/expense-accounts", token, payload))
            if result.get("success"):
                aid  = result.get("account_id", "N/A")
                cats = ", ".join(result.get("categories", []))
                lim  = result.get("monthly_limit", monthly_limit)
                return (
                    f"✅ Expense account created!\n"
                    f"   Account ID    : {aid}\n"
                    f"   Monthly Limit : ${lim:,.0f} {result.get('currency','USD')}\n"
                    f"   Categories    : {cats}"
                )
            return f"❌ Expense account creation failed: {result.get('error')}"

        @tool("Get Payroll Summary")
        def get_payroll_summary_tool(employee_id: str) -> str:
            """
            Retrieve the current payroll record for an employee.
            Args:
                employee_id: The employee's ID, e.g. EMP-001
            """
            logger.info(f"[PAYROLL_AGENT] Getting payroll for {employee_id}")
            result = asyncio.run(self._call_api("GET", f"/payroll/{employee_id}", token))
            if result.get("success"):
                return (
                    f"Payroll record for {employee_id}:\n"
                    f"  Grade: {result.get('salary_grade')}, "
                    f"  Salary: ${result.get('annual_salary'):,.0f}, "
                    f"  Schedule: {result.get('pay_frequency')}"
                )
            return f"No payroll record found for {employee_id}: {result.get('error')}"

        # ── CrewAI Agent ─────────────────────────────────────────────────────

        payroll_manager = Agent(
            role="Senior Finance & Payroll Manager",
            goal="Set up complete payroll and expense accounts for new employees quickly and accurately.",
            backstory=(
                "You are an experienced payroll specialist. When onboarding a new employee, "
                "you ALWAYS register them in payroll first (using their employee ID, name, and role), "
                "then immediately set up their expense account. "
                "Extract the employee ID (format EMP-XXX) from the context. "
                "Extract the monthly expense limit if mentioned (default $1000). "
                "Always call BOTH tools for a new employee."
            ),
            tools=[register_payroll_tool, setup_expense_account_tool, get_payroll_summary_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

        payroll_task = Task(
            description=(
                f"Process the following payroll onboarding request:\n\n'{query}'\n\n"
                f"IMPORTANT: Extract the Employee ID (EMP-XXX format) from the context above. "
                f"Register payroll AND set up an expense account for the employee. "
                f"If a monthly expense limit is mentioned, use it; otherwise default to $1000. "
                f"Provide a clear summary of both actions."
            ),
            expected_output=(
                "A formatted summary of the payroll registration and expense account setup, "
                "including payroll ID, salary grade, annual salary, and expense account details. "
                "Use markdown checkmarks (✅)."
            ),
            agent=payroll_manager,
        )

        payroll_crew = Crew(
            agents=[payroll_manager],
            tasks=[payroll_task],
            process=Process.sequential,
            verbose=True,
        )

        try:
            logger.info("[PAYROLL_AGENT] Kicking off CrewAI process...")
            result = await asyncio.to_thread(payroll_crew.kickoff)
            return str(result)
        except Exception as e:
            logger.error(f"[PAYROLL_AGENT] Crew execution failed: {e}", exc_info=True)
            return f"❌ Payroll agent workflow failed: {str(e)}"

    async def stream(self, query: str, token: str = None) -> AsyncIterable[Dict[str, Any]]:
        """Stream response — A2A pattern."""
        response = await self.process_request(query, token)
        yield {"content": response}
