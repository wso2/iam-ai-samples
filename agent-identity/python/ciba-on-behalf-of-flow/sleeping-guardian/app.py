"""
Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

 This software is the property of WSO2 LLC. and its suppliers, if any.
 Dissemination of any information or reproduction of any material contained
 herein is strictly forbidden, unless permitted by WSO2 in accordance with
 the WSO2 Commercial License available at http://wso2.com/licenses.
 For specific language governing the permissions and limitations under
 this license, please see the license as well as any agreement you've
 entered into with WSO2 governing the purchase of this software and any
"""

import os
import asyncio
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from pathlib import Path

from market_engine import MarketEngine
from aurelius_agent_llm import AureliusAgentLLM
from ciba_client import CIBAClient

# Load environment variables from current directory (sleeping-guardian folder)
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

app = Flask(__name__)

# Initialize components
MCP_SERVER_BASE_URL = os.getenv("STOCK_MCP_SERVER_URL", "http://localhost:8200/mcp").replace("/mcp", "")

market_engine = MarketEngine(
    initial_price=float(os.getenv("INITIAL_STOCK_PRICE", "150.00")),
    symbol=os.getenv("STOCK_SYMBOL", "NVDA"),
    mcp_server_url=MCP_SERVER_BASE_URL,
    mcp_admin_token=None  # Using unauthenticated endpoint
)

ciba_client = CIBAClient(
    base_url=os.getenv("ASGARDEO_BASE_URL"),
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    agent_id=os.getenv("AGENT_ID"),
    agent_secret=os.getenv("AGENT_SECRET"),
    redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:5001/callback"),
    notification_channel=os.getenv("CIBA_NOTIFICATION_CHANNEL", "email")
)

aurelius_agent = AureliusAgentLLM(
    market_engine=market_engine,
    ciba_client=ciba_client,
    user_email=os.getenv("INVESTOR_EMAIL"),
    mcp_server_url=os.getenv("STOCK_MCP_SERVER_URL", "http://localhost:8200/mcp"),
    model_name=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
    price_threshold=float(os.getenv("PRICE_THRESHOLD", "140.00")),
    trade_amount=float(os.getenv("TRADE_AMOUNT", "5000.00")),
    initial_balance=float(os.getenv("INITIAL_BALANCE", "10000.00"))
)

# --- ROUTES ---

@app.route('/')
def index():
    """Main dashboard showing market and portfolio status."""
    market_data = market_engine.get_current_state()
    portfolio = aurelius_agent.get_portfolio()
    ciba_status = aurelius_agent.get_ciba_status()

    return render_template(
        'dashboard.html',
        market=market_data,
        portfolio=portfolio,
        ciba_status=ciba_status,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@app.route('/crash')
def trigger_crash():
    """Trigger a market crash."""
    market_engine.trigger_crash()
    return redirect(url_for('index'))


@app.route('/stabilize')
def stabilize_market():
    """Stabilize the market."""
    market_engine.stabilize()
    return redirect(url_for('index'))


@app.route('/api/market')
def api_market():
    """API endpoint for market data."""
    return jsonify(market_engine.get_current_state())


@app.route('/api/portfolio')
def api_portfolio():
    """API endpoint for portfolio data."""
    return jsonify(aurelius_agent.get_portfolio())


@app.route('/api/status')
def api_status():
    """API endpoint for overall system status."""
    return jsonify({
        'market': market_engine.get_current_state(),
        'portfolio': aurelius_agent.get_portfolio(),
        'ciba': aurelius_agent.get_ciba_status()
    })


@app.route('/reset')
def reset():
    """Reset the entire system to initial state."""
    market_engine.reset()
    aurelius_agent.reset()
    return redirect(url_for('index'))


# --- BACKGROUND THREADS ---

def run_market_engine():
    """Run market engine in background thread."""
    market_engine.start()


def run_aurelius_agent():
    """Run Aurelius agent in background thread."""
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(aurelius_agent.start())
    finally:
        loop.close()


if __name__ == '__main__':
    # Validate configuration
    required_vars = [
        "ASGARDEO_BASE_URL",
        "CLIENT_ID",
        "CLIENT_SECRET",
        "AGENT_ID",
        "AGENT_SECRET",
        "INVESTOR_EMAIL",
        "GOOGLE_AI_API_KEY",  # LLM API key
        "STOCK_MCP_SERVER_URL"  # MCP server URL
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease configure your .env file based on .env.example")
        exit(1)

    print("=" * 100)
    print("🏦 AURELIUS - The Sleeping Guardian (LLM-Powered with MCP)")
    print("=" * 100)
    print(f"Investor: {os.getenv('INVESTOR_EMAIL')}")
    print(f"Stock Symbol: {os.getenv('STOCK_SYMBOL', 'NVDA')}")
    print(f"Initial Price: ${os.getenv('INITIAL_STOCK_PRICE', '150.00')}")
    print(f"Price Threshold: ${os.getenv('PRICE_THRESHOLD', '140.00')}")
    print(f"Trade Amount: ${os.getenv('TRADE_AMOUNT', '5000.00')}")
    print(f"CIBA Channel: {os.getenv('CIBA_NOTIFICATION_CHANNEL', 'email')}")
    print(f"LLM Model: {os.getenv('MODEL_NAME', 'gemini-2.5-flash')}")
    print(f"MCP Server: {os.getenv('STOCK_MCP_SERVER_URL', 'http://localhost:8200/mcp')}")
    print("=" * 100)
    print("\n🌐 Dashboard: http://localhost:5001")
    print("⚠️  NOTE: Make sure MCP Stock Server is running on port 8200!")
    print("   Start it with: cd mcp-stock-server && python main.py")
    print("\n")

    # Start background threads
    market_thread = threading.Thread(target=run_market_engine, daemon=True)
    agent_thread = threading.Thread(target=run_aurelius_agent, daemon=True)

    market_thread.start()
    agent_thread.start()

    # Start Flask app
    app.run(
        host='0.0.0.0',
        port=int(os.getenv("PORT", "5001")),
        debug=os.getenv("FLASK_DEBUG", "False").lower() == "true"
    )
