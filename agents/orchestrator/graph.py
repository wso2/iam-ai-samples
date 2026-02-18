"""
LangGraph-based Orchestrator Workflow.
Implements a stateful graph for intelligent task routing and multi-agent coordination.
"""

from typing import TypedDict, List, Dict, Any, Annotated
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.auth.token_broker import get_token_broker

logger = logging.getLogger(__name__)


# ============================================================================
# State Schema
# ============================================================================

class OrchestratorState(TypedDict):
    """State for the orchestrator workflow."""
    # Input
    user_query: str
    access_token: str
    context_id: str
    
    # Discovered agents
    available_agents: List[Dict[str, Any]]
    
    # Task decomposition
    task_plan: List[Dict[str, Any]]  # [{agent_url, agent_name, task, step}]
    
    # Execution tracking
    current_task_index: int
    task_results: List[Dict[str, Any]]  # [{step, agent, result}]
    
    # Approval tracking - List of all approval decisions
    approval_decisions: List[Dict[str, str]]  # [{"task": "...", "status": "approved"|"denied", "reason": "..."}]
    
    # Messages for LLM conversation
    messages: Annotated[List, "Messages for LLM context"]
    
    # Final output
    final_response: str
    error: str | None


# ============================================================================
# Graph Nodes
# ============================================================================

async def discover_agents_node(state: OrchestratorState) -> OrchestratorState:
    """
    Node 1: Discover available agents via A2A Card Resolution.
    """
    logger.info("🔍 [LangGraph] Discovering agents...")
    
    # Import here to avoid circular dependencies
    from agents.orchestrator.agent import OrchestratorAgent
    
    # Create temporary orchestrator instance for discovery
    orchestrator = OrchestratorAgent()
    agents = await orchestrator.discover_agents()
    
    logger.info(f"✅ [LangGraph] Discovered {len(agents)} agents")
    
    return {
        **state,
        "available_agents": agents,
        "messages": state.get("messages", []) + [
            AIMessage(content=f"Discovered {len(agents)} agents: {', '.join(a['name'] for a in agents)}")
        ]
    }


