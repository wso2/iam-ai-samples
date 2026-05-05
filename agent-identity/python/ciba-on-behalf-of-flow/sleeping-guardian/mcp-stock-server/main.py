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
from datetime import datetime, timezone
from dotenv import load_dotenv
from pydantic import AnyHttpUrl
import random
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

import jwt as pyjwt
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from jwt_validator import JWTValidator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Extract user ID from token
def get_user_id(token: AccessToken) -> str:
    """Extract the user's subject identifier from a validated access token."""
    payload = pyjwt.decode(token.token, options={"verify_signature": False})
    sub = payload.get("sub")
    if not sub:
        raise PermissionError("Token does not contain a 'sub' claim. An OBO token is required.")
    return sub


def require_scopes(*needed: str) -> AccessToken:
    """Enforce per-tool scopes. Returns the access token if all scopes are present."""
    token = get_access_token()
    if token is None:
        logger.error("[SCOPE CHECK] ❌ No access token in request context")
        raise PermissionError("No access token in request context.")

    have = set(token.scopes or [])
    missing = [s for s in needed if s not in have]

    logger.info(f"[SCOPE CHECK] Required: {list(needed)}")
    logger.info(f"[SCOPE CHECK] Available: {list(have)}")

    if missing:
        logger.warning("=" * 80)
        logger.warning("[SCOPE CHECK FAILED] ❌ INSUFFICIENT SCOPES")
        logger.warning(f"  Required: {list(needed)}")
        logger.warning(f"  Available: {list(have)}")
        logger.warning(f"  Missing: {missing}")
        logger.warning("  → CIBA authorization needed!")
        logger.warning("=" * 80)
        raise PermissionError(
            f"insufficient_scope: missing {missing}. "
            "Request authorization via CIBA with these scopes."
        )

    logger.info(f"[SCOPE CHECK] ✅ All required scopes present")
    return token


# In-memory data stores keyed by user id
_user_portfolios: dict[str, dict] = {}
_market_data: dict[str, dict] = {
    "NVDA": {"price": 150.00, "symbol": "NVDA", "name": "NVIDIA Corporation", "change": 0.00},
    "AAPL": {"price": 175.00, "symbol": "AAPL", "name": "Apple Inc.", "change": 0.00},
    "MSFT": {"price": 380.00, "symbol": "MSFT", "name": "Microsoft Corporation", "change": 0.00},
}
_trade_history: dict[str, list[dict]] = {}


