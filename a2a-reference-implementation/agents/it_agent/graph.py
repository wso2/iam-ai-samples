"""
LangGraph-based IT Agent Workflow.
Implements a stateful graph for IT provisioning via the MCP Server.

Graph Flow:
  START → call_mcp → format_results → END
"""

import json
import logging
from typing import TypedDict, Any, Dict, List

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# ============================================================================
# State Schema
# ============================================================================

class ITAgentState(TypedDict):
    """State carried through the IT Agent LangGraph workflow."""
    # Inputs
    query: str
    token: str

    # MCP raw result
    mcp_result: Dict[str, Any]

    # Final formatted output returned to the Orchestrator
    final_response: str
    error: str | None


# ============================================================================
# Graph Nodes
# ============================================================================

async def call_mcp_node(state: ITAgentState) -> ITAgentState:
    """
    Node 1: Forward the raw request to the IT MCP Server's
    handle_it_request tool via SSE transport and capture the result.
    """
    logger.info("🔧 [LangGraph/IT] Calling MCP handle_it_request...")

    from agents.it_agent.agent import ITAgent

    agent = ITAgent()
    mcp_result = await agent._call_mcp_tool("handle_it_request", {
        "request": state["query"],
        "token": state["token"],
    })

    logger.info(f"✅ [LangGraph/IT] MCP returned success={mcp_result.get('success')}")

    return {
        **state,
        "mcp_result": mcp_result,
    }


async def format_results_node(state: ITAgentState) -> ITAgentState:
    """
    Node 2: Transform the raw MCP result dict into a human-readable string
    (same formatting logic as the original process_request).
    """
    logger.info("📊 [LangGraph/IT] Formatting MCP results...")

    result = state["mcp_result"]

    if not result.get("success"):
        errors = []
        for r in result.get("results", []):
            if not r.get("success") and "error" in r:
                errors.append(r["error"])
        err_msg = "; ".join(errors) if errors else result.get("error", "Unknown error")
        return {
            **state,
            "final_response": f"[X] IT provisioning failed: {err_msg}",
            "error": err_msg,
        }

    results_array = result.get("results", [])
    if not results_array:
        return {
            **state,
            "final_response": "[X] IT provisioning failed: No results returned from MCP server",
            "error": "No results",
        }

    formatted_responses = []
    for action_result in results_array:
        routing = action_result.get("_routing", {})
        action = routing.get("action", "unknown")
        scope_info = routing.get("scope_narrowing", "N/A")
        classified_by = routing.get("routed_by", "N/A")
        employee_id = action_result.get("employee_id", "N/A")

        if action == "provision_vpn":
            res_text = (
                f"[OK] VPN access provisioned via MCP → IT API!\n"
                f"- Provision ID: {action_result.get('provision_id', 'N/A')}\n"
                f"- Employee: {action_result.get('employee_id', employee_id)}\n"
                f"- VPN Server: {action_result.get('details', {}).get('vpn_server', 'vpn.nebulasoft.internal')}\n"
                f"- Status: {action_result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )
        elif action == "provision_github":
            res_text = (
                f"[OK] GitHub Enterprise access provisioned via MCP → IT API!\n"
                f"- Provision ID: {action_result.get('provision_id', 'N/A')}\n"
                f"- Employee: {action_result.get('employee_id', employee_id)}\n"
                f"- GitHub User: {action_result.get('details', {}).get('github_username', 'N/A')}\n"
                f"- Repos: {action_result.get('details', {}).get('repositories', [])}\n"
                f"- Status: {action_result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )
        elif action == "provision_aws":
            res_text = (
                f"[OK] AWS environment provisioned via MCP → IT API!\n"
                f"- Provision ID: {action_result.get('provision_id', 'N/A')}\n"
                f"- Employee: {action_result.get('employee_id', employee_id)}\n"
                f"- IAM User: {action_result.get('details', {}).get('iam_user', 'N/A')}\n"
                f"- Account: {action_result.get('details', {}).get('account', 'N/A')}\n"
                f"- Status: {action_result.get('status', 'active')}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}"
            )
        elif action == "list_provisions":
            provisions = action_result.get("data", [])
            if not provisions:
                res_text = f"📋 No provisions found for {employee_id}."
            else:
                lines = [f"📋 Provisions for {employee_id} ({len(provisions)} total):"]
                for p in provisions:
                    lines.append(f"  - {p.get('provision_id')}: {p.get('service')} ({p.get('status')})")
                lines.append(f"  Routed by: {classified_by}")
                lines.append(f"  Token scope narrowed: {scope_info}")
                res_text = "\n".join(lines)
        else:
            res_text = (
                f"[OK] IT request processed via MCP → IT API!\n"
                f"- Action: {action}\n"
                f"- Routed by: {classified_by}\n"
                f"- Token scope narrowed: {scope_info}\n"
                f"- Result: {json.dumps(action_result, indent=2)}"
            )

        formatted_responses.append(res_text)

    return {
        **state,
        "final_response": "\n\n".join(formatted_responses),
        "error": None,
    }


# ============================================================================
# Graph Construction
# ============================================================================

def create_it_agent_graph() -> StateGraph:
    """
    Build and compile the IT Agent LangGraph workflow.

    Graph:  START → call_mcp → format_results → END
    """
    workflow = StateGraph(ITAgentState)

    workflow.add_node("call_mcp", call_mcp_node)
    workflow.add_node("format_results", format_results_node)

    workflow.set_entry_point("call_mcp")
    workflow.add_edge("call_mcp", "format_results")
    workflow.add_edge("format_results", END)

    return workflow.compile()


# ============================================================================
# Main Execution Function
# ============================================================================

async def run_it_agent_workflow(query: str, token: str) -> str:
    """
    Execute the IT Agent LangGraph workflow and return the formatted result string.

    Args:
        query: Natural language IT provisioning request
        token: Scoped OAuth2 bearer token (it:read + it:write)

    Returns:
        Human-readable result string to be returned via A2A
    """
    logger.info(f"🚀 [LangGraph/IT] Starting IT Agent workflow for: {query[:80]}...")

    graph = create_it_agent_graph()

    initial_state: ITAgentState = {
        "query": query,
        "token": token,
        "mcp_result": {},
        "final_response": "",
        "error": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
        logger.info("✅ [LangGraph/IT] Workflow completed")
        return final_state["final_response"]
    except Exception as e:
        logger.error(f"❌ [LangGraph/IT] Workflow failed: {e}", exc_info=True)
        return f"[X] IT Agent workflow failed: {str(e)}"