async def plan_tasks_node(state: OrchestratorState) -> OrchestratorState:
    """
    Node 2: Use LLM to decompose user query into ordered tasks.
    """
    logger.info("📋 [LangGraph] Planning tasks with LLM...")
    
    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=settings.openai_api_key,
        temperature=0
    )
    
    # Build agent context for LLM
    agent_descriptions = "\n".join([
        f"- {a['name']} ({a['url']}): {a['description']}\n  Skills: {', '.join(a['skills'])}"
        for a in state["available_agents"]
    ])
    
    system_prompt = f"""You are an intelligent task planner for a multi-agent system.

Available Agents:
{agent_descriptions}

Your task: Break down the user's request into ordered steps that can be executed by these agents.
Return a JSON array of tasks in this exact format:
[
  {{"step": 1, "agent_name": "HR Agent", "agent_url": "http://localhost:8001", "task": "Create employee record for John"}},
  {{"step": 2, "agent_name": "IT Agent", "agent_url": "http://localhost:8002", "task": "Provision accounts for new employee"}}
]

CRITICAL RULES:
1. **SEPARATE APPROVALS FOR MIXED-RISK REQUESTS**: 
   - If a request contains BOTH high-risk and low-risk operations, create SEPARATE approval tasks for each
   - Example: "Give Bob high-level HR privileges AND normal IT access" should become:
     * Approval 1 (high-risk): "Approve high-level HR privileges for Bob"
     * HR task execution
     * Approval 2 (low-risk): "Approve normal IT access for Bob"  
     * IT task execution
   - This allows low-risk operations to proceed even if high-risk ones are denied
   
2. **APPROVAL BEFORE EXECUTION**: Each privileged operation should have its approval immediately before execution, not all approvals at the start

3. **CONSOLIDATE AGENT TASKS**: If multiple operations can be done by the SAME agent with SAME risk level, combine them into ONE task
   - Example: Instead of 3 separate IT tasks (VPN, GitHub, AWS), create 1 task: "Provision VPN, GitHub, and AWS access for Alice"
   - This reduces token exchanges and improves efficiency

4. Only use agents that are actually available
5. Tasks should be specific and actionable
6. Return ONLY the JSON array, no other text

Example for MIXED-RISK request:
Request: "Give Bob high-level HR privileges and normal IT access"
[
  {{"step": 1, "agent_name": "Approval Agent", "agent_url": "http://localhost:8003", "task": "Approve request to grant high-level HR privileges to Bob"}},
  {{"step": 2, "agent_name": "HR Agent", "agent_url": "http://localhost:8001", "task": "Grant high-level HR privileges to Bob"}},
  {{"step": 3, "agent_name": "Approval Agent", "agent_url": "http://localhost:8003", "task": "Approve request to grant normal IT access to Bob"}},
  {{"step": 4, "agent_name": "IT Agent", "agent_url": "http://localhost:8002", "task": "Grant normal IT privileges to Bob"}}
]

Example for SAME-RISK request (consolidate):
Request: "Give Alice VPN, GitHub, and AWS access"
[
  {{"step": 1, "agent_name": "Approval Agent", "agent_url": "http://localhost:8003", "task": "Approve request to provision IT access for Alice"}},
  {{"step": 2, "agent_name": "IT Agent", "agent_url": "http://localhost:8002", "task": "Provision VPN, GitHub, and AWS access for Alice"}}
]
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"User request: {state['user_query']}")
    ]
    
    response = await llm.ainvoke(messages)
    
    # Parse the response
    import json
    try:
        task_plan = json.loads(response.content.strip())
        logger.info(f"✅ [LangGraph] Created plan with {len(task_plan)} tasks")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse LLM response: {e}")
        task_plan = []
    
    return {
        **state,
        "task_plan": task_plan,
        "current_task_index": 0,
        "task_results": [],
        "messages": state.get("messages", []) + [
            AIMessage(content=f"Created execution plan with {len(task_plan)} steps")
        ]
    }


async def execute_task_node(state: OrchestratorState) -> OrchestratorState:
    """
    Node 3: Execute the current task by calling the appropriate agent.
    Skips tasks whose approval was denied.
    """
    task_idx = state["current_task_index"]
    task_plan = state["task_plan"]
    
    # Safety check: prevent infinite loop
    if task_idx >= len(task_plan):
        logger.warning(f"⚠️ [LangGraph] Task index {task_idx} >= plan length {len(task_plan)}, stopping")
        return state
    
    current_task = task_plan[task_idx]
    logger.info(f"🚀 [LangGraph] Executing task {task_idx + 1}/{len(task_plan)}: {current_task['task']}")
    
    # Check if this task's approval was denied
    approval_decisions = state.get("approval_decisions", [])
    current_step = current_task.get("step")
    
    # Find if there's a denied approval for this task
    denied_approval = None
    for approval in approval_decisions:
        if approval.get("linked_task_step") == current_step and approval["status"] == "denied":
            denied_approval = approval
            break
    
    if denied_approval:
        logger.warning(f"⚠️ [LangGraph] Skipping task {task_idx + 1} - approval was denied")
        logger.warning(f"   Reason: {denied_approval['reason'][:100]}")
        
        # Record skipped task
        task_result = {
            "step": current_task["step"],
            "agent": current_task["agent_name"],
            "task": current_task["task"],
            "result": f"⏭️ SKIPPED - Approval denied: {denied_approval['reason'][:100]}",
            "success": False,
            "skipped": True
        }
        
        task_results = state.get("task_results", [])
        task_results = task_results + [task_result]
        
        return {
            **state,
            "current_task_index": task_idx + 1,
            "task_results": task_results
        }
    
    # Import here to avoid circular dependencies
    from agents.orchestrator.agent import OrchestratorAgent
    
    # Get token broker for token exchange
    token_broker = get_token_broker()
    
    # Dynamically determine agent key from discovered agents
    agent_key = None
    target_agent = None
    
    for agent in state["available_agents"]:
        if agent["url"] == current_task["agent_url"]:
            target_agent = agent
            # Derive key from agent name (e.g., "HR Agent" -> "hr_agent")
            agent_key = agent["name"].lower().replace(" ", "_")
            break
    
    if not agent_key:
        # Fallback: derive from agent name in task
        agent_key = current_task["agent_name"].lower().replace(" ", "_")
    
    # Get scopes from config dynamically
    from src.config_loader import load_yaml_config
    config = load_yaml_config()
    agents_config = config.get("agents", {})
    
    # Find agent config by key or name
    agent_config = agents_config.get(agent_key)
    if agent_config:
        # Get scopes from config
        agent_scopes = agent_config.get("scopes", [])
        if not agent_scopes:
            # Fallback: derive from agent name
            scope_prefix = agent_key.replace("_agent", "")
            agent_scopes = [f"{scope_prefix}:read", f"{scope_prefix}:write"]
    else:
        # Fallback: derive scopes from agent name
        scope_prefix = agent_key.replace("_agent", "")
        agent_scopes = [f"{scope_prefix}:read", f"{scope_prefix}:write"]

    
    try:
        # Exchange token for this specific agent
        agent_token = await token_broker.exchange_token_for_agent(
            source_token=state["access_token"],
            agent_key=agent_key,
            target_audience=current_task["agent_name"].lower().replace(" ", "-"),
            target_scopes=agent_scopes  # agent_scopes is already a list
        )
        
        # Call the agent with pre-exchanged token (avoid duplicate exchange)
        orchestrator = OrchestratorAgent()
        agent_response = await orchestrator.call_agent(
            agent_url=current_task["agent_url"],
            query=current_task["task"],
            access_token=state["access_token"],
            pre_exchanged_token=agent_token  # Pass pre-exchanged token to skip duplicate exchange
        )
        
        # Extract result from A2A response
        if isinstance(agent_response, dict):
            if "error" in agent_response:
                result = agent_response["error"]
                success = False
            elif "result" in agent_response:
                # A2A JSON-RPC response
                result_data = agent_response.get("result", {})
                
                if isinstance(result_data, list):
                    # Result is a list - stringify it
                    result = str(result_data)
                    success = True
                elif isinstance(result_data, dict):
                    # Extract text from message parts
                    message = result_data.get("message", {})
                    parts = message.get("parts", [])
                    if parts and isinstance(parts, list):
                        result = parts[0].get("text", str(result_data))
                    else:
                        result = str(result_data)
                    success = True
                else:
                    result = str(result_data)
                    success = True
            else:
                result = str(agent_response)
                success = True
        else:
            result = str(agent_response)
            success = True
        
        logger.info(f"✅ [LangGraph] Task {task_idx + 1} completed successfully")
        
        task_result = {
            "step": current_task["step"],
            "agent": current_task["agent_name"],
            "task": current_task["task"],
            "result": result,
            "success": success
        }
        
        # Check if this was an approval task and track the decision
        approval_decisions = state.get("approval_decisions", [])
        if "approval" in current_task["agent_name"].lower():
            result_lower = str(result).lower()
            decision_status = None
            
            if "approved" in result_lower or "approval granted" in result_lower:
                decision_status = "approved"
                logger.info("✅ [LangGraph] Approval granted")
            elif "denied" in result_lower or "rejected" in result_lower or "failed" in result_lower or "error" in result_lower:
                # Treat errors/failures as denial
                decision_status = "denied"
                logger.warning(f"❌ [LangGraph] Approval denied or failed: {result[:100]}")
            
            if decision_status:
                # Link approval to the next task (assumes approval task is immediately before execution task)
                next_task_idx = task_idx + 1
                linked_task_step = None
                if next_task_idx < len(task_plan):
                    linked_task_step = task_plan[next_task_idx].get("step")
                
                approval_decisions = approval_decisions + [{
                    "task": current_task["task"],
                    "status": decision_status,
                    "reason": str(result),
                    "linked_task_step": linked_task_step  # Link approval to its execution task
                }]
        
    except Exception as e:
        logger.error(f"❌ [LangGraph] Task {task_idx + 1} failed: {e}")
        task_result = {
            "step": current_task["step"],
            "agent": current_task["agent_name"],
            "task": current_task["task"],
            "result": str(e),
            "success": False
        }
        approval_decisions = state.get("approval_decisions", [])
    
    return {
        **state,
        "current_task_index": task_idx + 1,
        "task_results": state["task_results"] + [task_result],
        "approval_decisions": approval_decisions,
        "messages": state.get("messages", []) + [
            AIMessage(content=f"Completed: {current_task['task']}")
        ]
    }


async def aggregate_results_node(state: OrchestratorState) -> OrchestratorState:
    """
    Node 4: Aggregate all task results into a final response.
    """
    logger.info("📊 [LangGraph] Aggregating results...")
    
    # Build final response
    results_summary = []
    for idx, task_result in enumerate(state["task_results"]):
        # Debug logging
        logger.debug(f"Task result {idx}: type={type(task_result)}, value={task_result}")
        
        # Safely access task_result - handle both dict and unexpected types
        if isinstance(task_result, dict):
            status = "✅" if task_result.get("success", False) else "❌"
            results_summary.append(
                f"{status} Step {task_result.get('step', idx+1)}: {task_result.get('agent', 'Unknown')} - {task_result.get('task', 'N/A')}\n"
                f"   Result: {task_result.get('result', 'No result')}"
            )
        else:
            # Handle unexpected type
            logger.error(f"❌ Unexpected task_result type: {type(task_result)}")
            results_summary.append(
                f"❌ Step {idx+1}: Error - Invalid result format: {str(task_result)}"
            )
    
    final_response = "\n\n".join(results_summary)
    
    logger.info("✅ [LangGraph] Workflow completed")
    
    return {
        **state,
        "final_response": final_response
    }


# ============================================================================
# Conditional Routing
# ============================================================================

def should_continue_execution(state: OrchestratorState) -> str:
    """
    Decides whether to continue executing tasks or move to aggregation.
    With partial approval support: workflow continues even if some approvals are denied.
    Individual denied tasks are skipped in execute_task_node.
    """
    # Note: We removed the "stop on ANY denial" logic to support partial approvals
    # Individual tasks with denied approvals are now skipped in execute_task_node
    
    # Continue if there are more tasks
    current_idx = state["current_task_index"]
    total_tasks = len(state["task_plan"])
    
    logger.info(f"🔍 [LangGraph] Routing decision: index={current_idx}, total={total_tasks}")
    
    if current_idx < total_tasks:
        logger.info(f"   → Continuing to execute_task (task {current_idx + 1})")
        return "execute_task"
    else:
        logger.info(f"   → Moving to aggregate (all tasks complete)")
        return "aggregate"


# ============================================================================
# Graph Construction
# ============================================================================

def create_orchestrator_graph() -> StateGraph:
    """
    Creates the LangGraph workflow for the orchestrator.
    
    Graph Flow:
    START → discover_agents → plan_tasks → execute_task → (loop or aggregate) → END
    """
    workflow = StateGraph(OrchestratorState)
    
    # Add nodes
    workflow.add_node("discover_agents", discover_agents_node)
    workflow.add_node("plan_tasks", plan_tasks_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("aggregate", aggregate_results_node)
    
    # Define edges
    workflow.set_entry_point("discover_agents")
    workflow.add_edge("discover_agents", "plan_tasks")
    workflow.add_edge("plan_tasks", "execute_task")
    
    # Conditional routing after task execution
    workflow.add_conditional_edges(
        "execute_task",
        should_continue_execution,
        {
            "execute_task": "execute_task",  # Loop back for next task
            "aggregate": "aggregate"          # Move to final aggregation
        }
    )
    
    workflow.add_edge("aggregate", END)
    
    return workflow.compile()


# ============================================================================
# Main Execution Function
# ============================================================================

async def run_orchestrator_workflow(
    user_query: str,
    access_token: str,
    context_id: str = "default"
) -> Dict[str, Any]:
    """
    Execute the orchestrator workflow using LangGraph.
    
    Args:
        user_query: The user's request
        access_token: OAuth2 access token for the user
        context_id: Session context identifier
    
    Returns:
        Final state with aggregated results
    """
    logger.info(f"🚀 [LangGraph] Starting orchestrator workflow for: {user_query}")
    
    # Create the graph
    graph = create_orchestrator_graph()
    
    # Initialize state
    initial_state: OrchestratorState = {
        "user_query": user_query,
        "access_token": access_token,
        "context_id": context_id,
        "available_agents": [],
        "task_plan": [],
        "current_task_index": 0,
        "task_results": [],
        "approval_decisions": [],
        "messages": [HumanMessage(content=user_query)],
        "final_response": "",
        "error": None
    }
    
    # Run the graph
    try:
        final_state = await graph.ainvoke(initial_state)
        logger.info("✅ [LangGraph] Workflow completed successfully")
        return final_state
    except Exception as e:
        logger.error(f"❌ [LangGraph] Workflow failed: {e}")
        return {
            **initial_state,
            "error": str(e),
            "final_response": f"Workflow failed: {e}"
        }
