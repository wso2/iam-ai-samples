import os
import asyncio
from typing import TypedDict, Annotated, Literal, List, Optional
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
import json
import jwt  # Requires: pip install pyjwt
from urllib.parse import urlencode, parse_qs
from aiohttp import web

# MCP Integration imports
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from langchain_mcp_adapters.tools import load_mcp_tools

from dotenv import load_dotenv
load_dotenv()

# Initialize OpenAI LLM
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.5,
    api_key=os.getenv("OPENAI_API_KEY")
)

# --- GLOBAL STORAGE ---
# 1. Conversation History
conversation_memory = {}
# 2. Context Cache (Fixes DeprecationWarning)
SESSION_CONTEXT_CACHE = {} 

# Extended State to hold User Context
class ChatbotState(TypedDict):
    messages: Annotated[list, operator.add]
    user_intent: str
    extracted_info: dict
    # --- Context Fields ---
    user_email: str
    user_id: Optional[str]
    pets: Optional[List[dict]]
    active_pet_id: Optional[str]
    # --------------------------
    mcp_tools: list
    session_id: str

# MCP Server Configuration
MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

# Asgardeo OAuth2 Configuration
AUTH_ISSUER = os.getenv("AUTH_ISSUER", "https://api.asgardeo.io/t/pasansanjiiwa")
CLIENT_ID = os.getenv("CLIENT_ID", "")
REDIRECT_URI = "http://localhost:8080/callback"
AUTHORIZATION_ENDPOINT = f"{AUTH_ISSUER}/oauth2/authorize"
TOKEN_ENDPOINT = f"{AUTH_ISSUER}/oauth2/token"

KNOWLEDGE_BASE = """
=== PAWSOME PET CARE CENTER ===
SERVICES: Grooming, Boarding, Daycare, Training, Veterinary Services.
PRICING: Grooming $45-$110, Boarding $35-$65/night, Vets $65 checkup.
CONTACT: (555) 123-4567, info@pawsomepetcare.com
"""

# --- AUTHENTICATION LOGIC ---

def generate_pkce():
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('ascii').rstrip('=')
    return code_verifier, code_challenge

async def start_callback_server(auth_future):
    async def callback_handler(request):
        query = request.rel_url.query
        if 'code' in query:
            if not auth_future.done():
                auth_future.set_result(query['code'])
            return web.Response(text="Authentication successful! Return to the console.")
        return web.Response(text="No code found.", status=400)
    
    app = web.Application()
    app.router.add_get('/callback', callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    return runner

async def authenticate_with_asgardeo():
    print("\n🔐 Initiating Asgardeo Authentication...")
    auth_code_future = asyncio.Future()
    code_verifier, code_challenge = generate_pkce()
    
    runner = await start_callback_server(auth_code_future)
    
    # 1. Request scopes: 'openid', 'email', AND 'internal_login'
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile internal_login", 
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    auth_url = f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"
    
    print(f"👉 Opening browser: {auth_url}")
    webbrowser.open(auth_url)
    
    try:
        code = await asyncio.wait_for(auth_code_future, timeout=120)
    except asyncio.TimeoutError:
        raise Exception("Authentication timed out.")
    finally:
        await runner.cleanup()
    
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
        
        id_token = token_data.get("id_token")
        access_token = token_data.get("access_token")
        
        user_email = None
        
        # --- Attempt 1: ID Token ---
        if id_token:
            try:
                decoded = jwt.decode(id_token, options={"verify_signature": False})
                user_email = decoded.get("email")
                if not user_email and "@" in str(decoded.get("username", "")):
                    user_email = decoded.get("username")
            except Exception as e:
                print(f"⚠️ Error decoding ID token: {e}")

        # --- Attempt 2: SCIM2/Me (The Robust Fix) ---
        if not user_email and access_token:
            print("⚠️ Email not in ID Token. Attempting SCIM2 lookup...")
            
            # Strip '/oauth2/...' to get base URL
            base_url = AUTH_ISSUER.split("/oauth2")[0]
            scim_url = f"{base_url}/scim2/Me"
            
            try:
                scim_resp = await client.get(
                    scim_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/scim+json"
                    }
                )
                
                if scim_resp.status_code == 200:
                    scim_data = scim_resp.json()
                    
                    # DEBUG: Print the actual structure so we can see it
                    print(f"🔍 RAW SCIM DATA: {json.dumps(scim_data)}")
                    
                    # 1. Try 'emails' array
                    emails = scim_data.get("emails")
                    if isinstance(emails, list) and len(emails) > 0:
                        primary = emails[0]
                        
                        # FIX: Handle both Dict {"value": "..."} and String "..."
                        if isinstance(primary, dict):
                            user_email = primary.get("value")
                        elif isinstance(primary, str):
                            user_email = primary
                        else:
                            print(f"❌ Unknown email format in SCIM: {type(primary)}")

                    # 2. Try 'userName' if it looks like an email
                    if not user_email:
                        u_name = scim_data.get("userName")
                        if u_name and "@" in u_name:
                            user_email = u_name
                            print("✅ Used userName as email.")
                else:
                    print(f"❌ SCIM Failed ({scim_resp.status_code}): {scim_resp.text}")
                    
            except Exception as e:
                print(f"❌ SCIM Exception: {e}")

        if user_email:
            print(f"👤 Successfully Authenticated: {user_email}")
        else:
            print("❌ Failed to retrieve email. Bot will not know who you are.")

        # We return the valid access_token regardless, so the MCP connection succeeds
        return access_token, user_email

