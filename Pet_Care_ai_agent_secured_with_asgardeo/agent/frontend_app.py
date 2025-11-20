import streamlit as st
import asyncio
import nest_asyncio
from backend_logic import perform_login, run_chat_turn
from langchain_core.messages import HumanMessage, AIMessage

# Apply nest_asyncio to allow async loops inside Streamlit
nest_asyncio.apply()

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pawsome Pet Care AI", page_icon="🐾")

# --- STATE MANAGEMENT ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "access_token" not in st.session_state:
    st.session_state.access_token = None

# --- SIDEBAR (LOGIN) ---
with st.sidebar:
    st.header("🔐 Authentication")
    st.markdown("Login securely via **Asgardeo** to access the Pet Care Tools.")
    
    if st.session_state.access_token:
        st.success("✅ Authenticated")
        if st.button("Logout"):
            st.session_state.access_token = None
            st.session_state.messages = []
            st.rerun()
    else:
        st.warning("🔒 Please login to start")
        if st.button("Login with Asgardeo"):
            with st.spinner("Opening browser... Please login."):
                token = asyncio.run(perform_login())
                if token:
                    st.session_state.access_token = token
                    st.rerun()
                else:
                    st.error("Login failed or timed out.")

# --- MAIN CHAT AREA ---
st.title("🐾 Pawsome Pet Care Agent")
st.caption("Powered by Asgardeo Auth & MCP Tools")

# 1. Display Chat History
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage) and msg.content:
        with st.chat_message("assistant"):
            st.markdown(msg.content)

# 2. Chat Input Handler
if prompt := st.chat_input("Book an appointment, check vaccines..."):
    
    # Check Auth
    if not st.session_state.access_token:
        st.error("🔒 You must login via the sidebar to use the chat.")
        st.stop()

    # Show User Message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process Response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Create a Status Container for "Thinking" steps
        status_container = st.status("🤖 Connecting to MCP...", expanded=True)

        def update_status(msg, data=None):
            """Callback to update UI from backend"""
            status_container.write(msg)
            if data:
                status_container.json(data)

        # Run Backend Logic
        final_text, updated_history = asyncio.run(
            run_chat_turn(
                prompt, 
                st.session_state.messages, 
                st.session_state.access_token,
                status_callback=update_status
            )
        )
        
        # Finalize UI
        status_container.update(label="✅ Complete", state="complete", expanded=False)
        message_placeholder.markdown(final_text)
        
        # Save History
        st.session_state.messages = updated_history