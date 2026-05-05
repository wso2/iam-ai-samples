import os
import asyncio
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
import operator
from datetime import datetime
import httpx
import secrets
import hashlib
import base64
import webbrowser
from urllib.parse import urlencode, parse_qs
from aiohttp import web
import threading

# MCP Integration imports
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

from dotenv import load_dotenv
load_dotenv()

# Initialize OpenAI LLM
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY")
)

# Simple in-memory conversation storage
conversation_memory = {}

class ChatbotState(TypedDict):
    messages: Annotated[list, operator.add]
    user_intent: str
    extracted_info: dict
    needs_human: bool
    conversation_history: list
    mcp_tools: list
    mcp_results: dict
    session_id: str

# MCP Server Configuration
MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

# Asgardeo OAuth2 Configuration - FIXED ENDPOINTS
AUTH_ISSUER = os.getenv("AUTH_ISSUER", "https://api.asgardeo.io/t/pasansanjiiwa")
CLIENT_ID = os.getenv("CLIENT_ID", "")
REDIRECT_URI = "http://localhost:8080/callback"

# Correct endpoint construction
AUTHORIZATION_ENDPOINT = f"{AUTH_ISSUER}/oauth2/authorize"
TOKEN_ENDPOINT = f"{AUTH_ISSUER}/oauth2/token"

# auth_code_future = asyncio.Future()

KNOWLEDGE_BASE = """
=== PAWSOME PET CARE CENTER ===

SERVICES & PRICING:
1. Grooming:
   - Small pets (under 25 lbs): $45
   - Medium pets (25-50 lbs): $65
   - Large pets (50-80 lbs): $85
   - Extra-large pets (80+ lbs): $110
   - Duration: 1.5-3 hours
   - Includes: Bath, haircut, nail trimming, ear cleaning, teeth brushing

2. Boarding (per night):
   - Small: $35/night
   - Medium: $45/night
   - Large: $55/night
   - Extra-large: $65/night
   - 24/7 supervision, comfortable accommodations, playtime, meals included

3. Daycare:
   - Full day (7am-7pm): $30
   - Half day: $20
   - Includes: Socialization, supervised playtime, snacks

4. Training:
   - Single session (1 hour): $75
   - 5-session package: $350
   - 10-session package: $650
   - Services: Obedience training, behavior modification, puppy training

5. Veterinary Services:
   - General checkup: $65
   - Vaccinations: $25 each
   - Dental cleaning: $150
   - Minor treatments available

REQUIREMENTS:
- All pets must be up-to-date on rabies, distemper, and bordetella vaccines
- Puppies/kittens must be at least 4 months old for daycare and boarding
- Flea and tick prevention required
- Temperament evaluation required for group activities

HOURS:
- Monday-Friday: 7:00 AM - 7:00 PM
- Saturday: 8:00 AM - 6:00 PM
- Sunday: 9:00 AM - 5:00 PM

CONTACT:
- Phone: (555) 123-4567
- Email: info@pawsomepetcare.com
- Address: 123 Pet Care Lane, Anytown, USA
- Website: www.pawsomepetcare.com

POLICIES:
- Cancellation: 24-hour notice required
- Payment: Cash, credit cards, pet insurance accepted
- Emergency: 24/7 emergency line available for boarding guests
"""

def generate_pkce():
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('ascii').rstrip('=')
    return code_verifier, code_challenge

async def start_callback_server(auth_future):
    """Starts a temporary local server to catch the OAuth callback."""
    
    async def callback_handler(request):
        query = request.rel_url.query
        if 'code' in query:
            # Check if future is already done to avoid errors
            if not auth_future.done():
                auth_future.set_result(query['code'])
            return web.Response(text="Authentication successful! You can close this window and return to the terminal.")
        return web.Response(text="No code found in callback.", status=400)
    
    app = web.Application()
    app.router.add_get('/callback', callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    return runner

async def authenticate_with_asgardeo():
    """Performs the full OAuth2 Authorization Code flow."""
    print("\n🔐 Initiating Asgardeo Authentication...")
    
    # 1. Create the Future INSIDE the async function (Event loop is running now)
    auth_code_future = asyncio.Future()
    
    code_verifier, code_challenge = generate_pkce()
    
    # 2. Start local server, passing the future to it
    runner = await start_callback_server(auth_code_future)
    
    # 3. Construct Auth URL
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile internal_login",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    auth_url = f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"
    
    # 4. Open Browser
    print(f"👉 Opening browser: {auth_url}")
    webbrowser.open(auth_url)
    
    # 5. Wait for code
    try:
        print("⏳ Waiting for callback...")
        # Wait for the future to be set by the web server handler
        code = await asyncio.wait_for(auth_code_future, timeout=120)
    except asyncio.TimeoutError:
        raise Exception("Authentication timed out.")
    finally:
        await runner.cleanup()
    
    # 6. Exchange code for token
    print("🔄 Exchanging code for token...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "code_verifier": code_verifier
            }
        )
        response.raise_for_status()
        token_data = response.json()
        print("✅ Authentication successful!")
        return token_data["access_token"]