# --- NODES ---

async def load_context_node(state: ChatbotState):
    """Startup Node: Loads User ID and Pets into state."""
    print("🔄 Loading Context...")
    
    current_id = state.get('user_id')
    current_pets = state.get('pets') or []
    user_email = state.get('user_email')
    tools_list = state['mcp_tools']

    new_state = {
        'user_id': current_id,
        'pets': current_pets,
        'active_pet_id': state.get('active_pet_id')
    }
    
    # --- STEP 1: GET USER ID ---
    if not current_id and user_email and user_email != "unknown":
        try:
            tool = next((t for t in tools_list if t.name == 'get_user_id_by_email'), None)
            if tool:
                print(f"   👉 Calling get_user_id_by_email({user_email})...")
                result = await tool.ainvoke({"email": user_email})
                
                # Parsing logic
                data = {}
                if hasattr(result, 'content'): result = result.content
                if isinstance(result, str):
                    try:
                        clean = result.replace('```json', '').replace('```', '').strip()
                        data = json.loads(clean)
                    except: pass
                elif isinstance(result, dict):
                    data = result
                
                new_state['user_id'] = data.get('user_id')
                print(f"   ✅ Resolved User ID: {new_state['user_id']}")
        except Exception as e:
            print(f"   ❌ Error Step 1: {e}")

    # --- STEP 2: GET PETS ---
    # Always refresh pets if we have a user ID, just in case a new one was added
    if new_state['user_id']: 
        try:
            tool = next((t for t in tools_list if t.name == 'get_pets_by_user_id'), None)
            if tool:
                # Only print if we are actually fetching for the first time or refreshing
                if not current_pets: 
                    print(f"   👉 Calling get_pets_by_user_id({new_state['user_id']})...")
                
                result = await tool.ainvoke({"user_id": new_state['user_id']})
                
                data = {}
                if hasattr(result, 'content'): result = result.content
                if isinstance(result, str):
                    try:
                        clean = result.replace('```json', '').replace('```', '').strip()
                        data = json.loads(clean)
                    except: pass
                elif isinstance(result, dict):
                    data = result
                    
                pets = data.get('pets', [])
                new_state['pets'] = pets
                
                # Auto-select logic: If 1 pet, select it. If >1, ensure NONE is selected initially unless already set.
                if len(pets) == 1:
                    new_state['active_pet_id'] = pets[0]['pet_id']
                elif len(pets) > 1 and not new_state['active_pet_id']:
                    new_state['active_pet_id'] = None # Explicitly reset to force asking
                    
        except Exception as e:
            print(f"   ❌ Error Step 2: {e}")

    return new_state

def classify_node(state: ChatbotState):
    """Classify intent"""
    last_message = state["messages"][-1].content
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify into: greeting, services, pricing, mcp_action (for personal/pet data), general. Return label only."),
        ("user", "{message}")
    ])
    result = (prompt | llm).invoke({"message": last_message})
    intent = result.content.strip().lower()
    print(f"🎯 Intent: {intent}")
    return {"user_intent": intent}