def _get_user_portfolio(user_id: str) -> dict:
    """Get or create user portfolio."""
    if user_id not in _user_portfolios:
        _user_portfolios[user_id] = {
            "balance": 10000.00,
            "holdings": {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    return _user_portfolios[user_id]


def _add_trade_history(user_id: str, trade: dict):
    """Add trade to user's history."""
    if user_id not in _trade_history:
        _trade_history[user_id] = []
    _trade_history[user_id].append(trade)


class JWTTokenVerifier(TokenVerifier):
    """JWT token verifier using Asgardeo JWKS."""

    def __init__(self, jwks_url: str, issuer: str, client_id: str):
        self.jwt_validator = JWTValidator(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=client_id,
            ssl_verify=True
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = await self.jwt_validator.validate_token(token)

            expires_at = payload.get("exp")
            scopes = payload.get("scope", "").split() if payload.get("scope") else []
            subject = payload.get("sub")
            audience = payload.get("aud")
            aut = payload.get("aut")
            act = payload.get("act")

            logger.info("=" * 80)
            logger.info("[JWT VALIDATION SUCCESS]")
            logger.info(f"  Subject (sub): {subject}")
            logger.info(f"  Auth Method (aut): {aut}")
            logger.info(f"  🔍 Token Scopes: {scopes}")
            if act:
                logger.info(f"  Actor (act): {act}")
            logger.info("=" * 80)

            return AccessToken(
                token=token,
                client_id=audience if isinstance(audience, str) else self.jwt_validator.audience,
                scopes=scopes,
                expires_at=str(expires_at) if expires_at else None
            )
        except ValueError as e:
            logger.warning(f"Token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return None


AUTH_ISSUER = os.getenv("AUTH_ISSUER")
CLIENT_ID = os.getenv("CLIENT_ID")
JWKS_URL = os.getenv("JWKS_URL")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8200"))

if not all([AUTH_ISSUER, CLIENT_ID, JWKS_URL]):
    raise ValueError("Missing required environment variables: AUTH_ISSUER, CLIENT_ID, or JWKS_URL")

mcp = FastMCP(
    "Stock Trading Server",
    host="127.0.0.1",  # Bind to localhost only for security
    port=MCP_SERVER_PORT,
    token_verifier=JWTTokenVerifier(JWKS_URL, AUTH_ISSUER, CLIENT_ID),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH_ISSUER),
        resource_server_url=AnyHttpUrl(f"http://localhost:{MCP_SERVER_PORT}"),
    ),
)


# ==================== MARKET DATA TOOLS (stock:read scope) ====================

@mcp.tool()
async def get_market_price(symbol: str) -> dict:
    """
    Get current market price for a stock symbol.
    Requires scope: stock:read

    Args:
        symbol: Stock symbol (e.g., "NVDA", "AAPL")

    Returns:
        Dictionary with symbol, price, name, and change
    """
    require_scopes("stock:read")

    symbol = symbol.upper()
    if symbol not in _market_data:
        raise ValueError(f"Unknown stock symbol: {symbol}")

    return _market_data[symbol]


@mcp.tool()
async def list_available_stocks() -> list[dict]:
    """
    List all available stocks for trading.
    Requires scope: stock:read

    Returns:
        List of available stock symbols with current prices
    """
    require_scopes("stock:read")
    return list(_market_data.values())


@mcp.tool()
async def get_my_portfolio() -> dict:
    """
    Get the current user's portfolio including balance and holdings.
    Requires scope: stock:read

    Returns:
        Dictionary with balance, holdings, and portfolio value
    """
    token = require_scopes("stock:read")
    user_id = get_user_id(token)
    portfolio = _get_user_portfolio(user_id)

    # Calculate total portfolio value
    total_value = portfolio["balance"]
    for symbol, shares in portfolio["holdings"].items():
        if symbol in _market_data:
            total_value += shares * _market_data[symbol]["price"]

    return {
        "balance": portfolio["balance"],
        "holdings": portfolio["holdings"],
        "total_value": total_value,
        "created_at": portfolio["created_at"]
    }


@mcp.tool()
async def get_trade_history() -> list[dict]:
    """
    Get the current user's trade history.
    Requires scope: stock:read

    Returns:
        List of past trades with timestamp, symbol, action, shares, and price
    """
    token = require_scopes("stock:read")
    user_id = get_user_id(token)
    return _trade_history.get(user_id, [])


# ==================== TRADING TOOLS (stock:trade scope) ====================

@mcp.tool()
async def buy_stock(symbol: str, shares: int) -> dict:
    """
    Buy shares of a stock.
    Requires scope: stock:trade

    Args:
        symbol: Stock symbol to buy (e.g., "NVDA")
        shares: Number of shares to buy

    Returns:
        Trade confirmation with details
    """
    token = require_scopes("stock:trade", "stock:read")
    user_id = get_user_id(token)

    logger.info(f"[BUY_STOCK] ✅ Scope check passed for user {user_id}")

    symbol = symbol.upper()
    if symbol not in _market_data:
        raise ValueError(f"Unknown stock symbol: {symbol}")

    if shares <= 0:
        raise ValueError("Number of shares must be positive")

    portfolio = _get_user_portfolio(user_id)
    current_price = _market_data[symbol]["price"]
    total_cost = shares * current_price

    if portfolio["balance"] < total_cost:
        raise ValueError(
            f"Insufficient funds. Need ${total_cost:.2f}, have ${portfolio['balance']:.2f}"
        )

    # Execute trade
    portfolio["balance"] -= total_cost
    if symbol not in portfolio["holdings"]:
        portfolio["holdings"][symbol] = 0
    portfolio["holdings"][symbol] += shares

    # Record trade
    trade = {
        "id": str(len(_trade_history.get(user_id, [])) + 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "BUY",
        "symbol": symbol,
        "shares": shares,
        "price": current_price,
        "total": total_cost,
        "balance_after": portfolio["balance"]
    }
    _add_trade_history(user_id, trade)

    logger.info(f"[TRADE] User {user_id} bought {shares} {symbol} @ ${current_price:.2f}")

    return trade


@mcp.tool()
async def sell_stock(symbol: str, shares: int) -> dict:
    """
    Sell shares of a stock.
    Requires scope: stock:trade

    Args:
        symbol: Stock symbol to sell (e.g., "NVDA")
        shares: Number of shares to sell

    Returns:
        Trade confirmation with details
    """
    token = require_scopes("stock:trade", "stock:read")
    user_id = get_user_id(token)

    symbol = symbol.upper()
    if symbol not in _market_data:
        raise ValueError(f"Unknown stock symbol: {symbol}")

    if shares <= 0:
        raise ValueError("Number of shares must be positive")

    portfolio = _get_user_portfolio(user_id)

    if symbol not in portfolio["holdings"] or portfolio["holdings"][symbol] < shares:
        owned = portfolio["holdings"].get(symbol, 0)
        raise ValueError(f"Insufficient shares. Have {owned}, trying to sell {shares}")

    # Execute trade
    current_price = _market_data[symbol]["price"]
    total_proceeds = shares * current_price

    portfolio["holdings"][symbol] -= shares
    if portfolio["holdings"][symbol] == 0:
        del portfolio["holdings"][symbol]
    portfolio["balance"] += total_proceeds

    # Record trade
    trade = {
        "id": str(len(_trade_history.get(user_id, [])) + 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "SELL",
        "symbol": symbol,
        "shares": shares,
        "price": current_price,
        "total": total_proceeds,
        "balance_after": portfolio["balance"]
    }
    _add_trade_history(user_id, trade)

    logger.info(f"[TRADE] User {user_id} sold {shares} {symbol} @ ${current_price:.2f}")

    return trade


# ==================== MARKET ADMIN TOOLS (internal) ====================

@mcp.tool()
async def update_market_price(symbol: str, new_price: float) -> dict:
    """
    Update market price for a stock (admin/simulation only).
    Requires scope: stock:admin

    Args:
        symbol: Stock symbol
        new_price: New price for the stock

    Returns:
        Updated market data
    """
    require_scopes("stock:admin")

    symbol = symbol.upper()
    if symbol not in _market_data:
        raise ValueError(f"Unknown stock symbol: {symbol}")

    old_price = _market_data[symbol]["price"]
    _market_data[symbol]["price"] = new_price
    _market_data[symbol]["change"] = new_price - old_price

    logger.info(f"[MARKET] Price updated: {symbol} ${old_price:.2f} → ${new_price:.2f}")

    return _market_data[symbol]


# ==================== MARKET ENGINE SYNC ENDPOINT (NO AUTH) ====================
# SECURITY NOTE: This endpoint has no authentication to allow the market simulator
# to update prices. The server is bound to 127.0.0.1 (localhost only) to prevent
# external network access. For production use, implement proper authentication.

@mcp.custom_route("/api/market/update", methods=["POST"])
async def market_update_endpoint(request: Request):
    """
    Unauthenticated endpoint for market engine to push price updates.
    This bypasses MCP tools and directly updates the in-memory market data.

    SECURITY: Server is bound to localhost only (127.0.0.1) to prevent
    external access to this unauthenticated endpoint.
    """
    try:
        data = await request.json()
        symbol = data.get("symbol", "").upper()
        new_price = data.get("new_price")

        if not symbol or new_price is None:
            return JSONResponse(
                {"error": "Missing symbol or new_price"},
                status_code=400
            )

        if symbol not in _market_data:
            return JSONResponse(
                {"error": f"Unknown symbol: {symbol}"},
                status_code=404
            )

        old_price = _market_data[symbol]["price"]
        _market_data[symbol]["price"] = float(new_price)
        _market_data[symbol]["change"] = float(new_price) - old_price

        logger.info(f"[MARKET SYNC] {symbol} price updated: ${old_price:.2f} → ${new_price:.2f}")

        return JSONResponse({
            "success": True,
            "symbol": symbol,
            "old_price": old_price,
            "new_price": new_price
        })

    except Exception as e:
        logger.error(f"[MARKET SYNC] Error: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    print("=" * 80)
    print("Stock Trading MCP Server")
    print("=" * 80)
    print(f"Port: {MCP_SERVER_PORT}")
    print(f"Issuer: {AUTH_ISSUER}")
    print(f"Client ID: {CLIENT_ID}")
    print("=" * 80)
    print("\nAvailable Scopes:")
    print("  - stock:read   : Read market data and portfolio")
    print("  - stock:trade  : Execute buy/sell trades")
    print("  - stock:admin  : Update market prices (simulation)")
    print("=" * 80)
    print("\nMarket Sync Endpoint:")
    print(f"  POST http://localhost:{MCP_SERVER_PORT}/api/market/update")
    print("  (No authentication required - for market engine only)")
    print("\n⚠️  SECURITY NOTE:")
    print("  Server is bound to 127.0.0.1 (localhost only)")
    print("  This prevents external network access to unauthenticated endpoints")
    print("=" * 80)
    print("\nStarting server...\n")

    mcp.run(transport="streamable-http")
