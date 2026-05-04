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

import time
import random
import threading
import os
import requests
from datetime import datetime
from typing import Dict, Optional


class MarketEngine:
    """
    Synthetic stock market simulator that can be controlled for demo purposes.
    Simulates realistic price movements and controllable market crashes.
    """

    def __init__(self, initial_price: float = 150.00, symbol: str = "NVDA",
                 mcp_server_url: Optional[str] = None, mcp_admin_token: Optional[str] = None):
        self.initial_price = initial_price
        self.current_price = initial_price
        self.symbol = symbol
        self.status = "STABLE"  # STABLE, VOLATILE, CRASHING, RECOVERING
        self.running = False
        self.lock = threading.Lock()

        # MCP Server integration (for syncing prices)
        self.mcp_server_url = mcp_server_url
        self.mcp_admin_token = mcp_admin_token
        self.last_synced_price = initial_price
        self.sync_threshold = 0.5  # Only sync if price changed by more than $0.50

        # Price history for charts (last 100 data points)
        self.price_history = []
        self.max_history = 100

        # Market parameters
        self.volatility = {
            "STABLE": 0.2,      # Small fluctuations
            "VOLATILE": 0.8,    # Medium fluctuations
            "CRASHING": 3.5,    # Large drops
            "RECOVERING": 1.0   # Medium gains
        }

    def start(self):
        """Start the market simulation loop."""
        self.running = True
        print(f"[Market Engine] Started - {self.symbol} at ${self.current_price:.2f}")

        # Initial sync to MCP server
        self._sync_price_to_mcp(self.current_price)

        while self.running:
            self._update_price()
            time.sleep(1)  # Update every second

    def stop(self):
        """Stop the market simulation."""
        self.running = False

    def _sync_price_to_mcp(self, new_price: float):
        """Sync the current price to MCP server if configured."""
        if not self.mcp_server_url:
            return

        # Only sync if price changed significantly
        if abs(new_price - self.last_synced_price) < self.sync_threshold:
            return

        try:
            # Call MCP server's market update endpoint (no auth required)
            response = requests.post(
                f"{self.mcp_server_url}/api/market/update",
                json={"symbol": self.symbol, "new_price": new_price},
                timeout=2
            )
            if response.ok:
                self.last_synced_price = new_price
                print(f"[Market Engine] ✓ Synced price ${new_price:.2f} to MCP server")
            else:
                print(f"[Market Engine] ⚠️  Failed to sync price to MCP: {response.status_code}")
        except Exception as e:
            # Don't crash if MCP sync fails - just log it
            pass  # Silently ignore sync errors to avoid spam

    def _update_price(self):
        """Update the stock price based on current market status."""
        with self.lock:
            volatility = self.volatility.get(self.status, 0.2)

            if self.status == "CRASHING":
                # During crash, price mostly goes down
                change = random.uniform(-volatility, volatility * 0.2)
            elif self.status == "RECOVERING":
                # During recovery, price mostly goes up
                change = random.uniform(-volatility * 0.2, volatility)
            else:
                # Normal fluctuation (can go up or down)
                change = random.uniform(-volatility, volatility)

            self.current_price += change

            # Ensure price doesn't go negative
            if self.current_price < 1.0:
                self.current_price = 1.0

            # Sync to MCP server if configured
            self._sync_price_to_mcp(self.current_price)

            # Add to history
            self.price_history.append({
                'timestamp': datetime.now().isoformat(),
                'price': self.current_price,
                'status': self.status
            })

            # Limit history size
            if len(self.price_history) > self.max_history:
                self.price_history.pop(0)

    def get_current_state(self) -> Dict:
        """Get current market state."""
        with self.lock:
            # Calculate price change from initial
            change = self.current_price - self.initial_price
            change_percent = (change / self.initial_price) * 100

            return {
                'symbol': self.symbol,
                'price': round(self.current_price, 2),
                'initial_price': round(self.initial_price, 2),
                'change': round(change, 2),
                'change_percent': round(change_percent, 2),
                'status': self.status,
                'timestamp': datetime.now().isoformat(),
                'history': self.price_history[-20:]  # Last 20 points
            }

    def trigger_crash(self):
        """Trigger a market crash."""
        with self.lock:
            self.status = "CRASHING"
            # Force immediate sync on status change
            self.last_synced_price = self.current_price - 999  # Force sync
            print(f"[Market Engine] 🚨 MARKET CRASH TRIGGERED - {self.symbol}")

    def stabilize(self):
        """Return market to stable state."""
        with self.lock:
            self.status = "STABLE"
            print(f"[Market Engine] ✓ Market stabilized - {self.symbol}")

    def trigger_recovery(self):
        """Trigger market recovery."""
        with self.lock:
            self.status = "RECOVERING"
            print(f"[Market Engine] 📈 Market recovering - {self.symbol}")

    def set_volatile(self):
        """Set market to volatile state."""
        with self.lock:
            self.status = "VOLATILE"
            print(f"[Market Engine] ⚠️  Market volatile - {self.symbol}")

    def reset(self):
        """Reset market to initial state."""
        with self.lock:
            self.current_price = self.initial_price
            self.status = "STABLE"
            self.price_history = []
            print(f"[Market Engine] 🔄 Market reset - {self.symbol} at ${self.initial_price:.2f}")

    def get_price(self) -> float:
        """Get current price (thread-safe)."""
        with self.lock:
            return self.current_price

    def get_status(self) -> str:
        """Get current market status (thread-safe)."""
        with self.lock:
            return self.status