async def mcp_agent_node(state: ChatbotState):
    """
    Agent with Dynamic Context Logic.
    Calculates the strict state of the world before letting the LLM act.
    """
    print("🔧 Entering MCP Agent Node (Dynamic Mode)")
    
    tools = state["mcp_tools"]
    user_msg = state["messages"][-1].content.lower()
    
    # 1. Retrieve Data
    user_id = state.get("user_id", "unknown")
    user_email = state.get("user_email", "unknown")
    pets = state.get("pets", [])
    active_pet_id = state.get("active_pet_id")
    
    # 2. DYNAMIC RESOLUTION: Check if user mentioned a pet name in THIS message
    # This removes the need for the LLM to "guess" or "extract" it.
    detected_pet_name = None
    if pets:
        for pet in pets:
            if pet['pet_name'].lower() in user_msg:
                active_pet_id = pet['pet_id']
                detected_pet_name = pet['pet_name']
                print(f"   [Logic] Detected pet name '{detected_pet_name}' in message. Setting context.")
                break

    # 3. DYNAMIC PROMPT GENERATION
    # We build the instructions based on the specific scenario.
    
    base_context = f"User Email: {user_email}\nUser ID: {user_id}\n"
    specific_instruction = ""
    
    # SCENARIO A: No Pets
    if not pets:
        pet_info = "User has NO registered pets."
        specific_instruction = "Inform the user they have no pets registered. Do not call any pet-related tools."

    # SCENARIO B: Single Pet (Auto-Context)
    elif len(pets) == 1:
        p = pets[0]
        pet_info = f"User has 1 pet: {p['pet_name']} (ID: {p['pet_id']})."
        specific_instruction = f"The user is referring to {p['pet_name']} (ID: {p['pet_id']}). Use this ID for any tool calls."

    # SCENARIO C: Multiple Pets, BUT one is Selected (Active)
    elif len(pets) > 1 and active_pet_id:
        # Find the name of the active pet
        active_pet = next((p for p in pets if p['pet_id'] == active_pet_id), None)
        pet_info = f"User has {len(pets)} pets. CURRENT CONTEXT: {active_pet['pet_name']} (ID: {active_pet_id})."
        specific_instruction = f"Focus ONLY on {active_pet['pet_name']} (ID: {active_pet['pet_id']}) for this response."

    # SCENARIO D: Multiple Pets, NONE Selected (Ambiguity)
    else:
        # List all pets for the AI
        names = [f"{p['pet_name']} (ID: {p['pet_id']})" for p in pets]
        pet_info = f"User has {len(pets)} pets: " + ", ".join(names)
        
        # The Instruction: STRICTLY ASK FOR CLARIFICATION
        specific_instruction = (
            "CRITICAL: The user has multiple pets and has NOT specified which one they are talking about.\n"
            "1. If the user asks a general question (e.g., 'how many pets?'), answer it.\n"
            "2. If the user asks for specific info (vaccinations, appointments), you must ASK: 'Which pet are you referring to?'\n"
            "3. DO NOT call any tools yet."
        )

    # 4. Combine into System Prompt
    final_system_prompt = f"""You are a Pawsome Veterinary Assistant.

    === DYNAMIC DATA ===
    {base_context}
    {pet_info}
    ====================

    === CURRENT INSTRUCTION ===
    {specific_instruction}
    """

    # 5. Execute LLM
    llm_with_tools = llm.bind_tools(tools)
    messages_with_context = [SystemMessage(content=final_system_prompt)] + state["messages"]
    
    response = await llm_with_tools.ainvoke(messages_with_context)
    
    # 6. Handle Tools
    if response.tool_calls:
        tool_outputs = []
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            
            # Safety Check: If we are in Scenario D (Ambiguity) but LLM tried to call a tool anyway,
            # we can intercept it here. But usually, the strong prompt prevents this.
            
            print(f"🛠️ Agent calling {tool_name} with {args}")
            selected_tool = next((t for t in tools if t.name == tool_name), None)
            if selected_tool:
                try:
                    res = await selected_tool.ainvoke(args)
                    tool_outputs.append(ToolMessage(content=str(res), tool_call_id=tool_call['id'], name=tool_name))
                except Exception as e:
                    tool_outputs.append(ToolMessage(content=f"Error: {e}", tool_call_id=tool_call['id'], name=tool_name))
        
        final_response = await llm_with_tools.ainvoke(messages_with_context + [response] + tool_outputs)
        
        # Return with updated active_pet_id (persists the selection)
        return {"messages": [response] + tool_outputs + [final_response], "active_pet_id": active_pet_id}
    
    else:
        return {"messages": [response], "active_pet_id": active_pet_id}