def classify_node(state: ChatbotState):
    """Node: Classify user intent"""
    last_message = state["messages"][-1].content
    
    classification_prompt = ChatPromptTemplate.from_messages([
        ("system", """Classify the user's message into ONE category:
        - greeting
        - services
        - pricing
        - mcp_action (booking, cancellation, vaccination info, pet names)
        - general
        
        Respond ONLY with the category name."""),
        ("user", "{message}")
    ])
    
    result = (classification_prompt | llm).invoke({"message": last_message})
    intent = result.content.strip().lower()
    print(f"🎯 Node Classified: {intent}")
    return {"user_intent": intent}

def extract_node(state: ChatbotState):
    """Node: Extract entities"""
    last_message = state["messages"][-1].content
    
    extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", """Extract JSON info (pet_name, pet_type, date, service_interest, etc).
        Return JSON only. If nothing found, return {{}}."""),
        ("user", "{message}")
    ])
    
    # Simplified for brevity - add your regex cleaning logic here if needed
    result = (extraction_prompt | llm).invoke({"message": last_message})
    try:
        import json
        # Basic cleanup to ensure JSON
        content = result.content.replace('```json', '').replace('```', '').strip()
        extracted = json.loads(content)
    except:
        extracted = {}
        
    print(f"📋 Node Extracted: {extracted}")
    return {"extracted_info": extracted}

def greeting_node(state: ChatbotState):
    """Node: Handle Greetings"""
    msg = "🐾 Welcome to Pawsome Pet Care! I can help with services, booking, and vet info. How can I help?"
    return {"messages": [AIMessage(content=msg)]}

def service_node(state: ChatbotState):
    """Node: Handle Services"""
    interest = state["extracted_info"].get("service_interest", "general services")
    # Include conversation context
    context_messages = state["messages"][:-1]  # All messages except current
    context_str = "\n".join([f"{m.type}: {m.content}" for m in context_messages[-5:]])
    prompt = f"Previous conversation:\n{context_str}\n\nUser is interested in {interest}. Summarize available services from: {KNOWLEDGE_BASE}"
    response = llm.invoke(prompt)
    return {"messages": [response]}

def pricing_node(state: ChatbotState):
    """Node: Handle Pricing"""
    context_messages = state["messages"][:-1]
    context_str = "\n".join([f"{m.type}: {m.content}" for m in context_messages[-5:]])
    prompt = f"Previous conversation:\n{context_str}\n\nSummarize pricing from: {KNOWLEDGE_BASE}"
    response = llm.invoke(prompt)
    return {"messages": [response]}

def general_node(state: ChatbotState):
    """Node: General Q&A"""
    last_msg = state["messages"][-1].content
    # Include full conversation history for context
    all_messages = state["messages"]
    response = llm.invoke(all_messages)
    return {"messages": [response]}

async def mcp_agent_node(state: ChatbotState):
    """Node: Execute MCP Tools"""
    print("🔧 Entering MCP Node")
    last_message = state["messages"][-1]
    tools = state["mcp_tools"]
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # Ask LLM what to do
    # We pass the conversation history to give it context
    response = await llm_with_tools.ainvoke(state["messages"])
    
    # If LLM wants to call a tool
    if response.tool_calls:
        tool_outputs = []
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            print(f"🛠️ Invoking {tool_name} with {args}")
            
            selected_tool = next((t for t in tools if t.name == tool_name), None)
            if selected_tool:
                try:
                    # Execute Tool
                    res = await selected_tool.ainvoke(args)
                    
                    # Create ToolMessage (Required for OpenAI tool flow)
                    tool_outputs.append(ToolMessage(
                        content=str(res),
                        tool_call_id=tool_call['id'],
                        name=tool_name
                    ))
                except Exception as e:
                    tool_outputs.append(ToolMessage(
                        content=f"Error: {str(e)}",
                        tool_call_id=tool_call['id'],
                        name=tool_name
                    ))
        
        # Append the assistant's tool call request AND the tool outputs to history
        # Then ask LLM to generate final natural language answer
        new_messages = [response] + tool_outputs
        
        # Get final response based on tool outputs
        # We verify the chain: History -> ToolCall -> ToolResult -> FinalAnswer
        final_chain = state["messages"] + new_messages
        final_response = await llm_with_tools.ainvoke(final_chain)
        
        # Return all new messages to update state
        return {"messages": new_messages + [final_response]}
    
    else:
        # LLM decided not to call a tool
        return {"messages": [response]}

# --- GRAPH BUILDER ---

def route_intent(state: ChatbotState):
    """Conditional Logic to determine next node"""
    intent = state["user_intent"]
    if intent == "greeting": return "greeting"
    if intent == "services": return "services"
    if intent == "pricing": return "pricing"
    if intent == "mcp_action": return "mcp_agent"
    return "general"

def build_pet_care_graph(mcp_tools):
    """Constructs the LangGraph"""
    workflow = StateGraph(ChatbotState)
    
    # 1. Add Nodes
    workflow.add_node("classify", classify_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("services", service_node)
    workflow.add_node("pricing", pricing_node)
    workflow.add_node("general", general_node)
    workflow.add_node("mcp_agent", mcp_agent_node)
    
    # 2. Define Entry Point
    workflow.set_entry_point("classify")
    
    # 3. Add Edges
    # Classify -> Extract -> Router
    workflow.add_edge("classify", "extract")
    
    # Conditional Edges from Extract to specific handlers
    workflow.add_conditional_edges(
        "extract",
        route_intent,
        {
            "greeting": "greeting",
            "services": "services",
            "pricing": "pricing",
            "mcp_agent": "mcp_agent",
            "general": "general"
        }
    )
    
    # 4. All handlers go to END
    workflow.add_edge("greeting", END)
    workflow.add_edge("services", END)
    workflow.add_edge("pricing", END)
    workflow.add_edge("general", END)
    workflow.add_edge("mcp_agent", END)
    
    return workflow.compile()

# --- WEB SERVER ---

async def handle_chat_request(request):
    """API: Runs the Compiled Graph"""
    try:
        data = await request.json()
        user_input = data.get("message", "")
        session_id = data.get("session_id", "default")
        if not user_input:
            return web.json_response({"error": "No message"}, status=400)
        
        # Get the compiled graph and tools from app context
        app_graph = request.app['graph']
        mcp_tools = request.app['mcp_tools']
        
        # Retrieve conversation history from memory
        if session_id not in conversation_memory:
            conversation_memory[session_id] = []
        
        history = conversation_memory[session_id].copy()
        
        # Prepare Initial State with full history
        initial_state = {
            "messages": history + [HumanMessage(content=user_input)],
            "user_intent": "",
            "extracted_info": {},
            "mcp_tools": mcp_tools,
            "session_id": session_id
        }
        
        # Run the Graph!
        print("⚡ Invoking Graph...")
        final_state = await app_graph.ainvoke(initial_state)
        
        # Get all new messages (everything after the history)
        new_messages = final_state["messages"][len(history):]
        
        # Extract the last AI message
        last_ai_message = None
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg.content
                break
        
        if not last_ai_message:
            last_ai_message = "I'm sorry, I couldn't process that request."
        
        # Update conversation memory with new user message and AI response
        conversation_memory[session_id].append(HumanMessage(content=user_input))
        conversation_memory[session_id].append(AIMessage(content=last_ai_message))
        
        # Keep only last 20 messages to prevent memory overflow
        if len(conversation_memory[session_id]) > 20:
            conversation_memory[session_id] = conversation_memory[session_id][-20:]
        
        return web.json_response({"response": last_ai_message, "session_id": session_id})
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)

async def run_interactive_chat():
    print("=" * 60)
    print("🐾 PAWSOME PET CARE - GRAPH SERVER 🐾")
    print("=" * 60)
    
    # 1. Auth
    try:
        access_token = await authenticate_with_asgardeo()
    except Exception as e:
        print(f"Auth failed (continuing for testing): {e}")
        access_token = "test" # Remove for prod
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 2. Connect MCP & Build Graph
    async with streamablehttp_client(MCP_SERVER_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ MCP Connected")
            
            # Load tools
            tools = await load_mcp_tools(session)
            print(f"🛠️ Tools: {[t.name for t in tools]}")
            
            # BUILD THE GRAPH
            compiled_graph = build_pet_care_graph(tools)
            
            # 3. Start Web Server
            app = web.Application()
            app['graph'] = compiled_graph
            app['mcp_tools'] = tools
            
            app.router.add_post('/chat', handle_chat_request)
            app.router.add_get('/', lambda r: web.FileResponse('index.html'))
            
            # CORS Setup
            import aiohttp_cors
            cors = aiohttp_cors.setup(app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*"
                )
            })
            for route in list(app.router.routes()): cors.add(route)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', 8080)
            print("🚀 Server running at http://localhost:8080")
            await site.start()
            
            await asyncio.Event().wait()

if __name__ == "__main__":
    if not CLIENT_ID:
        print("⚠️  Please set CLIENT_ID in .env")
    else:
        asyncio.run(run_interactive_chat())