def greeting_node(state: ChatbotState):
    return {"messages": [AIMessage(content="🐾 Welcome back! I've loaded your pet details. How can I help?")]}
def service_node(state: ChatbotState):
    return {"messages": [llm.invoke(f"Summarize services from: {KNOWLEDGE_BASE}")]}
def pricing_node(state: ChatbotState):
    return {"messages": [llm.invoke(f"Summarize pricing from: {KNOWLEDGE_BASE}")]}
def general_node(state: ChatbotState):
    return {"messages": [llm.invoke(state["messages"])]}

def route_intent(state: ChatbotState):
    intent = state["user_intent"]
    if intent == "greeting": return "greeting"
    if intent == "services": return "services"
    if intent == "pricing": return "pricing"
    if intent == "mcp_action": return "mcp_agent"
    return "general"

def build_pet_care_graph(mcp_tools):
    workflow = StateGraph(ChatbotState)
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("services", service_node)
    workflow.add_node("pricing", pricing_node)
    workflow.add_node("general", general_node)
    workflow.add_node("mcp_agent", mcp_agent_node)
    
    workflow.set_entry_point("load_context")
    workflow.add_edge("load_context", "classify")
    workflow.add_conditional_edges("classify", route_intent, {
        "greeting": "greeting", "services": "services", "pricing": "pricing", "mcp_agent": "mcp_agent", "general": "general"
    })
    workflow.add_edge("greeting", END)
    workflow.add_edge("services", END)
    workflow.add_edge("pricing", END)
    workflow.add_edge("general", END)
    workflow.add_edge("mcp_agent", END)
    return workflow.compile()

# --- WEB SERVER ---

async def handle_chat_request(request):
    try:
        data = await request.json()
        user_input = data.get("message", "")
        session_id = data.get("session_id", "default")
        
        app_graph = request.app['graph']
        mcp_tools = request.app['mcp_tools']
        user_email = request.app['user_email']
        
        if session_id not in conversation_memory:
            conversation_memory[session_id] = []
        history = conversation_memory[session_id].copy()
        
        # Retrieve cached context from GLOBAL cache
        cached_ctx = SESSION_CONTEXT_CACHE.get(session_id, {})

        initial_state = {
            "messages": history + [HumanMessage(content=user_input)],
            "user_email": user_email,
            "user_id": cached_ctx.get('user_id'),
            "pets": cached_ctx.get('pets'),
            "active_pet_id": cached_ctx.get('active_pet_id'),
            "mcp_tools": mcp_tools,
            "session_id": session_id,
            "user_intent": "",
            "extracted_info": {}
        }
        
        final_state = await app_graph.ainvoke(initial_state)
        
        # Update GLOBAL cache
        SESSION_CONTEXT_CACHE[session_id] = {
            'user_id': final_state.get('user_id'),
            'pets': final_state.get('pets'),
            'active_pet_id': final_state.get('active_pet_id')
        }
        
        new_messages = final_state["messages"][len(history):]
        last_ai_message = "..."
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg.content
                break
        
        conversation_memory[session_id].append(HumanMessage(content=user_input))
        conversation_memory[session_id].append(AIMessage(content=last_ai_message))
        
        return web.json_response({
            "response": last_ai_message, 
            "session_id": session_id,
            "debug_pet": final_state.get("active_pet_id")
        })
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)

async def run_interactive_chat():
    print("=" * 60)
    print("🐾 PAWSOME PET CARE - INTELLIGENT AGENT 🐾")
    print("=" * 60)
    
    try:
        access_token, user_email = await authenticate_with_asgardeo()
    except Exception as e:
        print(f"Auth failed (using mock): {e}")
        access_token = "mock_token"
        user_email = "pasansanjiiwa2022@gmail.com"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with streamablehttp_client(MCP_SERVER_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            
            compiled_graph = build_pet_care_graph(tools)
            
            app = web.Application()
            app['graph'] = compiled_graph
            app['mcp_tools'] = tools
            app['user_email'] = user_email
            
            app.router.add_post('/chat', handle_chat_request)
            app.router.add_get('/', lambda r: web.FileResponse('index.html'))
            
            import aiohttp_cors
            cors = aiohttp_cors.setup(app, defaults={
                "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")
            })
            for route in list(app.router.routes()): cors.add(route)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', 8080)
            print(f"🚀 User {user_email} logged in.")
            print("🚀 Server running at http://localhost:8080")
            await site.start()
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_interactive_chat())